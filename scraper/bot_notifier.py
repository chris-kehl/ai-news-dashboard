#!/usr/bin/env python3
"""Bot notifications for Telegram and Discord."""

import os
import json
import requests
from datetime import datetime

def telegram_send(msg, bot_token=None, chat_id=None):
    """Send a Telegram message."""
    token = bot_token or os.getenv("TELEGRAM_BOT_TOKEN")
    chat = chat_id or os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat:
        print("[bots] No Telegram credentials, skipping")
        return False

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat,
        "text": msg,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    try:
        r = requests.post(url, json=payload, timeout=15)
        r.raise_for_status()
        print("[bots] Telegram sent")
        return True
    except Exception as e:
        print(f"[bots] Telegram error: {e}")
        return False

def discord_send(msg, webhook_url=None):
    """Send a Discord message via webhook."""
    url = webhook_url or os.getenv("DISCORD_WEBHOOK_URL")
    if not url:
        print("[bots] No Discord webhook, skipping")
        return False

    payload = {"content": msg}
    try:
        r = requests.post(url, json=payload, timeout=15)
        r.raise_for_status()
        print("[bots] Discord sent")
        return True
    except Exception as e:
        print(f"[bots] Discord error: {e}")
        return False

def build_digest(data):
    """Build a compact digest string for bots."""
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = [f"<b>AI News — {ts}</b>"]

    summary = data.get("summary", "")
    if summary:
        # Keep first 2 sentences or 200 chars
        brief = summary[:200].replace("\n", " ") + "..."
        lines.append(f"\n<b>Summary:</b> {brief}")

    sigs = data.get("signals", [])
    if sigs:
        lines.append("\n<b>Signals:</b>")
        for s in sigs[:4]:
            emoji = {"buy": "🟢", "sell": "🔴", "watch": "🟡"}.get(s["type"], "⚪")
            lines.append(f"{emoji} {s['text']}")

    reddit = data.get("reddit", [])
    if reddit:
        lines.append("\n<b>Reddit Top 3:</b>")
        for p in reddit[:3]:
            lines.append(f"• {p['title'][:70]} (r/{p['subreddit']})")

    b = data.get("bittensor", {})
    if b:
        price = b.get("price", 0)
        change = b.get("price_change_24h", 0)
        emoji = "📈" if change >= 0 else "📉"
        lines.append(f"\n<b>TAO:</b> ${price:.2f} {emoji} {change:+.1f}%")

    lines.append(f"\n<a href=\"https://YOURUSERNAME.github.io/ai-news-dashboard\">Open Dashboard</a>")
    return "\n".join(lines)

def notify_all(data_path="data.json"):
    """Send to all configured bots."""
    try:
        with open(data_path) as f:
            data = json.load(f)
    except Exception as e:
        print(f"[bots] Failed to load data.json: {e}")
        return False

    msg = build_digest(data)

    sent = False
    if telegram_send(msg):
        sent = True
    if discord_send(msg):
        sent = True
    return sent

if __name__ == "__main__":
    import sys
    path = sys.argv[1] if len(sys.argv) > 1 else "../data.json"
    ok = notify_all(path)
    sys.exit(0 if ok else 1)
