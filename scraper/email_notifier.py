#!/usr/bin/env python3
"""Email notifications using SMTP (Gmail, iCloud, Outlook, etc)."""

import os
import smtplib
import json
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

EMAIL_CONFIG = {
    "smtp_server": os.getenv("SMTP_SERVER", "smtp.gmail.com"),
    "smtp_port": int(os.getenv("SMTP_PORT", "587")),
    "username": os.getenv("EMAIL_USERNAME", ""),
    "password": os.getenv("EMAIL_PASSWORD", ""),      # app-specific password
    "from_addr": os.getenv("EMAIL_FROM", ""),
    "to_addr": os.getenv("EMAIL_TO", ""),
}

def send_email(subject, body_html, body_text=""):
    """Send email notification."""
    cfg = EMAIL_CONFIG
    if not cfg["username"] or not cfg["password"]:
        print("[email] No SMTP credentials in .env, skipping email")
        return False

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = cfg["from_addr"] or cfg["username"]
    msg["To"] = cfg["to_addr"] or cfg["username"]

    msg.attach(MIMEText(body_text or body_html, "plain"))
    msg.attach(MIMEText(body_html, "html"))

    try:
        server = smtplib.SMTP(cfg["smtp_server"], cfg["smtp_port"])
        server.starttls()
        server.login(cfg["username"], cfg["password"])
        server.send_message(msg)
        server.quit()
        print(f"[email] Sent: {subject}")
        return True
    except Exception as e:
        print(f"[email] Error sending: {e}")
        return False

def notify_update(data_path="data.json"):
    """Send daily summary email from generated data.json."""
    try:
        with open(data_path) as f:
            data = json.load(f)
    except Exception:
        return False

    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    subject = f"AI News Update — {ts}"

    # Plain text summary
    lines = [f"AI News Dashboard Update ({ts})", "=" * 40]
    lines.append(data.get("summary", "No summary."))
    lines.append("")
    lines.append("Signals:")
    for sig in data.get("signals", []):
        lines.append(f"  [{sig['type'].upper()}] {sig['text']}")
    lines.append("")
    lines.append("Reddit Top 3:")
    for p in data.get("reddit", [])[:3]:
        lines.append(f"  • {p['title'][:70]} (r/{p['subreddit']})")
    lines.append("")
    b = data.get("bittensor", {})
    lines.append(f"TAO: ${b.get('price', 0):.2f} ({b.get('price_change_24h', 0):+.1f}%)")
    body_text = "\n".join(lines)

    # HTML version
    html_signals = " ".join(
        f'<span style="padding:4px 10px;border-radius:6px;font-size:0.85em;font-weight:600;text-transform:uppercase;'
        f'background:{"#00d4aa22" if s["type"]=="buy" else "#ff475722" if s["type"]=="sell" else "#ffa50222"};'
        f'color:{"#00d4aa" if s["type"]=="buy" else "#ff4757" if s["type"]=="sell" else "#ffa502"};">'
        f'{s["type"].upper()} {s["text"]}</span>'
        for s in data.get("signals", [])
    )

    reddit_html = "\n".join(
        f'<li><a href="{p["url"]}" style="color:#e0e0e0;text-decoration:none;">{p["title"][:80]}</a> '
        f'<span style="color:#888;font-size:0.8em;">r/{p["subreddit"]} ▲{p["score"]}</span></li>'
        for p in data.get("reddit", [])[:5]
    )

    body_html = f"""\
<html><body style="background:#0a0a0f;color:#e0e0e0;font-family:sans-serif;padding:20px;">
<h2 style="color:#00d4aa;">AI News Dashboard — {ts}</h2>
<div style="background:#12121a;border:1px solid #2a2a3a;border-radius:8px;padding:16px;margin:12px 0;">
<p style="line-height:1.7;">{data.get('summary','No summary.').replace(chr(10),'<br>')}</p>
</div>
<div style="margin:12px 0;">{html_signals}</div>
<h3 style="color:#888;border-bottom:1px solid #2a2a3a;padding-bottom:6px;">Reddit Top 5</h3>
<ul style="line-height:1.8;padding-left:18px;">{reddit_html}</ul>
<p style="color:#666;font-size:0.8em;margin-top:20px;">
TAO: <strong style="color:#00d4aa;">${b.get('price',0):.2f}</strong> ({b.get('price_change_24h',0):+.1f}%) &bull;
Subnets: {b.get('active_subnets',0)} &bull; Miners: {b.get('total_miners',0)}
</p>
<p style="color:#555;font-size:0.75em;"><a href="https://YOURUSERNAME.github.io/ai-news-dashboard" style="color:#00d4aa;">Open Dashboard →</a></p>
</body></html>
"""

    return send_email(subject, body_html, body_text)

if __name__ == "__main__":
    import sys
    path = sys.argv[1] if len(sys.argv) > 1 else "../data.json"
    ok = notify_update(path)
    sys.exit(0 if ok else 1)
