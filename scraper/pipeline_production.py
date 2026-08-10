#!/usr/bin/env python3
"""
Production Weekly Pick Pipeline — Full Universe Analysis

SIGNAL WEIGHTS:
  40% Technical    — RSI, SMA crossover, MACD, Bollinger, volume
  30% Momentum     — Weekly/monthly performance, trend alignment
  20% Sentiment    — News headline bullish/bearish keyword scan
  10% Volatility   — Risk-adjusted returns, max drawdown

OUTPUT: data.json['weekly_pick'] with full breakdown
"""
import asyncio
import json
import re
import statistics
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

import yfinance as yf

ROOT = Path(__file__).resolve().parent.parent
DATA_PATH = ROOT / "data.json"
CACHE_DIR = ROOT / ".cache"

# ─── Sentiment dictionaries ──────────────────────────────────────────
BULLISH = {"buy","bullish","strong","growth","moon","rocket","surge","rally","breakout","pump","tendies","diamond hands","hodl","hold","accumulate","outperform","upgrade","beat","raised","conviction","bull case","upside","accelerating","booming","rip","squeeze","short squeeze","gamma","degen","ape","yolo","calls","leaps","long","added","buying","pumping","juicy","undervalued","discount","cheap","opportunity","loading","analyst upgrade","price target raised","overweight","top pick","top rated","buy rating","strong buy","pile in","front run","accumulation","whale","institutional buying","pivot","recovery","bounce","support held","bottom","reversal up","beat earnings","crushed earnings","guidance raised","raised outlook","partnership","contract win","fda approval","breakthrough","rises","rallies","gains","soars","jumps","climbs","advances","higher","beat expectations","record high","all time high","🚀","💎","🙌","🌙"}
BEARISH = {"sell","bearish","weak","dump","crash","dumping","panic","bear","recession","sell off","selloff","correction","downgrade","miss","underperform","cut","lowered","put","short","shorting","puts","overvalued","expensive","bubble","topping","reversal down","pullback","decline","falling","dropping","tank","plunge","nosedive","faded","paper hands","selling","sold","trimmed","out","exit","avoid","stay away","rug pull","scam","dead","analyst downgrade","price target cut","bear case","underweight","lowered to","warning","concern","risk","fear","caution","negative","pessimistic","slowing","disappointing","below expectations","missed earnings","revenue miss","guidance cut","bear flag","head and shoulders","distribution","resistance","rejected","failed breakout","lower high","death cross","bankruptcy","layoffs","investigation","sec probe","lawsuit","drops","declines","falls","plunges","tumbles","sinks","dumps","bear market","inflation","layoff","fraud","probe","litigation","fine","penalty","🐻"}

# ─── Technical functions ─────────────────────────────────────────────

def rsi(closes, period=14):
    if len(closes) < period + 1: return None
    gains, losses = [], []
    for i in range(1, period+1):
        d = closes[i] - closes[i-1]
        gains.append(max(d, 0)); losses.append(max(-d, 0))
    ag = sum(gains)/period; al = sum(losses)/period
    if al == 0: return 100.0
    return 100 - (100 / (1 + ag/al))

def sma(closes, period):
    if len(closes) < period: return None
    return sum(closes[-period:])/period

def macd(closes):
    if len(closes) < 26: return None, None
    def ema(p, n):
        mult = 2/(n+1)
        e = [p[0]]
        for pr in p[1:]:
            e.append((pr - e[-1])*mult + e[-1])
        return e
    e12, e26 = ema(closes, 12), ema(closes, 26)
    m = [e12[i]-e26[i] for i in range(len(e26))]
    s = ema(m, 9)
    return m[-1], m[-1] - s[-1]

def bollinger(closes):
    if len(closes) < 20: return None, None, None
    s = sum(closes[-20:])/20
    std = statistics.stdev(closes[-20:])
    return s + 2*std, s - 2*std, s

