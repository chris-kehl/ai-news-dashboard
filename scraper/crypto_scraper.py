#!/usr/bin/env python3
"""Crypto news scraper: CoinGecko prices + free RSS feeds."""

import requests
import xml.etree.ElementTree as ET
from datetime import datetime
import json
import time
from scraper_utils import fetch_with_retry, load_scraper_cache, save_scraper_cache

HEADERS = {
    "User-Agent": "AI-News-Dashboard/1.0 (Daily digest; bot)"
}

def get_crypto_prices():
    """Top 10 crypto prices via CoinGecko (free, no key needed) + TAO."""
    cached = load_scraper_cache("crypto_prices", max_age_minutes=10)
    if cached:
        print("      Using cached crypto prices")
        return cached
    try:
        # Top 10 by market cap + TAO explicitly
        url = "https://api.coingecko.com/api/v3/coins/markets"
        params = {
            "vs_currency": "usd",
            "order": "market_cap_desc",
            "per_page": 10,
            "page": 1,
            "sparkline": "false",
            "price_change_percentage": "24h"
        }
        r = fetch_with_retry(url, params=params, headers=HEADERS, timeout=20, max_retries=3, backoff_base=3.0, retry_codes=(429, 403, 502, 503))
        if r is None:
            return []
        data = r.json()
        coins = []
        tao_included = False
        for coin in data:
            change = coin.get("price_change_percentage_24h_in_currency") or coin.get("price_change_percentage_24h") or 0
            sym = coin["symbol"].upper()
            if sym == "TAO":
                tao_included = True
            coins.append({
                "name": coin["name"],
                "symbol": sym,
                "price": coin["current_price"],
                "change_24h": round(change, 2),
                "market_cap": coin.get("market_cap", 0)
            })
        # Explicit TAO fetch if not in top 10
        if not tao_included:
            try:
                tao_url = "https://api.coingecko.com/api/v3/coins/markets"
                tao_params = {
                    "vs_currency": "usd",
                    "ids": "bittensor",
                    "sparkline": "false",
                    "price_change_percentage": "24h"
                }
                tao_r = fetch_with_retry(tao_url, params=tao_params, headers=HEADERS, timeout=15, max_retries=2, backoff_base=3.0)
                if tao_r:
                    tao_data = tao_r.json()
                    for coin in tao_data:
                        change = coin.get("price_change_percentage_24h_in_currency") or coin.get("price_change_percentage_24h") or 0
                        coins.insert(0, {
                            "name": coin["name"],
                            "symbol": coin["symbol"].upper(),
                            "price": coin["current_price"],
                            "change_24h": round(change, 2),
                            "market_cap": coin.get("market_cap", 0)
                        })
            except Exception as e:
                print(f"      TAO explicit fetch error: {e}")
        if coins:
            save_scraper_cache("crypto_prices", coins)
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
            r = fetch_with_retry(feed_url, headers=HEADERS, timeout=15, max_retries=2, backoff_base=2.0, retry_codes=(429, 403, 502))
            if r is None:
                continue
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
    """Master entry: prices + news + DDG fallback if RSS empty."""
    print("[ ] Fetching crypto prices & news...")
    prices = get_crypto_prices()
    news = get_crypto_news()
    # If RSS returned nothing after 2 feeds, hit DDG news for 8 items
    if not news:
        try:
            from ddg_scraper import ddg_crypto_news
            print("      RSS empty — falling back to DDG crypto news")
            news = ddg_crypto_news(max_results=8)
        except Exception as e:
            print(f"      DDG crypto fallback failed: {e}")
    crypto_data = {
        "timestamp": datetime.utcnow().isoformat(),
        "prices": prices,
        "news": news
    }
    if file_path:
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(crypto_data, f, indent=2, ensure_ascii=False)
    return crypto_data


if __name__ == "__main__":
    data = get_crypto_data()
    print(f"Coins: {len(data['prices'])}, News: {len(data['news'])}")
