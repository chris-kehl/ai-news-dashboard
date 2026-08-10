#!/usr/bin/env python3
"""
yFinance batch fetch — bypasses Yahoo Finance 429 with cookie-impersonation.
Standalone script: builds universe, fetches history via yfinance, generates pick.
"""
import asyncio
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Dict, List

import yfinance as yf

# ─── Paths ────────────────────────────────────────────────────────────
SCRAPER_DIR = Path(__file__).resolve().parent
ROOT = SCRAPER_DIR.parent
DATA_PATH = ROOT / "data.json"
CACHE_DIR = ROOT / ".cache"
CACHE_DIR.mkdir(exist_ok=True)

# ─── Load existing scraper logic ──────────────────────────────────────
sys.path.insert(0, str(SCRAPER_DIR))

from weekly_pick_scraper import (
    build_universe,
    quick_select,
    analyze_ticker,
    analyze_one,
    scale_to_100,
    generate_rationale,
    DATA_PATH,
    CACHE_DIR,
    METALS,
)

try:
    from sentiment_analyzer import fetch_sentiment
except ImportError:
    fetch_sentiment = None


# ─── yFinance fetcher ─────────────────────────────────────────────────

def fetch_single_ticker(ticker: str, days: int = 35) -> List[float]:
    """Fetch daily closes for ONE ticker via yfinance (synchronous)."""
    try:
        data = yf.Ticker(ticker).history(period=f"{days}d", interval="1d")
        if data.empty:
            return []
        closes = data["Close"].dropna().tolist()
        return [float(c) for c in closes]
    except Exception:
        return []


async def batch_fetch_yf(tickers: List[str], days: int = 35) -> Dict[str, list]:
    """Fetch histories in parallel via ThreadPoolExecutor + yfinance."""
    results = {}
    loop = asyncio.get_event_loop()
    
    with ThreadPoolExecutor(max_workers=10) as pool:
        # Submit all
        futures = {
            t: loop.run_in_executor(pool, fetch_single_ticker, t, days)
            for t in tickers
        }
        
        # Gather with progress
        done = 0
        total = len(tickers)
        for t, fut in futures.items():
            try:
                closes = await fut
                if closes and len(closes) >= 5:
                    results[t] = closes
            except Exception:
                pass
            done += 1
            if done % 30 == 0:
                print(f"      [yf] {done}/{total} done, valid={len(results)}")
    
    print(f"      [yf] Final valid histories: {len(results)}/{len(tickers)}")
    return results


# ─── Analysis ─────────────────────────────────────────────────────────

def calc_rsi(closes, period=14):
    if len(closes) < period + 1:
        return None
    gains, losses = [], []
    for i in range(1, period + 1):
        diff = closes[i] - closes[i - 1]
        gains.append(max(diff, 0))
        losses.append(max(-diff, 0))
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def calc_sma(closes, period):
    if len(closes) < period:
        return None
    return sum(closes[-period:]) / period


def calc_volatility(closes, lookback=10):
    if len(closes) < lookback + 1:
        return None
    returns = []
    for i in range(-lookback, 0):
        ret = (closes[i] - closes[i - 1]) / abs(closes[i - 1]) if closes[i - 1] != 0 else 0
        returns.append(ret)
    import statistics
    if len(returns) < 2:
        return 0
    return statistics.stdev(returns) * (252 ** 0.5)


def calc_drawdown(closes):
    peak = max(closes)
    trough = min(closes)
    if peak == 0:
        return None
    return (peak - closes[-1]) / peak * 100 if closes[-1] < peak else 0


def analyze_ticker_yf(ticker, info, closes):
    if not closes or len(closes) < 14:
        return None
    price = closes[-1]
    week = (closes[-1] - closes[-5]) / abs(closes[-5]) * 100 if len(closes) >= 5 else 0
    month = (closes[-1] - closes[-min(20, len(closes))]) / abs(closes[-min(20, len(closes))]) * 100 if len(closes) >= 20 else 0
    rsi = calc_rsi(closes)
    sma20 = calc_sma(closes, 20)
    sma50 = calc_sma(closes, 50)
    vol = calc_volatility(closes)
    dd = calc_drawdown(closes)
    
    score = 50
    factors = []
    
    if week >= 3:
        score += 10
        factors.append(f"+{week:.1f}% week")
    elif week >= 1:
        score += 5
        factors.append(f"+{week:.1f}% week")
    elif week <= -3:
        score -= 10
        factors.append(f"{week:.1f}% week")
    
    if month >= 5:
        score += 10
        factors.append(f"+{month:.1f}% month")
    elif month >= 2:
        score += 5
        factors.append(f"+{month:.1f}% month")
    elif month <= -5:
        score -= 5
        factors.append(f"{month:.1f}% month")
    
    if rsi is not None:
        if 50 <= rsi <= 70:
            score += 5
            factors.append(f"RSI {rsi:.0f} positive")
        elif rsi > 70:
            score += 2
            factors.append(f"RSI {rsi:.0f} strong")
        elif rsi < 30:
            score -= 5
            factors.append(f"RSI {rsi:.0f} oversold")
    
    if sma20 and price > sma20 * 1.02:
        score += 5
        factors.append("above SMA20")
    elif sma20 and price < sma20 * 0.98:
        score -= 3
        factors.append("below SMA20")
    
    if sma50 and price > sma50 * 1.02:
        score += 3
    
    if vol is not None:
        if vol > 5:
            score -= 3
            factors.append(f"high vol {vol:.1f}%")
        elif vol > 3:
            score -= 1
            factors.append(f"elevated vol {vol:.1f}%")
    
    if dd is not None and dd > 10:
        score -= 3
        factors.append(f"deep drawdown -{dd:.0f}%")
    
    if info.get("category", "") == "ETF":
        score += 2
        factors.append("ETF trend strength")
    
    if ticker in {"BTC-USD", "ETH-USD", "SOL-USD", "ADA-USD", "LINK-USD", "AVAX-USD", "XRP-USD", "DOGE-USD"}:
        factors.append("crypto momentum")
    
    return {
        "ticker": ticker,
        "name": info.get("name", ticker),
        "category": info.get("category", "Stock"),
        "price": round(price, 2),
        "change_7d": round(week, 2),
        "change_30d": round(month, 2),
        "rsi": round(rsi, 1) if rsi is not None else None,
        "sma20": round(sma20, 2) if sma20 is not None else None,
        "sma50": round(sma50, 2) if sma50 is not None else None,
        "volatility": round(vol, 2) if vol is not None else None,
        "drawdown": round(dd, 2) if dd is not None else None,
        "score": max(min(score, 99), 1),
        "factors": factors,
    }


