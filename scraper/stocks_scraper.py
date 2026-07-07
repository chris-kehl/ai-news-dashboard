#!/usr/bin/env python3
"""Stocks scraper: trending stocks + market indices via Yahoo v8 chart + CNBC quote API."""

import time
from datetime import datetime
import json
from scraper_utils import fetch_json_with_retry, load_scraper_cache, save_scraper_cache

HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}

# ─── CNBC Quote API (reliable, no key) ──────────────────────────────────────

def cnbc_quotes(symbols):
    """Fetch real-time quotes from CNBC public quote endpoint.
    Symbols like .SPX, .DJI, .IXIC, .VIX, AAPL, TSLA, etc.
    """
    if not symbols:
        return []
    sym_str = "|".join(symbols)
    url = (
        "https://quote.cnbc.com/quote-html-webservice/restQuote/symbolType/symbol"
        f"?symbols={sym_str}&requestMethod=itv&noform=1&partnerId=2"
        "&fund=1&exthrs=1&output=json&events=1"
    )
    data = fetch_json_with_retry(url, headers=HEADERS, timeout=12, max_retries=2, backoff_base=3.0)
    if not data:
        return []
    quotes = []
    raw = data.get("FormattedQuoteResult", {}).get("FormattedQuote", [])
    if isinstance(raw, dict):  # single result
        raw = [raw]
    for q in raw:
        try:
            sym = q.get("symbol", "")
            last = q.get("last", "0").replace(",", "")
            change = q.get("change", "0").replace(",", "").replace("+", "")
            change_pct = q.get("change_pct", "0").replace(",", "").replace("+", "")
            prev = q.get("previous_day_closing", "0").replace(",", "")
            # Parse
            price = float(last) if last else 0
            prev_close = float(prev) if prev else 0
            # CNBC change_pct may have %% typo
            pct_str = change_pct.replace("%", "").replace("%%", "%")
            try:
                pct = float(pct_str) if pct_str else 0
            except:
                pct = 0
            if pct == 0 and prev_close and price:
                pct = round(((price - prev_close) / prev_close) * 100, 2)
            quotes.append({
                "symbol": sym,
                "price": price,
                "change": round(float(change) if change else 0, 2),
                "change_percent": pct,
                "name": q.get("shortName", sym)
            })
        except Exception:
            continue
    return quotes


# ─── Yahoo Finance v8 Chart (individual symbol) ───────────────────────────────

def yahoo_chart(sym):
    """Fetch single symbol via Yahoo v8 chart. Returns {symbol, price, change%, name}."""
    data = fetch_json_with_retry(
        f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?interval=1d&range=2d",
        headers=HEADERS, timeout=10, max_retries=2, backoff_base=3.0
    )
    if not data:
        return None
    try:
        result = data.get("chart", {}).get("result", [{}])[0]
        meta = result.get("meta", {})
        closes = result.get("indicators", {}).get("quote", [{}])[0].get("close", [])
        # Use last non-null close as current price
        price = None
        for c in reversed(closes):
            if c is not None:
                price = c
                break
        if price is None:
            price = meta.get("regularMarketPrice", 0)
        # Previous close: chartPreviousClose is reliable
        prev = meta.get("chartPreviousClose", 0)
        if prev and price:
            change = ((price - prev) / prev) * 100
        else:
            change = 0
        return {
            "symbol": sym,
            "price": round(price, 2) if price else 0,
            "change": round(price - prev, 2) if price and prev else 0,
            "change_percent": round(change, 2),
            "name": meta.get("shortName", sym)
        }
    except Exception:
        return None


def yahoo_charts_batch(symbols, delay=0.3):
    """Fetch multiple symbols via individual v8 calls (batch API is 401)."""
    out = []
    for sym in symbols:
        q = yahoo_chart(sym)
        if q:
            out.append(q)
        time.sleep(delay)
    return out


# ─── Trending tickers ─────────────────────────────────────────────────────────

def get_trending_tickers():
    """Yahoo trending tickers list (free)."""
    cached = load_scraper_cache("trending_stocks", max_age_minutes=15)
    if cached:
        return cached
    data = fetch_json_with_retry(
        "https://query1.finance.yahoo.com/v1/finance/trending/US",
        headers=HEADERS, timeout=15, max_retries=2, backoff_base=3.0
    )
    if not data:
        return []
    try:
        quotes = data.get("finance", {}).get("result", [{}])[0].get("quotes", [])
        tickers = [q["symbol"] for q in quotes[:20]]
        if tickers:
            save_scraper_cache("trending_stocks", tickers)
        return tickers
    except Exception:
        return []


