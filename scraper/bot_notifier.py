#!/usr/bin/env python3
"""Bot notifications for Telegram and Discord with signal filtering."""
import os, json, requests
from datetime import datetime

def telegram_send(msg, bot_token=None, chat_id=None):
    token = bot_token or os.getenv("TELEGRAM_BOT_TOKEN")
    chat = chat_id or os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat:
        return False
    try:
        r = requests.post(f"https://api.telegram.org/bot{token}/sendMessage", json={
            "chat_id": chat, "text": msg, "parse_mode": "HTML", "disable_web_page_preview": True
        }, timeout=15)
        r.raise_for_status()
        print("[bots] Telegram sent")
        return True
    except Exception as e:
        print(f"[bots] Telegram error: {e}")
        return False

def discord_send(msg, webhook_url=None):
    url = webhook_url or os.getenv("DISCORD_WEBHOOK_URL")
    if not url:
        return False
    try:
        r = requests.post(url, json={"content": msg}, timeout=15)
        r.raise_for_status()
        print("[bots] Discord sent")
        return True
    except Exception as e:
        print(f"[bots] Discord error: {e}")
        return False

def build_digest(data, high_priority_only=False):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = [f"<b>AI News — {ts}</b>"]
    summary = data.get("summary", "")
    if summary:
        lines.append(f"\n<b>Summary:</b> {summary[:200].replace(chr(10), ' ')}...")
    sigs = data.get("signals", [])
    if sigs:
        lines.append("\n<b>Signals:</b>")
        for s in sigs[:4]:
            emoji = {"buy": "🟢", "sell": "🔴", "watch": "🟡"}.get(s["type"], "⚪")
            lines.append(f"{emoji} {s['text']}")
    defense = data.get("defense", [])
    escalation_keywords = ["war", "attack", "strike", "invasion", "escalation", "missile", "drone", "casualties", "killed", "destroyed"]
    escalations = [d["title"][:70] for d in defense[:5] if any(k in d.get("title", "").lower() for k in escalation_keywords)]
    if escalations:
        lines.append("\n<b>🚨 Defense Alerts:</b>")
        for e in escalations[:2]:
            lines.append(f"⚠️ {e}...")
    if not high_priority_only:
        reddit = data.get("reddit", [])
        if reddit:
            lines.append("\n<b>Reddit Top 3:</b>")
            for p in reddit[:3]:
                lines.append(f"• {p['title'][:70]} (r/{p['subreddit']})")
        b = data.get("bittensor", {})
        if b:
            price, change = b.get("price", 0), b.get("price_change_24h", 0)
            emoji = "📈" if change >= 0 else "📉"
            lines.append(f"\n<b>TAO:</b> ${price:.2f} {emoji} {change:+.1f}%")
    lines.append(f'\n<a href="https://chris-kehl.github.io/ai-news-dashboard">Open Dashboard</a>')
    return "\n".join(lines)

def notify_all(data_path="data.json"):
    try:
        with open(data_path) as f:
            data = json.load(f)
    except Exception as e:
        print(f"[bots] Failed to load data.json: {e}")
        return False
    msg = build_digest(data, high_priority_only=False)
    return telegram_send(msg) or discord_send(msg)

def notify_high_priority(data_path="data.json"):
    try:
        with open(data_path) as f:
            data = json.load(f)
    except Exception as e:
        print(f"[bots] Failed to load data.json: {e}")
        return False
    sigs = data.get("signals", [])
    buy_sell = [s for s in sigs if s["type"] in ("buy", "sell")]
    defense = data.get("defense", [])
    escalation_keywords = ["war", "attack", "strike", "invasion", "escalation", "missile", "drone", "casualties", "killed", "destroyed"]
    has_escalation = any(any(k in d.get("title", "").lower() for k in escalation_keywords) for d in defense[:5])
    if not buy_sell and not has_escalation:
        print("[bots] No high-priority alerts. Skipping notification.")
        return False
    print(f"[bots] Found {len(buy_sell)} buy/sell signals, escalation={has_escalation}")
    msg = build_digest(data, high_priority_only=True)
    return telegram_send(msg) or discord_send(msg)

if __name__ == "__main__":
    import sys
    path = sys.argv[1] if len(sys.argv) > 1 else "../data.json"
    ok = notify_high_priority(path) if "--priority-only" in sys.argv else notify_all(path)
    sys.exit(0 if ok else 1)
