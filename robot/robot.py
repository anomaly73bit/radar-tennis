#!/usr/bin/env python3
"""
Radar: ogni 30 minuti (GitHub Actions)
  1. scarica, quando il budget lo permette, le quote di tennis, MMA, pugilato, basket (NBA, Eurolega)
     e hockey (NHL) da The Odds API: quote sharp (Pinnacle, Betfair, Matchbook) e quote di
     Unibet, Betsson, NordicBet, William Hill, 888sport;
  2. trova gli esiti dove il miglior bookmaker paga almeno il 3% piu' della quota giusta;
  3. li registra come giocate simulate (conto 200 euro, 2% a giocata), manda l'email per i nuovi
     e li chiude con i risultati (ESPN per il tennis, The Odds API per gli altri sport);
  4. rigenera la pagina docs/index.html.
Nessuna scommessa vera viene piazzata.
"""
import datetime, html, json, os, pathlib, urllib.request, zoneinfo
from tennis_model import State, Names, as_date, norm
import sharp
import notify

HERE = pathlib.Path(__file__).resolve().parent
OUT = HERE.parent / "docs" / "index.html"
STATE, BETS, BT, SNAP = HERE / "state.json", HERE / "bets.json", HERE / "backtest.json", HERE / "sharp.json"
SOGLIA = 0.03
ODDS_RANGE = (1.20, 6.0)
MIN_INTERVAL_H = 2.0
SCORES_EVERY_H = 8.0
PRAGUE = zoneinfo.ZoneInfo("Europe/Prague")
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0", "Accept": "application/json"}
ESPN = "https://site.api.espn.com/apis/site/v2/sports/tennis/{tour}/scoreboard?dates={d}"
ICON = {"Tennis": "🎾", "MMA": "🥊", "Pugilato": "🥊", "Basket": "🏀", "Hockey": "🏒"}
NOW = datetime.datetime.now(datetime.timezone.utc)


def utc(iso):
    return datetime.datetime.fromisoformat(iso.replace("Z", "+00:00"))



