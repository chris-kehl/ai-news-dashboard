#!/usr/bin/env python3
"""
Universe Builder — scrapes live S&P 500, Russell 2000, ETF lists, and crypto.
Writes assets.json with ~2,700 tickers.
"""
import asyncio
import json
import re
from datetime import datetime
from pathlib import Path

import aiohttp

ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = ROOT / ".cache"
CACHE_DIR.mkdir(exist_ok=True)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
}

async def fetch_sp500(session: aiohttp.ClientSession) -> list:
    """Scrape S&P 500 constituents from Wikipedia."""
    url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
    try:
        async with session.get(url, headers=HEADERS, timeout=aiohttp.ClientTimeout(total=15)) as r:
            if r.status != 200:
                return []
            text = await r.text()
            # Find the constituent table
            tbody = re.search(r'<tbody[^>]*>(.*?)</tbody>', text, re.DOTALL)
            if not tbody:
                return []
            # Extract ticker symbols from the first column links
            tickers = re.findall(r'<a[^>]*href="/wiki/[^"]*"[^>]*title="[^"]*">([A-Z]{1,5})</a>', tbody.group(1))
            # Remove Wikipedia article links that aren't tickers
            tickers = [t for t in tickers if t not in {"NYSE", "NASDAQ", "ETF", "INDEX", "THE", "AND"}]
            # Wikipedia has some non-ticker links — filter anything > 5 chars or < 1
            tickers = [t for t in tickers if 1 <= len(t) <= 5]
            # Deduplicate preserving order
            seen = set()
            result = []
            for t in tickers:
                if t not in seen:
                    seen.add(t)
                    result.append(t)
            print(f"      [sp500] Scraped {len(result)} tickers from Wikipedia")
            return result
    except Exception as e:
        print(f"      [sp500] Error: {e}")
        return []


async def fetch_russell2k(session: aiohttp.ClientSession) -> list:
    """Scrape Russell 2000 from stockanalysis.com (paginated)."""
    tickers = []
    try:
        for page in range(1, 21):  # 20 pages × ~100 = 2,000 tickers
            url = f"https://stockanalysis.com/list/russell-2000-stocks/?page={page}"
            async with session.get(url, headers=HEADERS, timeout=aiohttp.ClientTimeout(total=20)) as r:
                if r.status != 200:
                    break
                text = await r.text()
                # Match the stock links
                page_tickers = re.findall(r'href="/stock/([a-z0-9\-]+)/"', text, re.IGNORECASE)
                page_tickers = [t.upper().replace('-', '.') for t in page_tickers]
                if not page_tickers:
                    break
                tickers.extend(page_tickers)
                print(f"      [russell] Page {page}: {len(page_tickers)} tickers")
        
        # Deduplicate
        seen = set()
        result = []
        for t in tickers:
            if t not in seen and t not in {"PAGE", "STOCK"}:
                seen.add(t)
                result.append(t)
        print(f"      [russell] Total scraped: {len(result)}")
        return result
    except Exception as e:
        print(f"      [russell] Error: {e}")
        return []


