"""
Email con le nuove partite da giocare, inviata dal tuo Gmail a te stesso.
Secrets necessari: GMAIL_USER (indirizzo Gmail) e GMAIL_APP_PASSWORD (password per le app di Google,
non la password normale). Se mancano, il robot non invia nulla.
"""
import datetime, html, os, smtplib, ssl, zoneinfo
from email.mime.text import MIMEText

PRAGUE = zoneinfo.ZoneInfo("Europe/Prague")
PAGE = "https://anomaly73bit.github.io/radar-tennis/"
ICON = {"Tennis": "🎾", "MMA": "🥊", "Pugilato": "🥊", "Basket": "🏀", "Hockey": "🏒"}


def send_new_picks(new_bets):
    user = os.environ.get("GMAIL_USER", "").strip()
    pwd = os.environ.get("GMAIL_APP_PASSWORD", "").replace(" ", "").strip()
    if not new_bets:
        return
    if not user or not pwd:
        print("Email: Secrets GMAIL_USER / GMAIL_APP_PASSWORD assenti, non invio")
        return
    def when(iso):
        return datetime.datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(PRAGUE).strftime("%d/%m alle %H:%M")
    def fmt(x):
        return f"{x:.2f}".replace(".", ",")
    rows = ""
    for i, b in enumerate(new_bets, 1):
        pick = "Pareggio" if b["pick"] == "Draw" else b["pick"]
        p = b.get("p", b.get("pmodel", 0))
        minq = 1 / p if p else 0
        match = f'{b.get("home", pick)} – {b.get("away", b.get("opp", ""))}' if b.get("home") else f'{pick} – {b.get("opp", "")}'
        rows += (
            f'<tr><td style="padding:14px 12px;border-bottom:1px solid #2b5d93;font-family:Arial,sans-serif">'
            f'<div style="font-size:13px;color:#cfdbe6">{i}. {ICON.get(b.get("sport"), "")} {html.escape(b.get("league", ""))} · {when(b["start"])}</div>'
            f'<div style="font-size:14px;color:#cfdbe6">{html.escape(match)}</div>'
            f'<div style="font-size:22px;font-weight:700;color:#e3f25a;margin:6px 0">PUNTA SU: {html.escape(pick)}</div>'
            f'<div style="font-size:15px;color:#ffffff">su <b>{html.escape(b.get("book", "Unibet"))}</b> a quota <b>{fmt(b["odds"])}</b></div>'
            f'<div style="font-size:14px;color:#ffffff;margin-top:4px">Gioca solo se la quota è <b>almeno {fmt(minq)}</b>. Sotto, non conviene.</div>'
            f'<div style="font-size:13px;color:#cfdbe6;margin-top:4px">Probabilità vera di vittoria: {p * 100:.0f}%</div></td></tr>')
    names = ", ".join(b["pick"] for b in new_bets[:3]) + ("…" if len(new_bets) > 3 else "")
    msg = MIMEText(body, "html", "utf-8")
    msg["Subject"] = f"Da giocare: {names}"
    msg["From"] = f"Radar Scommesse <{user}>"
    msg["To"] = user
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=ssl.create_default_context(), timeout=30) as s:
            s.login(user, pwd)
            s.send_message(msg)
        print(f"Email inviata: {len(new_bets)} partite")
    except Exception as e:
        print("Email non inviata:", e)
