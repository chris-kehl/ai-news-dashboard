#!/usr/bin/env python3
"""Minimal Monday pick generator — uses yfinance with polite delays."""
import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
import time
import sys

import yfinance as yf

ROOT = Path(__file__).resolve().parent.parent
DATA_PATH = ROOT / "data.json"

# Focused universe — liquid, reliable tickers
LIQUID_UNIVERSE = {
    # Core US equity
    "SPY": "SPDR S&P 500 ETF",
    "QQQ": "Invesco QQQ Trust",
    "IWM": "iShares Russell 2000 ETF",
    "DIA": "SPDR Dow Jones ETF",
    "VTI": "Vanguard Total Stock Market",
    # Sectors
    "XLF": "Financial Select Sector",
    "XLK": "Technology Select Sector",
    "XLE": "Energy Select Sector",
    "XLI": "Industrials Select Sector",
    "XLV": "Health Care Select Sector",
    "XLP": "Consumer Staples Select",
    "XLY": "Consumer Discretionary",
    "XLB": "Materials Select Sector",
    "XLRE": "Real Estate Select Sector",
    "XLU": "Utilities Select Sector",
    # Other major ETFs
    "IBB": "iShares Nasdaq Biotech",
    "SMH": "VanEck Semiconductors",
    "SOXX": "iShares Semiconductors",
    "ARKK": "ARK Innovation ETF",
    "ARKB": "ARK 21Shares Bitcoin",
    # International
    "ACWX": "iShares MSCI ACWI ex US",
    "IEFA": "iShares Core MSCI EAFE",
    "EEM": "iShares MSCI Emerging Mkts",
    "EMXC": "iShares EM ex China",
    "INDA": "iShares MSCI India",
    "EWZ": "iShares MSCI Brazil",
    # Commodities / metals
    "GLD": "SPDR Gold Trust",
    "SLV": "iShares Silver Trust",
    "USO": "United States Oil Fund",
    # Bonds
    "TLT": "iShares 20+ Year Treasury",
    "HYG": "iShares High Yield Corp Bond",
    "LQD": "iShares Inv Grade Corp Bond",
    "BND": "Vanguard Total Bond Market",
    "SCHD": "Schwab US Dividend Equity",
    # Crypto
    "BTC-USD": "Bitcoin",
    "ETH-USD": "Ethereum",
    "SOL-USD": "Solana",
    "ADA-USD": "Cardano",
    "XRP-USD": "XRP",
    "LINK-USD": "Chainlink",
    "DOGE-USD": "Dogecoin",
    # Crypto ETFs
    "IBIT": "iShares Bitcoin Trust",
    "FBTC": "Fidelity Wise Origin Bitcoin",
    "BITO": "ProShares Bitcoin Strategy",
    "ETHE": "Grayscale Ethereum Trust",
    "ETHA": "iShares Ethereum Trust",
}


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
    rsi = 100 - (100 / (1 + avg_gain / avg_loss))
    return rsi


def calc_sma(closes, period):
    if len(closes) < period:
        return None
    return sum(closes[-period:]) / period


def analyze(closes, name, cat):
    if not closes or len(closes) < 14:
        return None
    price = closes[-1]
    week = (closes[-1] - closes[-5]) / abs(closes[-5]) * 100 if len(closes) >= 5 and closes[-5] != 0 else 0
    month = (closes[-1] - closes[-min(20, len(closes))]) / abs(closes[-min(20, len(closes))]) * 100 if len(closes) >= 20 else 0
    rsi = calc_rsi(closes)
    sma20 = calc_sma(closes, 20)
    
    score = 50
    factors = []
    
    if week >= 3:
        score += 10; factors.append(f"+{week:.1f}% week")
    elif week >= 1:
        score += 5; factors.append(f"+{week:.1f}% week")
    elif week <= -3:
        score -= 10; factors.append(f"{week:.1f}% week")
    
    if month >= 5:
        score += 10; factors.append(f"+{month:.1f}% month")
    elif month >= 2:
        score += 5; factors.append(f"+{month:.1f}% month")
    elif month <= -5:
        score -= 5; factors.append(f"{month:.1f}% month")
    
    if rsi:
        if 50 <= rsi <= 70:
            score += 5; factors.append(f"RSI {rsi:.0f} positive")
        elif rsi > 70:
            score += 2; factors.append(f"RSI {rsi:.0f} strong")
        elif rsi < 30:
            score -= 5; factors.append(f"RSI {rsi:.0f} oversold")
    
    if sma20 and price > sma20 * 1.02:
        score += 5; factors.append("above SMA20")
    elif sma20 and price < sma20 * 0.98:
        score -= 3; factors.append("below SMA20")
    
    if cat == "ETF":
        score += 2; factors.append("ETF trend strength")
    
    return {
        "ticker": name,
        "name": LIQUID_UNIVERSE.get(name, name),
        "category": cat,
        "price": round(price, 2),
        "change_7d": round(week, 2),
        "change_30d": round(month, 2),
        "rsi": round(rsi, 1) if rsi else None,
        "sma20": round(sma20, 2) if sma20 else None,
        "score": max(min(score, 99), 1),
        "factors": factors,
    }