async def fetch_etfs(session: aiohttp.ClientSession) -> list:
    """Scrape ETF list from Wikipedia + stockanalysis.com for complete coverage."""
    # First try stockanalysis.com (comprehensive: 5,500+ ETFs)
    all_etfs = []
    seen = set()
    
    try:
        for page in range(1, 21):  # Pages 1-20 cover top ~2,000 ETFs by AUM
            url = f"https://stockanalysis.com/etf/?page={page}"
            async with session.get(url, headers=HEADERS, timeout=aiohttp.ClientTimeout(total=20)) as r:
                if r.status != 200:
                    break
                text = await r.text()
                import re
                matches = re.findall(r'\{s:"([A-Z]{1,5})",n:"([^"]+)"', text)
                for sym, name in matches:
                    if sym not in seen:
                        seen.add(sym)
                        all_etfs.append((sym, name))
                if not matches:
                    break
    except Exception as e:
        print(f"      [etfs] StockAnalysis error: {e}")
    
    # Also try Wikipedia as a secondary source
    try:
        url = "https://en.wikipedia.org/wiki/List_of_American_exchange-traded_funds"
        async with session.get(url, headers=HEADERS, timeout=aiohttp.ClientTimeout(total=15)) as r:
            if r.status == 200:
                text = await r.text()
                import re
                tables = re.findall(r'<table[^>]*class="wikitable[^"]*"[^>]*>(.*?)</table>', text, re.DOTALL)
                for table in tables[:3]:
                    t = re.findall(r'<td[^>]*>\s*<a[^>]+href="[^"]*"[^>]*>([A-Z]{1,5})</a>\s*</td>', table)
                    for sym in t:
                        if sym not in seen and sym not in {"ETF", "NYSE", "NASDAQ", "THE", "AND", "USD"} and len(sym) <= 5:
                            seen.add(sym)
                            all_etfs.append((sym, sym))
    except Exception:
        pass
    
    print(f"      [etfs] Total unique ETFs scraped: {len(all_etfs)}")
    return all_etfs


async def fetch_crypto() -> list:
    """Get top crypto from CoinGecko (free API, no key needed)."""
    url = "https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd&order=market_cap_desc&per_page=100&page=1"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as r:
                if r.status != 200:
                    return []
                data = await r.json()
                tickers = [f"{c['symbol'].upper()}-USD" for c in data[:100]]
                # Remove duplicates
                seen = set()
                result = []
                for t in tickers:
                    if t not in seen:
                        seen.add(t)
                        result.append(t)
                print(f"      [crypto] Fetched {len(result)} from CoinGecko")
                return result
    except Exception as e:
        print(f"      [crypto] Error: {e}")
        return []


async def build_full_universe() -> dict:
    """Build complete asset universe with live scraping."""
    print("[universe] Building full asset universe...")
    
    async with aiohttp.ClientSession() as session:
        sp500, russell, etfs = await asyncio.gather(
            fetch_sp500(session),
            fetch_russell2k(session),
            fetch_etfs(session),
        )
    
    crypto = await fetch_crypto()
    
    # Combine
    assets = {}
    
    for t in sp500:
        assets[t] = {"name": t, "category": "Equity - S&P 500"}
    
    for t in russell:
        if t not in assets:
            assets[t] = {"name": t, "category": "Equity - Russell 2000"}
    
    for t, name in etfs:
        if t not in assets:
            assets[t] = {"name": name or t, "category": "ETF"}
    
    for t in crypto:
        if t not in assets:
            assets[t] = {"name": t.replace('-USD', ''), "category": "Crypto"}
    
    # Add precious metals
    metals = ["GLD", "SLV", "IAU", "PPLT", "PALL", "CPER", "GC=F", "SI=F", "PL=F"]
    for t in metals:
        if t not in assets:
            assets[t] = {"name": t, "category": "Precious Metal"}
    
    # Add bonds
    bonds = ["TLT", "IEF", "SHY", "LQD", "HYG", "JNK", "EMB", "BND", "AGG", "TIP", "MBB"]
    for t in bonds:
        if t not in assets:
            assets[t] = {"name": t, "category": "Bond ETF"}
    
    # Add commodities
    commods = ["USO", "UNG", "DBC", "DBA", "PDBC", "GSG"]
    for t in commods:
        if t not in assets:
            assets[t] = {"name": t, "category": "Commodity ETF"}
    
    print(f"[universe] Total unique assets: {len(assets)}")
    print(f"           S&P 500: {len(sp500)}")
    print(f"           Russell 2000: {len(russell)}")
    print(f"           ETFs: {len(etfs)}")
    print(f"           Crypto: {len(crypto)}")
    print(f"           Metals/Bonds/Commods: {len(metals) + len(bonds) + len(commods)}")
    
    return assets


if __name__ == "__main__":
    assets = asyncio.run(build_full_universe())
    out = CACHE_DIR / "universe.json"
    with open(out, "w") as f:
        json.dump(assets, f, indent=2)
    print(f"[universe] Written to {out}")
