#!/usr/bin/env python3
"""Parallel universe validator — filters dead tickers fast."""
import json, multiprocessing, signal, yfinance as yf, time
from pathlib import Path

def check_ticker(args):
    t, info = args
    try:
        signal.alarm(8)
        h = yf.Ticker(t).history(period="2d", interval="1d")
        signal.alarm(0)
        if len(h) < 1:
            return None
        return (t, info)
    except:
        return None
    finally:
        signal.alarm(0)

if __name__ == "__main__":
    base = Path("/Users/chris/ai-news-dashboard")
    universe = json.load(open(base / ".cache/universe_full.json"))
    items = list(universe.items())
    print(f"Validating {len(items)} tickers via {multiprocessing.cpu_count()} processes...")
    
    pool = multiprocessing.Pool(processes=min(8, multiprocessing.cpu_count()))
    start = time.time()
    results = pool.map(check_ticker, items, chunksize=50)
    pool.close()
    pool.join()
    
    valid = {}
    for r in results:
        if r:
            valid[r[0]] = r[1]
    
    elapsed = time.time() - start
    print(f"\nValid: {len(valid)} / {len(items)} ({elapsed:.0f}s)")
    with open(base / ".cache/universe_valid.json", "w") as f:
        json.dump(valid, f)
    print("Saved to universe_valid.json")