def vol_score(closes):
    if len(closes) < 10: return 50, "insufficient data"
    rets = [(closes[i]-closes[i-1])/abs(closes[i-1]) for i in range(1, min(21, len(closes))) if closes[i-1] != 0]
    if not rets: return 50, "no returns"
    vol = statistics.stdev(rets)*(252**0.5)*100
    peak, dd = max(closes), 0
    if peak > 0: dd = (peak - closes[-1])/peak*100
    score = 50
    if vol < 15: score += 15; msg = f"low vol {vol:.0f}%"
    elif vol < 25: score += 5; msg = f"moderate vol {vol:.0f}%"
    elif vol < 35: score -= 5; msg = f"elevated vol {vol:.0f}%"
    else: score -= 15; msg = f"high vol {vol:.0f}%"
    if dd < 3: score += 10; msg += ", near highs"
    elif dd > 15: score -= 10; msg += f", deep dd {dd:.0f}%"
    elif dd > 8: score -= 3; msg += f", dd {dd:.0f}%"
    return max(0, min(100, score)), msg

# ─── Fetchers ────────────────────────────────────────────────────────

def fetch_yf(ticker, days=50):
    """Sync fetch via yfinance."""
    try:
        hist = yf.Ticker(ticker).history(period=f"{max(days, 60)}d", interval="1d")
        if hist.empty or len(hist) < 20:
            return None
        closes = [float(c) for c in hist["Close"].dropna().tolist()[-days:]]
        volumes = [float(v) for v in hist["Volume"].dropna().tolist()[-days:]] if "Volume" in hist else []
        return {"closes": closes, "volumes": volumes, "latest": closes[-1]}
    except Exception:
        return None

async def fetch_batch(tickers, workers=8):
    """Async parallel fetch."""
    results = {}
    loop = asyncio.get_event_loop()
    sem = asyncio.Semaphore(workers)
    
    async def _one(t):
        async with sem:
            return await loop.run_in_executor(None, fetch_yf, t, 50)
    
    for i in range(0, len(tickers), workers*3):
        batch = tickers[i:i+workers*3]
        outs = await asyncio.gather(*[_one(t) for t in batch])
        for t, d in zip(batch, outs):
            if d: results[t] = d
        if i % 200 == 0:
            print(f"      [fetch] {min(i+len(batch), len(tickers))}/{len(tickers)}, valid={len(results)}")
    
    print(f"      [fetch] Final: {len(results)}/{len(tickers)} valid")
    return results

# ─── Sentiment fetch ─────────────────────────────────────────────────

def fetch_sentiment(tickers):
    """Scan yfinance news headlines for sentiment keywords."""
    results = {}
    for ticker in tickers:
        try:
            news = yf.Ticker(ticker).news
            if not news or len(news) == 0:
                continue
            bull, bear = 0, 0
            for item in news[:8]:
                text = (item.get("title","") + " " + item.get("summary","")).lower()
                b = sum(1 for term in BULLISH if term in text)
                be = sum(1 for term in BEARISH if term in text)
                if b > be: bull += 1
                elif be > b: bear += 1
            score = 50 + (bull - bear) * 12 if (bull + bear) > 0 else 50
            score = max(0, min(100, score))
            results[ticker] = {"score": score, "bull": bull, "bear": bear}
        except Exception:
            pass
    return results

# ─── Scoring engine ──────────────────────────────────────────────────

