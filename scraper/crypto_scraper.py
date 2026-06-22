#!/usr/bin/env python3
"""Crypto news scraper: CoinGecko prices + free RSS feeds."""

import requests
import xml.etree.ElementTree as ET
from datetime import datetime
import json

HEADERS = {
    "User-Agent": "AI-News-Dashboard/1.0 (Daily digest; bot)"
}

def get_crypto_prices():
    """Top 10 crypto prices via CoinGecko (free, no key needed)."""
    try:
        url = "https://api.coingecko.com/api/v3/coins/markets"
        params = {
            "vs_currency": "usd",
            "order": "market_cap_desc",
            "per_page": 10,
            "page": 1,
            "sparkline": "false",
            "price_change_percentage": "24h"
        }
        r = requests.get(url, params=params, headers=HEADERS, timeout=20)
        r.raise_for_status()
        data = r.json()
        coins = []
        for coin in data:
            change = coin.get("price_change_percentage_24h_in_currency") or coin.get("price_change_percentage_24h") or 0
            coins.append({
                "name": coin["name"],
                "symbol": coin["symbol"].upper(),
                "price": coin["current_price"],
                "change_24h": round(change, 2),
                "market_cap": coin.get("market_cap", 0)
            })
        return coins
    except Exception as e:
        print(f"      CoinGecko error: {e}")
        return []

def get_crypto_news():
    """Crypto news via Cointelegraph RSS (free, no key)."""
    feeds = [
        "https://cointelegraph.com/rss",
        "https://coindesk.com/arc/outboundfeeds/rss/",
    ]
    news = []
    for feed_url in feeds:
        try:
            r = requests.get(feed_url, headers=HEADERS, timeout=15)
            r.raise_for_status()
            root = ET.fromstring(r.content)
            items = root.findall(".//item")
            for item in items[:8]:
                title = item.findtext("title", "")
                link = item.findtext("link", "")
                pub = item.findtext("pubDate", "")
                desc = item.findtext("description", "")[:250]
                news.append({
                    "title": title.strip(),
                    "url": link.strip(),
                    "published": pub.strip()[:17],
                    "description": desc.strip()
                })
        except Exception as e:
            print(f"      Crypto RSS {feed_url} failed: {e}")
            continue
    # Deduplicate by title
    seen = set()
    uniq = []
    for n in news:
        if n["title"] not in seen and n["title"]:
            seen.add(n["title"])
            uniq.append(n)
    return uniq[:12]

def get_crypto_data(file_path=None):
    """Master entry: prices + news."""
    print("[ ] Fetching crypto prices & news...")
    crypto_data = {
        "timestamp": datetime.utcnow().isoformat(),
        "prices": get_crypto_prices(),
        "news": get_crypto_news()
    }
    if file_path:
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(crypto_data, f, indent=2, ensure_ascii=False)
    return crypto_data


if __name__ == "__main__":
    data = get_crypto_data()
    print(f"Coins: {len(data['prices'])}, News: {len(data['news'])}")