def get(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as r:
        return json.loads(r.read())


def surface_of(st, month, *names):
    """Superficie del torneo nello stesso periodo dell'anno (stesso mese o quello vicino); altrimenti cemento."""
    for n in names:
        n = (n or "").lower()
        for key in (n, n.split(",")[0].strip()):
            months = st.surfaces.get(key)
            if not months:
                continue
            for dm in (0, -1, 1):
                m = str((month - 1 + dm) % 12 + 1)
                if m in months:
                    return months[m]
    return "Hard"


def short_key(full, short):
    """'F. Cina' -> 'Cina F.' (formato dei dati storici) per i giocatori nuovi."""
    if short and ". " in short:
        ini, sur = short.split(". ", 1)
        return f"{sur} {ini[0]}."
    parts = full.split()
    return f"{' '.join(parts[1:])} {parts[0][0]}." if len(parts) > 1 else full


# ---------- 1. risultati ESPN ----------
def update_results(st, names):
    done = set(st.espn_done)
    today = datetime.datetime.now(datetime.timezone.utc).date()
    results, new = [], 0
    for tour in ("atp", "wta"):
        for d in (today - datetime.timedelta(days=1), today):
            try:
                data = get(ESPN.format(tour=tour, d=d.strftime("%Y%m%d")))
            except Exception as e:
                print(f"  ESPN {tour} {d}: {e}")
                continue
            for ev in data.get("events", []):
                for g in ev.get("groupings", []):
                    for c in g.get("competitions", []):
                        slug = c.get("type", {}).get("slug", "")
                        rnd = (c.get("round") or {}).get("displayName", "")
                        status = c.get("status", {}).get("type", {}).get("name", "")
                        if not slug.endswith("singles") or rnd.startswith("Qualifying"):
                            continue
                        if status not in ("STATUS_FINAL", "STATUS_RETIRED"):
                            continue
                        comp = c.get("competitors", [])
                        if len(comp) != 2 or not any(x.get("winner") for x in comp):
                            continue
                        T = tour.upper()
                        w = next(x for x in comp if x.get("winner"))
                        l = next(x for x in comp if not x.get("winner"))
                        def key(x):
                            a = x.get("athlete", {})
                            return names.find(T, a.get("displayName", "")) or short_key(a.get("displayName", ""), a.get("shortName", ""))
                        wk, lk = key(w), key(l)
                        day = c.get("date", "")[:10]
                        results.append({"id": c.get("id"), "tour": T, "day": day, "w": wk, "l": lk,
                                        "retired": status == "STATUS_RETIRED"})
                        if c.get("id") in done or day <= st.base_date:
                            continue
                        surf = surface_of(st, int(day[5:7]), (c.get("venue") or {}).get("fullName"), ev.get("name"))
                        st.update(T, wk, lk, surf, day)
                        done.add(c.get("id"))
                        new += 1
    st.espn_done = sorted(done)[-5000:]
    print(f"Risultati nuovi elaborati: {new}")
    return results


# ---------- 2-3. quote Unibet e modello ----------

def pkey(full):
    t = norm(full)
    return f"{t[-1]}|{t[0][0]}" if len(t) > 1 else (t[0] if t else "")


# ---------- 1. quote ----------
def snapshot(n_open_keys):
    snap = json.loads(SNAP.read_text()) if SNAP.exists() else {}
    if not os.environ.get("ODDS_API_KEY"):
        print("Chiave ODDS_API_KEY assente")
        return snap
    try:
        keys = sharp.active_keys()
    except Exception as e:
        print("Elenco sport non disponibile:", e)
        return snap
    month = NOW.strftime("%Y-%m")
    remaining = int(snap.get("remaining") or 500) if snap.get("month") == month else max(int(snap.get("remaining") or 0), 500)
    days_left = (datetime.date(NOW.year + NOW.month // 12, NOW.month % 12 + 1, 1) - NOW.date()).days or 1
    reserve = int(n_open_keys * 2 * 24 / SCORES_EVERY_H * min(days_left, 3)) + 10
    per = max(1, len(keys))
    interval = max(MIN_INTERVAL_H, 24 * per * days_left / max(remaining - reserve, 1))
    last = utc(snap["time"]) if snap.get("time") else None
    due = last is None or (NOW - last).total_seconds() / 3600 >= interval or os.environ.get("FORCE_SHARP") == "1"
    print(f"{len(keys)} campionati attivi, richieste rimaste {remaining}, controllo ogni {interval:.1f} h, "
          + ("scarico adesso" if due else f"ultime quote {last.astimezone(PRAGUE):%H:%M}"))
    if not due or remaining - per < 8:
        return snap
    events = []
    for key, label, title in keys:
        try:
            data = sharp.fetch_odds(key)
        except Exception as e:
            print(f"  {key}: {e}")
            continue
        for ev in data:
            out = sharp.analyse(ev)
            if out:
                events.append({"id": ev["id"], "key": key, "sport": label, "league": title, "start": ev["commence_time"],
                               "home": ev["home_team"], "away": ev["away_team"], "outcomes": out})
        remaining = sharp.remaining() or remaining
        print(f"  {title}: {len(data)} eventi")
    snap.update(time=NOW.isoformat(timespec="minutes"), month=month, remaining=remaining, events=events,
                keys=[k for k, _, _ in keys])
    SNAP.write_text(json.dumps(snap, ensure_ascii=False, indent=1))
    return snap


def find_picks(snap):
    picks = []
    for ev in snap.get("events", []):
        if utc(ev["start"]) <= NOW + datetime.timedelta(minutes=5):
            continue
        cand = [o for o in ev["outcomes"] if o["value"] is not None and o["value"] >= SOGLIA
                and ODDS_RANGE[0] <= o["odds"] <= ODDS_RANGE[1]]
        if cand:
            o = max(cand, key=lambda o: o["value"])
            others = [x["name"] for x in ev["outcomes"] if x["name"] != o["name"] and x["name"] != "Draw"]
            picks.append({"id": f'{ev["id"]}|{o["name"]}', "event": ev["id"], "key": ev["key"], "sport": ev["sport"],
                          "league": ev["league"], "start": ev["start"], "pick": o["name"], "opp": ", ".join(others),
                          "home": ev["home"], "away": ev["away"], "odds": o["odds"], "book": o["book"],
                          "p": round(o["p"], 4), "value": round(o["value"], 4)})
    picks.sort(key=lambda p: -p["value"])
    return picks


# ---------- 3. giocate simulate e risultati ----------
def record(bets, picks):
    known = {b["id"] for b in bets}
    new = []
    for p in picks:
        if p["id"] in known:
            continue
        b = dict(p, placed=NOW.isoformat(timespec="minutes"), status="aperta")
        bets.append(b)
        new.append(b)
        print(f"  NUOVA GIOCATA: {p['sport']} {p['pick']} @ {p['odds']} su {p['book']} (valore {p['value']:+.1%})")
    return new


def settle(bets, snap, tennis_results):
    open_b = [b for b in bets if b["status"] == "aperta" and utc(b["start"]) < NOW - datetime.timedelta(hours=2)]
    checked = snap.setdefault("scores_checked", {})
    scores = {}
    for key in sorted({b["key"] for b in open_b if not b["key"].startswith("tennis")}):
        last = checked.get(key)
        if last and (NOW - utc(last)).total_seconds() / 3600 < SCORES_EVERY_H:
            continue
        try:
            scores[key] = sharp.fetch_scores(key)
            checked[key] = NOW.isoformat(timespec="minutes")
            snap["remaining"] = sharp.remaining() or snap.get("remaining")
        except Exception as e:
            print(f"  risultati {key}: {e}")
    for b in open_b:
        winner, void = None, None
        if b["key"].startswith("tennis"):
            pk, ok = pkey(b["pick"]), pkey(b["opp"])
            for r in tennis_results:
                if abs((as_date(r["day"]) - as_date(b["start"])).days) > 2:
                    continue
                if {pkey_short(r["w"]), pkey_short(r["l"])} == {pk, ok}:
                    void = r["retired"]
                    winner = b["pick"] if pkey_short(r["w"]) == pk else b["opp"]
                    break
        else:
            for ev in scores.get(b["key"], []):
                if ev.get("id") != b["event"] or not ev.get("completed") or not ev.get("scores"):
                    continue
                sc = {s["name"]: float(s["score"]) for s in ev["scores"] if s.get("score") not in (None, "")}
                if len(sc) == 2:
                    (n1, s1), (n2, s2) = sc.items()
                    winner = "Draw" if s1 == s2 else (n1 if s1 > s2 else n2)
                break
        if void:
            b.update(status="annullata", note="ritiro")
        elif winner:
            b.update(status="vinta" if winner == b["pick"] else "persa", settled=NOW.isoformat(timespec="minutes"))
        elif (NOW - utc(b["start"])).days > 6:
            b.update(status="annullata", note="risultato non disponibile")


def pkey_short(k):
    """'Sinner J.' -> 'sinner|j' (stesso formato di pkey sui nomi completi)."""
    t = norm(k)
    return f"{' '.join(t[:-1]).split()[-1] if len(t) > 1 else t[0]}|{t[-1][0]}" if t else ""


BANK0 = 200.0   # conto simulato iniziale in euro
STAKE = 0.02    # puntata: 2% del conto del momento


def bankroll(items):
    """items: [(data, quota, esito)] in ordine; esito 1 vinta, 0 persa, None aperta/annullata.
    Ritorna serie del conto, puntate, conto finale."""
    bank, curve, stakes = BANK0, [], []
    for d, q, res in items:
        st = round(bank * STAKE, 2)
        stakes.append(st)
        if res == 1:
            bank += st * (q - 1)
        elif res == 0:
            bank -= st
        if res is not None:
            curve.append((d, round(bank, 2)))
    return curve, stakes, bank


def spark(curve, w=640, h=150):
    """Grafico SVG del conto, con la linea di partenza a 200 €."""
    if len(curve) < 2:
        return '<div class="flat">Il grafico comparirà dopo le prime partite concluse.</div>'
    vals = [BANK0] + [v for _, v in curve]
    lo, hi = min(vals), max(vals)
    pad = (hi - lo) * 0.12 or 10
    lo, hi = lo - pad, hi + pad
    X = lambda i: 8 + (w - 16) * i / (len(vals) - 1)
    Y = lambda v: 8 + (h - 30) * (1 - (v - lo) / (hi - lo))
    pts = " ".join(f"{X(i):.1f},{Y(v):.1f}" for i, v in enumerate(vals))
    area = f"8,{h - 22} " + pts + f" {X(len(vals) - 1):.1f},{h - 22}"
    y0 = Y(BANK0)
    first, last = curve[0][0], curve[-1][0]
    fd = lambda d: f"{d[8:10]}/{d[5:7]}/{d[2:4]}"
    return (f'<svg viewBox="0 0 {w} {h}" class="chart" role="img" aria-label="Andamento del conto">'
            f'<line x1="8" x2="{w - 8}" y1="{y0:.1f}" y2="{y0:.1f}" class="base"/>'
            f'<text x="{w - 8}" y="{y0 - 5:.1f}" text-anchor="end" class="ax">200 €</text>'
            f'<polygon points="{area}" class="area"/><polyline points="{pts}" class="ln"/>'
            f'<circle cx="{X(len(vals) - 1):.1f}" cy="{Y(vals[-1]):.1f}" r="4.5" class="dot"/>'
            f'<text x="8" y="{h - 6}" class="ax">{fd(first)}</text><text x="{w - 8}" y="{h - 6}" text-anchor="end" class="ax">{fd(last)}</text></svg>')




# ---------- 4. pagina ----------
def build_page(snap, picks, bets, bt):
    now = NOW.astimezone(PRAGUE)
    esc = html.escape
    def t(iso):
        dt = utc(iso).astimezone(PRAGUE)
        day = "oggi" if dt.date() == now.date() else "domani" if dt.date() == now.date() + datetime.timedelta(days=1) else dt.strftime("%d/%m")
        return f"{day} {dt.strftime('%H:%M')}"
    pct = lambda x: f"{x * 100:.0f}%"
    num = lambda x, d=2: f"{x:,.{d}f}".replace(",", " ").replace(".", ",")
    eur = lambda x: ("−" if x < 0 else "") + num(abs(x)) + " €"
    nm = lambda n: "Pareggio" if n == "Draw" else n

    tips = "".join(
        f'<li class="tip"><span class="no">{i}</span>'
        f'<div class="who"><span class="sp">{ICON.get(p["sport"], "")} {esc(p["sport"])} · {esc(p["league"])}</span>'
        f'<span class="cap">punta su</span><span class="pn">{esc(nm(p["pick"]))}</span>'
        f'<span class="vs">{"vs " + esc(p["opp"]) if p["opp"] else ""}</span>'
        f'<span class="tn">{t(p["start"])} · gioca su <b>{esc(p["book"])}</b> solo se la quota è almeno <b>{num(1 / p["p"])}</b></span></div>'
        f'<div class="fig"><span class="big">{pct(p["p"])}</span><span class="cap">vittoria</span></div>'
        f'<div class="fig"><span class="big q">{num(p["odds"])}</span><span class="cap">quota</span></div></li>'
        for i, p in enumerate(picks, 1))
    if not tips:
        tips = ('<li class="nothing">Adesso nessuna partita dove un bookmaker paga più del giusto. '
                'Quando ce ne sarà una comparirà qui e ti arriverà l\'email.</li>')

    upcoming = sorted([e for e in snap.get("events", []) if utc(e["start"]) > NOW], key=lambda e: e["start"])
    allrows = []
    for e in upcoming:
        outs = e["outcomes"]
        allrows.append(
            f'<tr><td class="mono">{t(e["start"])}</td><td><span class="dim">{ICON.get(e["sport"], "")} {esc(e["league"])}</span><br>'
            + "<br>".join(esc(nm(o["name"])) for o in outs) + '</td><td class="r mono"><br>'
            + "<br>".join((num(o["odds"]) + f' <span class="dim">{esc(o["book"])}</span>') if o["odds"] else "—" for o in outs)
            + '</td><td class="r mono"><br>' + "<br>".join(pct(o["p"]) for o in outs) + '</td></tr>')

    live = sorted([b for b in bets if b["status"] != "annullata"], key=lambda b: b["start"])
    lcurve, lstakes, lbank = bankroll([(b["start"][:10], b["odds"], 1 if b["status"] == "vinta" else 0 if b["status"] == "persa" else None) for b in live])
    lrows = []
    for b, st in sorted(zip(live, lstakes), key=lambda x: x[0]["start"], reverse=True)[:50]:
        if b["status"] == "aperta":
            res, cls = "in attesa", "wait"
        elif b["status"] == "vinta":
            res, cls = "+" + eur(st * (b["odds"] - 1)), "win"
        else:
            res, cls = "−" + eur(st), "lose"
        lrows.append(f'<tr><td class="mono">{t(b["start"])}</td><td>{ICON.get(b["sport"], "")} <b>{esc(nm(b["pick"]))}</b> '
                     f'<span class="dim">{("vs " + esc(b["opp"])) if b["opp"] else ""} · {esc(b["book"])}</span></td>'
                     f'<td class="r mono">{num(b["odds"])}</td><td class="r mono">{eur(st)}</td><td class="r mono {cls}">{res}</td></tr>')
    lclosed = [b for b in live if b["status"] in ("vinta", "persa")]
    lwon = sum(b["status"] == "vinta" for b in lclosed)

    pb = bt.get("bets_sharp", [])
    pcurve, pstakes, pbank = bankroll([(r[0], r[5], r[7]) for r in pb])
    prows = "".join(
        f'<tr><td class="mono">{r[0][8:10]}/{r[0][5:7]}/{r[0][2:4]}</td><td><b>{esc(r[3])}</b> <span class="dim">vs {esc(r[4])}</span></td>'
        f'<td class="r mono">{num(r[5])}</td><td class="r mono">{eur(st)}</td>'
        f'<td class="r mono {"win" if r[7] else "lose"}">{("+" + eur(st * (r[5] - 1))) if r[7] else ("−" + eur(st))}</td></tr>'
        for r, st in list(zip(pb, pstakes))[::-1][:30])
    pwon = sum(r[7] for r in pb)

    def head(bank, n, won, pend=None):
        ch = bank - BANK0
        extra = f'<div><span class="k">In attesa</span><span class="v">{pend}</span></div>' if pend is not None else ""
        return (f'<div class="bank"><div><span class="k">Conto</span><span class="bal">{eur(bank)}</span>'
                f'<span class="chg {"win" if ch >= 0 else "lose"}">{"+" if ch >= 0 else "−"}{eur(abs(ch))} · {"+" if ch >= 0 else "−"}{abs(ch) / BANK0 * 100:.1f}%</span></div>'
                f'<div class="stats"><div><span class="k">Giocate</span><span class="v">{n}</span></div>'
                f'<div><span class="k">Vinte</span><span class="v">{won}{f" · {won / n * 100:.0f}%" if n else ""}</span></div>{extra}</div></div>')

    qt = utc(snap["time"]).astimezone(PRAGUE).strftime("%d/%m %H:%M") if snap.get("time") else "—"
    vals = {
        "updated": now.strftime("%d/%m %H:%M"), "oddstime": qt, "ntips": str(len(picks)), "tips": tips,
        "nall": str(len(upcoming)), "allrows": "".join(allrows) or '<tr><td colspan="4" class="dim">Nessun evento in programma.</td></tr>',
        "livehead": head(lbank, len(lclosed), lwon, len(live) - len(lclosed)), "livechart": spark(lcurve),
        "liverows": "".join(lrows) or '<tr><td colspan="5" class="dim">Le prime giocate compariranno qui.</td></tr>',
        "livestart": (live[0]["start"][8:10] + "/" + live[0]["start"][5:7]) if live else now.strftime("%d/%m"),
        "pasthead": head(pbank, len(pb), pwon), "pastchart": spark(pcurve), "pastrows": prows,
        "pastrange": (f'{pb[0][0][8:10]}/{pb[0][0][5:7]}/{pb[0][0][:4]} – {pb[-1][0][8:10]}/{pb[-1][0][5:7]}/{pb[-1][0][:4]}' if pb else ""),
        "books": ", ".join(sharp.SOFT.values()),
    }
    page = (HERE / "page.html").read_text(encoding="utf-8")
    for k, v in vals.items():
        page = page.replace("%%" + k + "%%", v)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(page, encoding="utf-8")


def main():
    raw = json.loads(STATE.read_text())
    st = State.from_json(raw)
    st.surfaces, st.espn_done = raw.get("surfaces", {}), raw.get("espn_done", [])
    st.base_date = raw.get("base_date") or raw["last_date"]
    bets = json.loads(BETS.read_text()) if BETS.exists() else []
    bt = json.loads(BT.read_text())
    names = Names(list(st.elo.keys()))
    try:
        tennis_results = update_results(st, names)
    except Exception as e:
        print("Risultati tennis non disponibili:", e)
        tennis_results = []
    open_keys = {b["key"] for b in bets if b["status"] == "aperta" and not b["key"].startswith("tennis")}
    snap = snapshot(len(open_keys))
    picks = find_picks(snap)
    new = record(bets, picks)
    settle(bets, snap, tennis_results)
    if new:
        notify.send_new_picks(new)
    SNAP.write_text(json.dumps(snap, ensure_ascii=False, indent=1))
    out = st.to_json()
    out.update(surfaces=st.surfaces, espn_done=st.espn_done, base_date=st.base_date)
    STATE.write_text(json.dumps(out, separators=(",", ":")))
    BETS.write_text(json.dumps(bets, ensure_ascii=False, indent=1))
    build_page(snap, picks, bets, bt)
    print(f"Da giocare: {len(picks)} · pagina aggiornata")


if __name__ == "__main__":
    main()
