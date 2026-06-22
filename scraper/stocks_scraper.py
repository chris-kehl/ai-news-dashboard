#!/usr/bin/env python3
"""Stocks scraper: trending / hottest stocks via free APIs."""

import requests
from datetime import datetime
import json

HEADERS = {
    "User-Agent": "AI-News-Dashboard/1.0 (Education; bot)"
}

def get_trending_stocks():
    """Yahoo Finance trending tickers (free, no key)."""
    try:
        url = "https://query1.finance.yahoo.com/v1/finance/trending/US"
        r = requests.get(url, headers=HEADERS, timeout=15)
        r.raise_for_status()
        data = r.json()
        quotes = data.get("finance", {}).get("result", [{}])[0].get("quotes", [])
        tickers = [q["symbol"] for q in quotes[:20]]
        return tickers
    except Exception as e:
        print(f"      Trending fetch error: {e}")
        return []

def get_stock_info(symbols):
    """Batch quote for symbols via Yahoo Finance."""
    if not symbols:
        return []
    try:
        # Yahoo Finance requires cookie + crumb; simpler: use free API alternative
        # Fallback: use API with no auth
        url = "https://query1.finance.yahoo.com/v8/finance/chart/"
        stocks = []
        # Fetch in batches of 5 to be polite
        for sym in symbols[:15]:
            try:
                chart_url = f"{url}{sym}?interval=1d&range=2d"
                r = requests.get(chart_url, headers=HEADERS, timeout=10)
                r.raise_for_status()
                d = r.json()
                result = d.get("chart", {}).get("result", [{}])[0]
                meta = result.get("meta", {})
                closes = result.get("indicators", {}).get("quote", [{}])[0].get("close", [])
                if len(closes) >= 2 and closes[-1] and closes[-2]:
                    change = ((closes[-1] - closes[-2]) / closes[-2]) * 100
                else:
                    change = 0
                stocks.append({
                    "symbol": sym,
                    "price": round(closes[-1], 2) if closes else meta.get("regularMarketPrice", 0),
                    "change_percent": round(change, 2),
                    "name": meta.get("shortName", sym)
                })
            except:
                continue
        return stocks
    except Exception as e:
        print(f"      Stock info error: {e}")
        return []

def get_meme_stocks():
    """Manually track known meme / momentum stocks."""
    meme = ["GME", "AMC", "BB", "PLTR", "TSLA", "NVDA", "AMD", "COIN", "HOOD", "MSTR"]
    return get_stock_info(meme)

def get_stocks_data(file_path=None):
    """Master entry: trending + meme stocks."""
    print("[ ] Fetching hottest stocks...")
    trending_tickers = get_trending_stocks()
    trending = get_stock_info(trending_tickers[:15])
    meme = get_meme_stocks()
    data = {
        "timestamp": datetime.utcnow().isoformat(),
        "trending": sorted(trending, key=lambda x: abs(x.get("change_percent", 0)), reverse=True)[:10],
        "meme_momentum": sorted(meme, key=lambda x: abs(x.get("change_percent", 0)), reverse=True)[:10]
    }
    if file_path:
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    return data


if __name__ == "__main__":
    data = get_stocks_data()
    print(f"Trending: {len(data['trending'])}, Meme: {len(data['meme_momentum'])}")