# ─── Main ─────────────────────────────────────────────────────────────

async def main():
    print(f"[weekly_pick] Generating fresh pick for {datetime.now().strftime('%a %b %d %Y')}")
    print("      [step 1] Building universe...")
    
    # Use existing weekly_pick_scraper to build universe
    # We just need the tickers list — replicate quickly
    from weekly_pick_scraper import (
        fetch_sp500_tickers,
        fetch_russell_tickers,
        fetch_etf_tickers,
        get_crypto_list,
    )
    
    async with None:  # Dummy for signature
        pass
    
    # Actually just call build_universe with a dummy session
    import aiohttp
    timeout = aiohttp.ClientTimeout(total=15)
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    }
    async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
        assets = await build_universe(session)
    
    if not assets:
        print("      [ERROR] No assets to analyze")
        return
    
    print(f"      [step 2] Fetching {len(assets)} histories via yfinance...")
    histories = await batch_fetch_yf(list(assets.keys()))
    
    if not histories:
        print("      [ERROR] No valid price histories")
        return
    
    print(f"      [step 3] Analyzing {len(histories)} assets...")
    results = []
    for ticker, closes in histories.items():
        info = assets.get(ticker, {})
        result = analyze_ticker_yf(ticker, info, closes)
        if result:
            results.append(result)
    
    if not results:
        print("      [ERROR] No analyzable results")
        return
    
    print(f"      [step 4] Sentiment fetch...")
    if fetch_sentiment:
        sentiment_data = await fetch_sentiment()
        ticker_sent = {}
        top_sent = None
        total_mentions = 0
    else:
        sentiment_data = {}
        ticker_sent = {}
        top_sent = None
        total_mentions = 0
    
    print(f"      [step 5] Ranking and building output...")
    results.sort(key=lambda x: x["score"], reverse=True)
    top_pick = results[0]
    top_five = results[:5]
    all_assets = results[:15]
    
    week_label = datetime.now().strftime("Week of %b %d, %Y")
    
    # Build rationales
    for asset in all_assets:
        ticker = asset["ticker"]
        asset["rationale"] = f"Scored {asset['score']}/100 — " + ", ".join(asset["factors"][:4])
    
    top_pick["rationale"] = generate_rationale(
        top_pick, top_five, len(results), top_sent, total_mentions
    )
    
    weekly_pick = {
        "generated_at": datetime.now().isoformat(),
        "week_label": week_label,
        "top_pick": {
            "name": top_pick["ticker"],
            "display_name": top_pick.get("name", top_pick["ticker"]),
            "price": top_pick["price"],
            "signal": "BULLISH" if top_pick.get("score", 50) > 60 else "NEUTRAL",
            "score": top_pick.get("score", 50),
            "rationale": top_pick.get("rationale", ""),
            "key_levels": f"Support: ${top_pick.get('sma20', 0):.2f}",
            "timeframe": "Swing (1-4 weeks)",
            "factors": top_pick.get("factors", []),
            "sentiment_score": top_sent.get("sentiment_score", 0) if top_sent else None,
            "mention_count": top_sent.get("mention_count", 0) if top_sent else None,
        },
        "top_five": [
            {
                "ticker": r["ticker"],
                "name": r.get("name", r["ticker"]),
                "category": r.get("category", ""),
                "score": r["score"],
                "price": r["price"],
                "change_7d": r.get("change_7d", 0),
                "change_30d": r.get("change_30d", 0),
            }
            for r in top_five
        ],
        "all_assets": all_assets,
        "rationale": top_pick.get("rationale", ""),
    }
    
    # Write data.json
    print("      [step 6] Writing data.json...")
    try:
        with open(DATA_PATH) as f:
            existing = json.load(f)
    except Exception:
        existing = {}
    
    existing["weekly_pick"] = weekly_pick
    existing["generated_at"] = datetime.now().isoformat()
    
    with open(DATA_PATH, "w") as f:
        json.dump(existing, f, indent=2, default=str)
    
    # Write standalone cache
    cache_path = CACHE_DIR / "weekly_pick_cache.json"
    with open(cache_path, "w") as f:
        json.dump(weekly_pick, f, indent=2, default=str)
    
    print(f"      [DONE] Top pick: {top_pick['ticker']} ({top_pick.get('name','')}) — Score {top_pick['score']}")
    print(f"      [DONE] Written to {DATA_PATH}")
    
    # Sentiment flag
    if top_sent and total_mentions > 0:
        print(f"      [SENTIMENT] Final sentiment: {top_sent.get('sentiment_score',0):.0f}/100, "
              f"polarity={top_sent.get('polarity',0):+.2f}, mentions={total_mentions}")


if __name__ == "__main__":
    asyncio.run(main())
