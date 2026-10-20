"""
Email con le nuove partite da giocare, inviata dal tuo Gmail a te stesso.
Secrets necessari: GMAIL_USER (indirizzo Gmail) e GMAIL_APP_PASSWORD (password per le app di Google,
non la password normale). Se mancano, il robot non invia nulla.
"""
import datetime, html, os, smtplib, ssl, zoneinfo
from email.mime.text import MIMEText

PRAGUE = zoneinfo.ZoneInfo("Europe/Prague")
PAGE = "https://anomaly73bit.github.io/radar-tennis/"


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
    rows = "".join(
        f'<tr><td style="padding:10px 12px;border-bottom:1px solid #2b5d93"><div style="font:700 20px Arial,sans-serif;color:#e3f25a">{i}. {html.escape(b["pick"])}</div>'
        f'<div style="font:14px Arial,sans-serif;color:#cfdbe6">vs {html.escape(b["opp"])} · {html.escape(b["tournament"])} · {when(b["start"])}</div></td>'
        f'<td style="padding:10px 12px;border-bottom:1px solid #2b5d93;text-align:right;font:14px Arial,sans-serif;color:#ffffff;white-space:nowrap">'
        f'<b style="font-size:20px">{b["odds"]:.2f}</b> quota<br>{b["pmodel"] * 100:.0f}% vittoria</td></tr>'.replace(".", ",", 1)
        for i, b in enumerate(new_bets, 1))
    body = (f'<div style="background:#15372a;padding:20px"><div style="max-width:560px;margin:0 auto;background:#1d4b80;border:2px solid #eef3ee;border-radius:3px">'
            f'<div style="padding:14px 12px;font:800 24px Arial,sans-serif;color:#ffffff;text-transform:uppercase">Radar Tennis · da giocare</div>'
            f'<table style="width:100%;border-collapse:collapse">{rows}</table>'
            f'<div style="padding:12px;font:13px Arial,sans-serif"><a style="color:#e3f25a" href="{PAGE}">Apri la pagina</a></div></div></div>')
    names = ", ".join(b["pick"] for b in new_bets[:3]) + ("…" if len(new_bets) > 3 else "")
    msg = MIMEText(body, "html", "utf-8")
    msg["Subject"] = f"🎾 Da giocare: {names}"
    msg["From"] = f"Radar Tennis <{user}>"
    msg["To"] = user
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=ssl.create_default_context(), timeout=30) as s:
            s.login(user, pwd)
            s.send_message(msg)
        print(f"Email inviata: {len(new_bets)} partite")
    except Exception as e:
        print("Email non inviata:", e)
