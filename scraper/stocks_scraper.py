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
    """Master entry: trending + meme stocks + ticker data."""
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


def generate_ticker_json(output_path=None):
    """Generate scrolling ticker JSON: crypto + S&P + trending."""
    print("[ ] Generating market ticker...")

    crypto_coins = ["BTC", "ETH", "SOL", "DOGE", "AVAX", "LINK", "TAO"]
    sp_list = [
        "AAPL","MSFT","GOOGL","AMZN","NVDA","META","TSLA","BRK-B","UNH","XOM",
        "LLY","JPM","V","JNJ","WMT","MA","PG","AVGO","HD","CVX","MRK","ABBV",
        "PEP","KO","COST","TMO","ADBE","DIS","ABT","WFC","BAC","CSCO","PFE",
        "CRM","ORCL","ACN","NKE","MCD","CMCSA","TXN","DHR","VZ","NEE","PM",
        "RTX","HON","LIN","IBM","LOW","UPS","AMGN","CAT","INTC","GS","SPGI",
        "MDT","BLK","T","BA","DE","LMT","GE","AMAT","NOW","SYK","ISRG","GILD",
        "BKNG","MMC","TJX","VRTX","PLD","ADI","MDLZ","TMUS","SCHW","CI","AXP",
        "C","MS","PYPL","CB","SO","REGN","ZTS","BSX","MO","DUK","BMY","PGR",
        "SLB","TGT","COP","FDX","SBUX","ELV","CL","ICE","APD","ETN","PSA","ITW",
        "EOG","EW","HCA","NOC","AON","FISV","GD","GM","SHW","OXY","MU","PNC",
        "CSX","NSC","DXCM","KMB","SRE","BDX","LRCX","STZ","HUM","MAR","MCO"
    ]

    # Batch fetch via Yahoo Finance v8 chart (free, no auth)
    def batch_quotes(symbols, limit=80):
        """Fetch up to N symbols to avoid rate limits."""
        quotes = []
        for sym in symbols[:limit]:
            try:
                url = f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?interval=1d&range=2d"
                r = requests.get(url, headers=HEADERS, timeout=8)
                if not r.ok:
                    continue
                d = r.json()
                result = d.get("chart", {}).get("result", [{}])[0]
                meta = result.get("meta", {})
                closes = result.get("indicators", {}).get("quote", [{}])[0].get("close", [])
                price = closes[-1] if closes and closes[-1] else meta.get("regularMarketPrice", 0)
                prev = closes[-2] if len(closes) >= 2 and closes[-2] else meta.get("previousClose", 0)
                if price and prev:
                    change = ((price - prev) / prev) * 100
                else:
                    change = 0
                quotes.append({
                    "symbol": sym,
                    "price": round(price, 2) if price else 0,
                    "change": round(change, 2)
                })
            except Exception:
                continue
        return quotes

    # Get crypto prices from CoinGecko
    crypto_prices = []
    try:
        url = "https://api.coingecko.com/api/v3/coins/markets"
        params = {"vs_currency":"usd","ids":"bitcoin,ethereum,solana,dogecoin,avalanche-2,chainlink,bittensor","sparkline":"false","price_change_percentage":"24h"}
        cg = requests.get(url, params=params, headers=HEADERS, timeout=15)
        if cg.ok:
            for coin in cg.json():
                crypto_prices.append({
                    "symbol": coin["symbol"].upper(),
                    "price": coin["current_price"],
                    "change": round(coin.get("price_change_percentage_24h") or 0, 2)
                })
    except Exception as e:
        print(f"      Crypto ticker error: {e}")

    # Get S&P stocks
    sp_quotes = batch_quotes(sp_list, limit=80)

    # Combine: crypto first, then S&P
    items = crypto_prices + sp_quotes

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
