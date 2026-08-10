#!/usr/bin/env python3
"""
Weekly AI Pick Scorer
Fetches data for all tickers in universe.jsonl, calculates composite scores,
and outputs top picks with rationale. Run Sundays at 3pm after market-data update.
"""

import json, time, urllib.request, urllib.error, math
from pathlib import Path
from datetime import datetime

UNIVERSE_PATH = Path.home() / "ai-news-dashboard" / "data" / "universe.jsonl"
SCORES_PATH = Path.home() / "ai-news-dashboard" / "data" / "weekly_scores.json"
MAX_CONSECUTIVE_ERRORS = 5


def fetch_yf(ticker: str):
    """Fetch chart data from Yahoo Finance public API."""
    # Handle tickers with special chars
    url_ticker = urllib.parse.quote(ticker) if '^' in ticker or '%' in ticker else ticker
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{url_ticker}?interval=1d&range=3mo&includeAdjustedClose=true"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
        result = data.get("chart", {}).get("result", [None])[0]
        if not result:
            return None
        indicators = result.get("indicators", {}).get("quote", [{}])[0]
        closes = [c for c in indicators.get("close", []) if c is not None]
        volumes = [v for v in indicators.get("volume", []) if v is not None]
        timestamps = result.get("timestamp", [])
        meta = result.get("meta", {})
        return {
            "closes": closes,
            "volumes": volumes,
            "timestamps": timestamps,
            "price": closes[-1] if closes else meta.get("regularMarketPrice"),
            "prev_close": meta.get("previousClose"),
            "market_cap": None,  # Not available from chart endpoint
            "name": meta.get("shortName", "") or meta.get("longName", ""),
        }
    except Exception as e:
        return {"error": str(e)}


def sma(data, n):
    if len(data) < n:
        return sum(data) / len(data) if data else 0
    return sum(data[-n:]) / n


def rsi(closes, period=14):
    if len(closes) < period + 1:
        return 50
    gains, losses = [], []
    for i in range(1, period + 1):
        change = closes[-i] - closes[-(i + 1)]
        if change > 0:
            gains.append(change)
            losses.append(0)
        else:
            gains.append(0)
            losses.append(abs(change))
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    if avg_loss == 0:
        return 100
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def ema(closes, period):
    if len(closes) < period:
        return sma(closes, len(closes))
    k = 2 / (period + 1)
    ema_val = sma(closes[:period], period)
    for price in closes[period:]:
        ema_val = price * k + ema_val * (1 - k)
    return ema_val


