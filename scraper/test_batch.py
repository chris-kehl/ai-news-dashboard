#!/usr/bin/env python3
"""Test batch download with a subset of tickers first."""
import json, yfinance as yf, time
from pathlib import Path

base = Path("/Users/chris/ai-news-dashboard")
universe = json.load(open(base / ".cache/universe_full.json"))

# Test with 100 tickers first
test_tickers = list(universe.keys())[:100]
print(f"Testing batch download with {len(test_tickers)} tickers...")

start = time.time()
result = yf.download(
    test_tickers,
    period="35d",
    interval="1d",
    group_by="ticker",
    threads=True,
    progress=False,
    auto_adjust=False
)
elapsed = time.time() - start

valid = []
if hasattr(result.columns, 'get_level_values'):
    tickers_found = result.columns.get_level_values(0).unique().tolist()
else:
    tickers_found = list(universe.keys())[:1]  # single ticker case

for t in tickers_found:
    try:
        close = result[(t, 'Close')].dropna().tolist() if hasattr(result.columns, 'get_level_values') else result['Close'].dropna().tolist()
        if len(close) > 5:
            valid.append(t)
    except:
        pass

print(f"Downloaded: {len(tickers_found)} tickers in {elapsed:.1f}s")
print(f"Valid (have prices): {len(valid)} / {len(test_tickers)}")
print(f"First 10 valid: {valid[:10]}")

# Now test crypto-specific
print("\nTesting crypto-specific download...")
crypto = ['BTC-USD', 'ETH-USD', 'SOL-USD', 'ADA-USD']
result = yf.download(crypto, period='5d', group_by='ticker', threads=True, progress=False)
if hasattr(result.columns, 'get_level_values'):
    crypto_found = result.columns.get_level_values(0).unique().tolist()
else:
    crypto_found = []
print(f"Crypto tickers found: {crypto_found}")
for t in crypto_found:
    try:
        close = result[(t, 'Close')].dropna().iloc[-1]
        print(f"  {t}: ${close:.2f}")
    except:
        pass