def score_asset(ticker, info, data, sent):
    closes, volumes = data["closes"], data.get("volumes", [])
    p = closes[-1]
    week = (closes[-1] - closes[-5])/abs(closes[-5])*100 if len(closes) >= 5 and closes[-5] != 0 else 0
    month = (closes[-1] - closes[-min(20, len(closes))])/abs(closes[-min(20, len(closes))])*100 if len(closes) >= 20 else 0
    
    # Technical score
    ts, tf = 40, []
    r = rsi(closes)
    if r:
        if 50 <= r <= 65: ts += 12; tf.append(f"RSI {r:.0f} bullish")
        elif r > 65 and r <= 75: ts += 8; tf.append(f"RSI {r:.0f} strong")
        elif r > 75: ts += 3; tf.append(f"RSI {r:.0f} overbought")
        elif r < 35: ts -= 5; tf.append(f"RSI {r:.0f} oversold")
    
    s20 = sma(closes, 20)
    s50 = sma(closes, 50) if len(closes) >= 50 else None
    if s20:
        if p > s20 * 1.03: ts += 10; tf.append("well above SMA20")
        elif p > s20 * 1.01: ts += 5; tf.append("above SMA20")
        elif p < s20 * 0.97: ts -= 5; tf.append("below SMA20")
    if s50 and s20 and s20 > s50 * 1.01: ts += 8; tf.append("golden cross")
    elif s50 and s20 and s20 < s50 * 0.99: ts -= 5; tf.append("death cross")
    
    m, mh = macd(closes)
    if m and mh:
        if mh > 0 and m > 0: ts += 8; tf.append("MACD bullish")
        elif mh < 0: ts -= 3; tf.append("MACD weakening")
    
    bu, bl, bm = bollinger(closes)
    if bu and p > bu * 0.98: ts += 3; tf.append("near upper BB")
    elif bl and p < bl * 1.02: ts -= 2; tf.append("near lower BB")
    
    # Volume confirmation
    if len(volumes) >= 20 and len(closes) >= 20:
        v5 = sum(volumes[-5:])/5
        v20 = sum(volumes[-20:])/20
        up = closes[-1] > closes[-5]
        if v5 > v20 * 1.2 and up: ts += 5; tf.append("volume confirming")
        elif v5 > v20 * 1.2 and not up: ts -= 3; tf.append("volume distribution")
    
    ts = max(0, min(100, ts))
    
    # Momentum score
    ms, mf = 40, []
    if week >= 5: ms += 20; mf.append(f"+{week:.1f}% week — strong momentum")
    elif week >= 2: ms += 10; mf.append(f"+{week:.1f}% week")
    elif week >= 0.5: ms += 5; mf.append(f"+{week:.1f}% week")
    elif week <= -5: ms -= 15; mf.append(f"{week:.1f}% week — breakdown")
    elif week <= -2: ms -= 8; mf.append(f"{week:.1f}% week")
    
    if month >= 10: ms += 15; mf.append(f"+{month:.1f}% month — powerful")
    elif month >= 5: ms += 8; mf.append(f"+{month:.1f}% month")
    elif month <= -10: ms -= 10; mf.append(f"{month:.1f}% month — correction")
    elif month <= -5: ms -= 5; mf.append(f"{month:.1f}% month")
    
    if len(closes) >= 20:
        ma5 = sum(closes[-5:])/5
        ma20 = sum(closes[-20:])/20
        if ma5 > ma20 * 1.02: ms += 10; mf.append("5d > 20d — accelerating")
        elif ma5 < ma20 * 0.98: ms -= 5; mf.append("5d < 20d — decelerating")
    
    ms = max(0, min(100, ms))
    
    # Volatility score
    vs, vm = vol_score(closes)
    vf = [vm]
    
    # Sentiment
    ss = 50
    sf = ["no sentiment data"]
    if sent and ticker in sent:
        s = sent[ticker]
        ss = s["score"]
        sf = [f"news sentiment {ss:.0f}/100 ({s['bull']} bull, {s['bear']} bear)"]
    
    # Combined weighted
    combined = ts * 0.40 + ms * 0.30 + vs * 0.10 + ss * 0.20
    cat = info.get("category", "Stock")
    if cat in {"ETF", "Crypto ETF"}: combined += 1
    
    return {
        "ticker": ticker,
        "name": info.get("name", ticker),
        "category": cat,
        "price": round(p, 2),
        "change_7d": round(week, 2),
        "change_30d": round(month, 2),
        "rsi": round(r, 1) if r else None,
        "sma20": round(s20, 2) if s20 else None,
        "score": round(combined, 1),
        "technical": round(ts, 1),
        "momentum": round(ms, 1),
        "sentiment": round(ss, 1),
        "volatility": round(vs, 1),
        "factors": tf + mf + vf + sf,
    }

# ─── Main ────────────────────────────────────────────────────────────