def get_meme_tickers():
    """Known momentum / meme stocks."""
    return ["GME", "AMC", "BB", "PLTR", "TSLA", "NVDA", "AMD", "COIN", "HOOD", "MSTR"]


# ─── Master: Hot Stocks card data ─────────────────────────────────────────────

def get_stocks_data(file_path=None):
    """Trending + meme stocks for the HOT STOCKS card."""
    print("[ ] Fetching hottest stocks...")
    trending_syms = get_trending_tickers()
    trending = yahoo_charts_batch(trending_syms[:12], delay=0.25)
    meme = yahoo_charts_batch(get_meme_tickers(), delay=0.25)
    data = {
        "timestamp": datetime.utcnow().isoformat(),
        "trending": sorted(trending, key=lambda x: abs(x.get("change_percent", 0)), reverse=True)[:10],
        "meme_momentum": sorted(meme, key=lambda x: abs(x.get("change_percent", 0)), reverse=True)[:10]
    }
    if file_path:
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    return data


# ─── Master: Scrolling ticker JSON ────────────────────────────────────────────

def generate_ticker_json(output_path=None):
    """Generate scrolling ticker: indices + crypto + futures + top movers."""
    print("[ ] Generating market ticker...")

    # 1. Market indices via CNBC (reliable)
    indices = cnbc_quotes([".SPX", ".DJI", ".IXIC", ".VIX", ".RUT"])

    # 2. Futures via Yahoo v8 (works for futures symbols)
    futures_symbols = ["ES=F", "NQ=F", "YM=F", "RTY=F", "CL=F", "GC=F", "NG=F"]
    futures = yahoo_charts_batch(futures_symbols, delay=0.25)

    # 3. Crypto via CoinGecko (free, no key)
    crypto_prices = []
    try:
        url = "https://api.coingecko.com/api/v3/coins/markets"
        params = {
            "vs_currency": "usd",
            "ids": "bitcoin,ethereum,solana,dogecoin,avalanche-2,chainlink,bittensor",
            "sparkline": "false",
            "price_change_percentage": "24h"
        }
        cg = fetch_json_with_retry(url, params=params, headers=HEADERS, timeout=15, max_retries=2, backoff_base=3.0)
        if cg:
            for coin in cg:
                crypto_prices.append({
                    "symbol": coin["symbol"].upper(),
                    "price": coin["current_price"],
                    "change": round(coin.get("price_change_percentage_24h") or 0, 2)
                })
    except Exception as e:
        print(f"      Crypto ticker error: {e}")

    # Ensure TAO is first
    crypto_prices.sort(key=lambda x: 0 if x.get("symbol") == "TAO" else 1)

    # 3. Top moving stocks: trending + meme, limited to avoid rate limits
    trending_syms = get_trending_tickers()
    # Interleave trending + meme to get actual movers
    combined = []
    seen = set()
    for s in trending_syms[:10] + get_meme_tickers():
        if s not in seen:
            combined.append(s)
            seen.add(s)
    movers = yahoo_charts_batch(combined[:14], delay=0.3)
    # Sort by absolute change
    movers = sorted(movers, key=lambda x: abs(x.get("change_percent", 0)), reverse=True)[:10]

    # Build items: indices first, then futures, then crypto, then movers
    items = []
    for idx in indices:
        items.append({
            "symbol": idx["symbol"].replace(".", ""),
            "price": idx["price"],
            "change": idx["change_percent"]
        })
    for f in futures:
        items.append({
            "symbol": f["symbol"],
            "price": f["price"],
            "change": f["change_percent"]
        })
    for c in crypto_prices:
        items.append({"symbol": c["symbol"], "price": c["price"], "change": c["change"]})
    for m in movers:
        items.append({"symbol": m["symbol"], "price": m["price"], "change": m["change_percent"]})

    ticker_data = {
        "timestamp": datetime.utcnow().isoformat(),
        "items": items
    }

    if output_path:
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(ticker_data, f, indent=2, ensure_ascii=False)
        print(f"      Ticker: {len(items)} items written to {output_path}")

    return ticker_data


if __name__ == "__main__":
    data = get_stocks_data()
    print(f"Trending: {len(data['trending'])}, Meme: {len(data['meme_momentum'])}")
    ticker = generate_ticker_json("ticker.json")
    print(f"Ticker items: {len(ticker['items'])}")
    for i in ticker["items"][:15]:
        print(f"  {i['symbol']:8} {str(i['price']):>12}  {i['change']:>+7.2f}%")
