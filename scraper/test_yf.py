#!/usr/bin/env python3
import json, yfinance as yf, time, sys

assets = json.load(open('/Users/chris/ai-news-dashboard/.cache/universe.json'))
print(f'Universe: {len(assets)}')

# Test first 30 tickers to find hang pattern
for a in assets[:30]:
    t = a['ticker']
    start = time.time()
    try:
        h = yf.Ticker(t).history(period='5d')
        closes = h['Close'].tolist()
        print(f'{t}: OK ({len(closes)} rows, {time.time()-start:.1f}s)')
    except Exception as e:
        print(f'{t}: ERROR ({time.time()-start:.1f}s) - {e}')