def fetch_one(ticker):
    try:
        t = yf.Ticker(ticker)
        data = t.history(period="3mo", interval="1d")
        if data.empty:
            return None
        closes = data["Close"].dropna().tolist()
        return [float(c) for c in closes] if len(closes) >= 14 else None
    except Exception:
        return None


async def main():
    print(f"[minimal_pick] Running at {datetime.now().strftime('%H:%M')}")
    print(f"[minimal_pick] Universe: {len(LIQUID_UNIVERSE)} tickers")
    
    # Fetch with polite delays via threadpool
    results = {}
    loop = asyncio.get_event_loop()
    
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {t: loop.run_in_executor(pool, fetch_one, t) for t in LIQUID_UNIVERSE}
        for t, fut in futures.items():
            closes = await fut
            if closes:
                cat = "Crypto" if "-USD" in t else "Crypto ETF" if t in {"IBIT","FBTC","BITO","ETHE","ETHA","ARKB"} else "ETF"
                result = analyze(closes, t, cat)
                if result:
                    results[t] = result
            await asyncio.sleep(0.3)  # polite
    
    print(f"[minimal_pick] Fetched {len(results)}/{len(LIQUID_UNIVERSE)} tickers")
    
    if not results:
        print("[minimal_pick] ERROR: no results")
        return
    
    # Rank
    ranked = sorted(results.values(), key=lambda x: x["score"], reverse=True)
    top = ranked[0]
    top5 = ranked[:5]
    
    week_label = datetime.now().strftime("Week of %b %d, %Y")
    
    # Build rationales
    for r in ranked:
        r["rationale"] = f"Scored {r['score']}/100 — " + ", ".join(r["factors"][:4])
    
    # Top pick full rationale
    top_rationale = (
        f"**HIGHEST CONVICTION: {top['name']} ({top['ticker']})** — ${top['price']}\n\n"
        f"{top['name']} scores {top['score']}/100 — the strongest setup across {len(results)} tracked assets this week.\n\n"
        f"Key drivers: {', '.join(top['factors'][:4])}.\n\n"
        f"Entry: Current levels or pullback to SMA20. Stop: Daily close below SMA20. "
        f"Target: Upside continuation.\n\n"
        f"*Not financial advice. DYOR.*"
    )
    
    weekly_pick = {
        "generated_at": datetime.now().isoformat(),
        "week_label": week_label,
        "top_pick": {
            "name": top["ticker"],
            "display_name": top["name"],
            "price": top["price"],
            "signal": "BULLISH" if top["score"] > 60 else "NEUTRAL",
            "score": top["score"],
            "rationale": top_rationale,
            "key_levels": f"Support: ${top['sma20']}" if top.get('sma20') else "Watch SMA20",
            "timeframe": "Swing (1-4 weeks)",
            "factors": top["factors"],
            "sentiment_score": None,
            "mention_count": None,
        },
        "top_five": [
            {"ticker": r["ticker"], "name": r["name"], "category": r["category"],
             "score": r["score"], "price": r["price"],
             "change_7d": r["change_7d"], "change_30d": r["change_30d"]}
            for r in top5
        ],
        "all_assets": ranked[:15],
        "rationale": top_rationale,
    }
    
    # Merge into data.json
    try:
        with open(DATA_PATH) as f:
            existing = json.load(f)
    except Exception:
        existing = {}
    
    existing["weekly_pick"] = weekly_pick
    existing["generated_at"] = datetime.now().isoformat()
    
    with open(DATA_PATH, "w") as f:
        json.dump(existing, f, indent=2, default=str)
    
    print(f"[minimal_pick] TOP PICK: {top['ticker']} ({top['name']}) — Score {top['score']}")
    print(f"[minimal_pick] Written to {DATA_PATH}")


if __name__ == "__main__":
    asyncio.run(main())