async def run():
    print(f"[pipeline] Starting at {datetime.now().strftime('%a %b %d %H:%M')}")
    
    # Load universe
    universe_file = CACHE_DIR / "universe.json"
    if not universe_file.exists():
        print("[pipeline] ERROR: universe.json not found. Run build_universe.py first.")
        return None
    
    with open(universe_file) as f:
        universe = json.load(f)
    
    print(f"[pipeline] Universe: {len(universe)} assets")
    tickers = list(universe.keys())
    
    # Fetch prices
    print(f"[pipeline] Fetching prices...")
    prices = await fetch_batch(tickers, workers=8)
    
    if not prices:
        print("[pipeline] ERROR: No prices fetched")
        return None
    
    # Fetch sentiment for valid tickers
    print(f"[pipeline] Fetching sentiment for {min(len(prices), 30)} top candidates...")
    sentiment = fetch_sentiment(list(prices.keys())[:30])
    
    # Score all
    print(f"[pipeline] Scoring {len(prices)} assets...")
    results = []
    for ticker, data in prices.items():
        info = universe.get(ticker, {"name": ticker, "category": "Stock"})
        scored = score_asset(ticker, info, data, sentiment)
        results.append(scored)
    
    results.sort(key=lambda x: x["score"], reverse=True)
    
    top = results[0]
    top5 = results[:5]
    
    # Build rationale
    rationale = (
        f"**HIGHEST CONVICTION: {top['name']} ({top['ticker']})** — ${top['price']}\n\n"
        f"Combined score: **{top['score']}/100** (analyzed {len(results)} assets).\n\n"
        f"**Signal Breakdown:**\n"
        f"• Technical: {top['technical']}/100 (RSI, trend, volume)\n"
        f"• Momentum: {top['momentum']}/100 ({top['change_7d']:+.1f}% week, {top['change_30d']:+.1f}% month)\n"
        f"• Sentiment: {top['sentiment']}/100 (news scan)\n"
        f"• Volatility: {top['volatility']}/100 (risk-adjusted)\n\n"
        f"**Key Drivers:**\n" + "\n".join(f"• {f}" for f in top['factors'][:6]) + "\n\n"
        f"**Trade Plan:**\n"
        f"Entry: Current levels or pullback to SMA20 (${top['sma20']:.2f}).\n"
        f"Stop: Daily close below SMA20 or -5% from entry.\n"
        f"Target: Measured move continuation.\n\n"
        f"*Not financial advice. DYOR.*"
    )
    
    weekly_pick = {
        "generated_at": datetime.now().isoformat(),
        "week_label": datetime.now().strftime("Week of %b %d, %Y"),
        "top_pick": {
            "name": top["ticker"],
            "display_name": top["name"],
            "price": top["price"],
            "signal": "BULLISH" if top["score"] > 65 else "NEUTRAL-BULLISH" if top["score"] > 55 else "NEUTRAL",
            "score": top["score"],
            "rationale": rationale,
            "key_levels": f"Support: ${top['sma20']:.2f}" if top.get('sma20') else "Watch SMA20",
            "timeframe": "Swing (1-4 weeks)",
            "factors": top["factors"],
            "sub_scores": {
                "technical": top["technical"],
                "momentum": top["momentum"],
                "sentiment": top["sentiment"],
                "volatility": top["volatility"],
            },
            "sentiment_score": top["sentiment"],
        },
        "top_five": [
            {"ticker": r["ticker"], "name": r["name"], "category": r["category"],
             "score": r["score"], "price": r["price"], "change_7d": r["change_7d"],
             "change_30d": r["change_30d"]}
            for r in top5
        ],
        "all_assets": results[:20],
        "rationale": rationale,
        "meta": {
            "total_analyzed": len(results),
            "universe_size": len(universe),
            "weights": {"technical": 0.40, "momentum": 0.30, "sentiment": 0.20, "volatility": 0.10},
        }
    }
    
    # Write
    try:
        with open(DATA_PATH) as f:
            existing = json.load(f)
    except:
        existing = {}
    existing["weekly_pick"] = weekly_pick
    existing["generated_at"] = datetime.now().isoformat()
    with open(DATA_PATH, "w") as f:
        json.dump(existing, f, indent=2, default=str)
    with open(CACHE_DIR / "weekly_pick_cache.json", "w") as f:
        json.dump(weekly_pick, f, indent=2, default=str)
    
    print(f"\n{'='*60}")
    print(f"🏆 TOP PICK: {top['ticker']} ({top['name']})")
    print(f"📊 Score: {top['score']}/100 | Technical: {top['technical']} | Momentum: {top['momentum']}")
    print(f"💰 ${top['price']} | Week: {top['change_7d']:+.1f}% | Month: {top['change_30d']:+.1f}%")
    print(f"🥈 Top 5: {[r['ticker'] for r in top5]}")
    print(f"{'='*60}")
    
    return weekly_pick

if __name__ == "__main__":
    r = asyncio.run(run())
    sys.exit(0 if r else 1)
