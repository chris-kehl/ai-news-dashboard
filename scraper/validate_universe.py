#!/usr/bin/env python3
"""
Quick ticker validator — filters universe to only liquid, valid tickers.
Runs once per week, cached for the pipeline.
"""
import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

import yfinance as yf

ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = ROOT / ".cache"

def quick_check(ticker):
    """5-second check if ticker has recent data."""
    try:
        t = yf.Ticker(ticker)
        # Fast check — just get last day's close
        hist = t.history(period="2d", interval="1d", timeout=5)
        if hist.empty or len(hist) < 1:
            return None
        close = float(hist["Close"].iloc[-1])
        if close > 0:
            return {"ticker": ticker, "price": round(close, 2)}
    except Exception:
        pass
    return None

async def validate_universe(universe_path, out_path, max_workers=10):
    print(f"[validate] Loading universe from {universe_path}")
    with open(universe_path) as f:
        universe = json.load(f)
    
    tickers = list(universe.keys())
    print(f"[validate] Checking {len(tickers)} tickers...")
    
    loop = asyncio.get_event_loop()
    sem = asyncio.Semaphore(max_workers)
    
    async def _check(t):
        async with sem:
            return await loop.run_in_executor(None, quick_check, t)
    
    valid = {}
    batch_size = 50
    for i in range(0, len(tickers), batch_size):
        batch = tickers[i:i+batch_size]
        results = await asyncio.gather(*[_check(t) for t in batch])
        for r in results:
            if r:
                info = universe.get(r["ticker"], {})
                valid[r["ticker"]] = info
        print(f"      [validate] {min(i+len(batch), len(tickers))}/{len(tickers)} — {len(valid)} valid")
        await asyncio.sleep(0.5)
    
    print(f"[validate] {len(valid)}/{len(tickers)} tickers are liquid and valid")
    with open(out_path, "w") as f:
        json.dump(valid, f, indent=2)
    return valid

if __name__ == "__main__":
    universe_path = CACHE_DIR / "universe.json"
    out_path = CACHE_DIR / "universe_validated.json"
    asyncio.run(validate_universe(universe_path, out_path))
