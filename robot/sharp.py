"""
Quote da The Odds API (https://the-odds-api.com). Chiave nel Secret ODDS_API_KEY.

Quota "giusta": media delle quote sharp (Pinnacle conta doppio, poi Betfair Exchange e Matchbook)
dopo aver tolto il margine. Quota da giocare: la migliore tra i bookmaker scelti.
Costo: 1 richiesta per campionato/torneo a ogni controllo (fino a 10 bookmaker = 1 regione);
l'elenco degli sport e' gratuito; i risultati costano 2 richieste per campionato.
"""
import json, os, urllib.error, urllib.parse, urllib.request

BASE = "https://api.the-odds-api.com/v4"
SHARP = ["pinnacle", "betfair_ex_eu", "matchbook"]
SOFT = {"unibet_nl": "Unibet", "betsson": "Betsson", "nordicbet": "NordicBet",
        "williamhill": "William Hill", "sport888": "888sport"}

# sport scelti: gruppo o chiave della The Odds API -> etichetta
SPORTS = [
    ("Tennis", lambda k: k.startswith("tennis_atp") or k.startswith("tennis_wta"), "Tennis"),
    ("Mixed Martial Arts", lambda k: True, "MMA"),
    ("Boxing", lambda k: True, "Pugilato"),
    ("Basketball", lambda k: k in ("basketball_nba", "basketball_euroleague"), "Basket"),
    ("Ice Hockey", lambda k: k == "icehockey_nhl", "Hockey"),
]

LAST_HEADERS = {}


def _get(path, params):
    params = dict(params, apiKey=os.environ["ODDS_API_KEY"].strip())
    url = f"{BASE}{path}?{urllib.parse.urlencode(params)}"
    with urllib.request.urlopen(urllib.request.Request(url, headers={"Accept": "application/json"}), timeout=30) as r:
        LAST_HEADERS.clear()
        LAST_HEADERS.update({k.lower(): v for k, v in r.headers.items()})
        return json.loads(r.read())


def active_keys():
    """[(chiave, etichetta sport, titolo)] dei campionati attivi tra quelli scelti (gratuito)."""
    out = []
    for s in _get("/sports", {}):
        for group, ok, label in SPORTS:
            if s.get("group") == group and s.get("active") and ok(s["key"]) and not s.get("has_outrights"):
                out.append((s["key"], label, s.get("title", s["key"])))
    return out


def fetch_odds(key):
    return _get(f"/sports/{key}/odds", {"markets": "h2h", "oddsFormat": "decimal", "dateFormat": "iso",
                                       "bookmakers": ",".join(SHARP + list(SOFT))})


def fetch_scores(key):
    return _get(f"/sports/{key}/scores", {"daysFrom": 3, "dateFormat": "iso"})


def remaining():
    v = LAST_HEADERS.get("x-requests-remaining")
    return int(float(v)) if v is not None else None


def analyse(ev):
    """Per ogni esito: probabilita' giusta e migliore quota tra i bookmaker scelti.
    Ritorna lista di dict {name, p, odds, book, value} oppure [] se mancano le quote sharp."""
    def h2h(b):
        m = next((m for m in b.get("markets", []) if m["key"] == "h2h"), None)
        return {o["name"]: o["price"] for o in m["outcomes"]} if m else None
    names, probs, weights, srcs = None, [], [], []
    for b in ev.get("bookmakers", []):
        if b["key"] not in SHARP:
            continue
        o = h2h(b)
        if not o or len(o) < 2:
            continue
        if names is None:
            names = sorted(o)
        if sorted(o) != names:
            continue
        inv = {k: 1 / v for k, v in o.items()}
        tot = sum(inv.values())
        if not (0.99 <= tot <= 1.09):      # quote non credibili (mercato senza liquidita' o errore)
            continue
        probs.append({k: v / tot for k, v in inv.items()})
        weights.append(2 if b["key"] == "pinnacle" else 1)
        srcs.append(b["key"])
    if not probs:
        return []
    # serve Pinnacle, oppure almeno due fonti sharp che concordano
    if "pinnacle" not in srcs:
        if len(probs) < 2 or max(abs(probs[0][k] - probs[1][k]) for k in names) > 0.04:
            return []
    fair = {k: sum(p[k] * w for p, w in zip(probs, weights)) / sum(weights) for k in names}
    best = {k: (None, None) for k in names}
    for b in ev.get("bookmakers", []):
        if b["key"] not in SOFT:
            continue
        o = h2h(b)
        if not o or sorted(o) != names:
            continue
        for k, v in o.items():
            if best[k][0] is None or v > best[k][0]:
                best[k] = (v, SOFT[b["key"]])
    out = []
    for k in names:
        q, book = best[k]
        v = (fair[k] * q - 1) if q else None
        if v is not None and v > 0.20:     # differenza troppo grande: quasi certamente un errore di dati
            v = None
        out.append({"name": k, "p": fair[k], "odds": q, "book": book, "value": v})
    return out