def score_ticker(ticker_info, data):
    """Compute composite score 0-100."""
    closes = data.get("closes", [])
    volumes = data.get("volumes", [])
    if len(closes) < 20:
        return {"score": 0, "error": "insufficient data"}

    price = closes[-1] if closes else 0
    
    # --- Momentum Component (0-30) ---
    chg_1d = (closes[-1] / closes[-2] - 1) * 100 if len(closes) >= 2 else 0
    chg_5d = (closes[-1] / closes[-6] - 1) * 100 if len(closes) >= 6 else 0
    chg_20d = (closes[-1] / closes[-21] - 1) * 100 if len(closes) >= 21 else 0
    
    momentum = 0
    # Reward positive 5-day and 20-day momentum
    if chg_5d > 2: momentum += 8
    elif chg_5d > 0: momentum += 4
    elif chg_5d < -2: momentum -= 4
    
    if chg_20d > 5: momentum += 10
    elif chg_20d > 0: momentum += 5
    elif chg_20d < -5: momentum -= 5
    
    # 1-day follow-through (confirmation)
    if chg_1d > 0 and chg_5d > 0: momentum += 6
    elif chg_1d < 0 and chg_5d > 0: momentum += 2  # still positive week
    elif chg_1d < 0 and chg_5d < 0: momentum -= 4
    
    if chg_20d > 10: momentum += 6  # strong trend bonus
    
    momentum = max(0, min(30, momentum))
    
    # --- Trend Component (0-25) ---
    sma10 = sma(closes, min(10, len(closes)))
    sma20 = sma(closes, min(20, len(closes)))
    sma50 = sma(closes, min(50, len(closes)))
    
    trend = 0
    if price > sma10: trend += 5
    if price > sma20: trend += 5
    if price > sma50: trend += 5
    if sma10 > sma20: trend += 5  # golden arrangement
    if sma20 > sma50: trend += 5
    trend = max(0, min(25, trend))
    
    # --- RSI Component (0-15) ---
    rsi_val = rsi(closes, 14)
    rsi_score = 0
    if 40 < rsi_val < 60: rsi_score = 10  # sweet spot
    elif 30 < rsi_val <= 40: rsi_score = 12  # oversold bounce potential
    elif 60 <= rsi_val < 75: rsi_score = 12  # momentum room
    elif rsi_val >= 75: rsi_score = 5  # overbought
    elif rsi_val <= 30: rsi_score = 5  # oversold, could fall further
    rsi_score = max(0, min(15, rsi_score))
    
    # --- Volume Component (0-15) ---
    vol_score = 0
    if len(volumes) >= 10:
        avg_vol = sum(volumes[-10:]) / 10
        latest_vol = volumes[-1] if volumes else 0
        if avg_vol > 0:
            vol_ratio = latest_vol / avg_vol
            if vol_ratio > 1.5: vol_score = 12  # volume confirmation
            elif vol_ratio > 1.1: vol_score = 8
            elif vol_ratio > 0.8: vol_score = 5
            elif vol_ratio < 0.5: vol_score = 2
    else:
        vol_score = 7  # neutral
    vol_score = max(0, min(15, vol_score))
    
    # --- Volatility / Risk Component (0-15) ---
    vol = None
    if len(closes) >= 5:
        returns = [(closes[i] / closes[i-1] - 1) * 100 for i in range(1, len(closes))]
        mean_ret = sum(returns) / len(returns)
        variance = sum((r - mean_ret) ** 2 for r in returns) / len(returns)
        vol = math.sqrt(variance)
        # Lower vol is better for a pick (stable uptrend)
        if vol < 1.0: vol_adj = 15
        elif vol < 1.5: vol_adj = 12
        elif vol < 2.5: vol_adj = 10
        elif vol < 4.0: vol_adj = 7
        else: vol_adj = 4
    else:
        vol_adj = 7
    
    # Composite
    total = momentum + trend + rsi_score + vol_score + vol_adj
    
    factors = {
        "price": round(price, 2),
        "chg_1d": round(chg_1d, 2),
        "chg_5d": round(chg_5d, 2),
        "chg_20d": round(chg_20d, 2),
        "rsi": round(rsi_val, 1),
        "momentum": momentum,
        "trend": trend,
        "rsi_score": rsi_score,
        "vol_score": vol_score,
        "volatility": round(vol, 2) if vol is not None else None,
        "vol_adj": vol_adj,
    }
    
    return {"score": round(total, 1), "factors": factors}


def main():
    print(f"Weekly AI Pick Scorer — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    
    # Load universe
    universe = []
    with open(UNIVERSE_PATH) as f:
        for line in f:
            universe.append(json.loads(line))
    
    # For testing, limit to first 100 tickers to verify scoring logic
    # universe = universe[:100]
    
    print(f"Universe: {len(universe)} tickers")
    
    scored = []
    consecutive_errors = 0
    
    for item in universe:
        ticker = item["ticker"]
        name = item.get("name", "")
        
        if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
            print("  Too many errors, pausing 5s...")
            time.sleep(5)
            consecutive_errors = 0
        
        data = fetch_yf(ticker)
        
        if data is None or (isinstance(data, dict) and data.get("error")):
            consecutive_errors += 1
            continue
        
        consecutive_errors = 0
        result = score_ticker(item, data)
        result["ticker"] = ticker
        result["name"] = name or data.get("name", "")
        result["type"] = item.get("type", "stock")
        result["category"] = item.get("category", "")
        scored.append(result)
        
        # Rate limit
        time.sleep(0.15)
    
    # Sort by score descending
    scored.sort(key=lambda x: x["score"], reverse=True)
    
    # Save results
    output = {
        "generated_at": datetime.now().isoformat(),
        "universe_size": len(universe),
        "scored_count": len(scored),
        "top_picks": scored[:20],
        "all_scores": scored,
    }
    
    with open(SCORES_PATH, "w") as f:
        json.dump(output, f, indent=2)
    
    print(f"\nScored {len(scored)} tickers")
    print("\n=== TOP 10 ===")
    for s in scored[:10]:
        print(f"  {s['score']:>5.1f} | {s['ticker']:<6} | {s['name'][:30]:<30} | {s.get('category','')}")
    
    print(f"\nScores saved to {SCORES_PATH}")
    
    return scored[:5]


if __name__ == "__main__":
    import urllib.parse
    main()
