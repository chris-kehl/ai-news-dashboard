#!/usr/bin/env python3
"""Advanced tech-sector analysis: earnings + technicals + sentiment scoring.

Reads ALPHA_VANTAGE_API_KEY from environment (loaded by run_scraper.sh).
Fetches earnings, SMA(20), RSI(14), MACD, and latest quote for top 10 tech tickers.
Generates composite 0-100 score and BUY/SELL/NEUTRAL signals.

Tickers: AAPL, AMZN, MSFT, NVDA, GOOGL, META, TSLA, AMD, AVGO, NFLX
"""
import json
import os
import time
from datetime import datetime
import requests

AV_KEY = os.getenv("ALPHA_VANTAGE_API_KEY", "")
BASE = "https://www.alphavantage.co/query"
TECH_TICKERS = ["AAPL", "AMZN", "MSFT", "NVDA", "GOOGL", "META", "TSLA", "AMD", "AVGO", "NFLX"]
RATE_LIMIT_DELAY = 13  # free tier: 5 calls/min


def av_get(params):
    params["apikey"] = AV_KEY
    try:
        r = requests.get(BASE, params=params, timeout=30)
        data = r.json()
        if "Note" in data or "Information" in data:
            print("      AV rate limit: " + str(data.get("Note", data.get("Information", "")))[:60])
            return {}
        return data
    except Exception as e:
        print(f"      AV error: {e}")
        return {}


def fetch_earnings(ticker):
    data = av_get({"function": "EARNINGS", "symbol": ticker})
    q = data.get("quarterlyEarnings", [])
    if not q:
        return {}
    latest = q[0]
    prev = q[1] if len(q) > 1 else {}
    return {
        "reported_eps": latest.get("reportedEPS"),
        "estimated_eps": latest.get("estimatedEPS"),
        "surprise_pct": latest.get("surprisePercentage"),
        "report_date": latest.get("fiscalDateEnding"),
        "prev_surprise_pct": prev.get("surprisePercentage"),
    }


def fetch_technicals(ticker):
    results = {}
    # SMA(20)
    sma = av_get({
        "function": "SMA", "symbol": ticker, "interval": "daily",
        "time_period": "20", "series_type": "close",
    })
    ss = sma.get("Technical Analysis: SMA", {})
    if ss:
        ld = max(ss.keys())
        results["sma20"] = float(ss[ld]["SMA"])
    # RSI(14)
    rsi = av_get({
        "function": "RSI", "symbol": ticker, "interval": "daily",
        "time_period": "14", "series_type": "close",
    })
    rs = rsi.get("Technical Analysis: RSI", {})
    if rs:
        ld = max(rs.keys())
        results["rsi14"] = float(rs[ld]["RSI"])
    # MACD
    macd = av_get({
        "function": "MACD", "symbol": ticker, "interval": "daily",
        "series_type": "close", "fastperiod": "12", "slowperiod": "26", "signalperiod": "9",
    })
    ms = macd.get("Technical Analysis: MACD", {})
    if ms:
        ld = max(ms.keys())
        m = ms[ld]
        results["macd"] = float(m["MACD"])
        results["macd_signal"] = float(m["MACD_Signal"])
        results["macd_hist"] = float(m["MACD_Hist"])
    # Quote
    quote = av_get({"function": "GLOBAL_QUOTE", "symbol": ticker})
    gq = quote.get("Global Quote", {})
    if gq:
        results["price"] = float(gq.get("05. price", 0))
        results["change_pct"] = float(gq.get("10. change percent", "0").replace("%", ""))
    return results


def compute_score(ticker, earnings, tech):
    score = 50
    factors = []

    # Technicals (40 pts max)
    tech_score = 0
    if tech.get("sma20") and tech.get("price"):
        if tech["price"] > tech["sma20"]:
            tech_score += 15
            factors.append("price > SMA20")
        else:
            tech_score -= 10
            factors.append("price < SMA20")

    if tech.get("rsi14") is not None:
        rsi = tech["rsi14"]
        if 50 < rsi < 70:
            tech_score += 15
            factors.append(f"RSI {rsi:.1f} bullish zone")
        elif rsi > 70:
            tech_score += 5
            factors.append(f"RSI {rsi:.1f} overbought")
        elif 30 < rsi < 50:
            tech_score -= 5
            factors.append(f"RSI {rsi:.1f} weak")
        else:
            tech_score -= 15
            factors.append(f"RSI {rsi:.1f} oversold")

    if tech.get("macd_hist") is not None:
        if tech["macd_hist"] > 0:
            tech_score += 10
            factors.append("MACD bullish cross")
        else:
            tech_score -= 10
            factors.append("MACD bearish")

    score += tech_score * 0.4

    # Earnings (30 pts max)
    earn_score = 0
    if earnings.get("surprise_pct"):
        sp = float(earnings["surprise_pct"])
        if sp > 5:
            earn_score = 25
            factors.append(f"earnings beat +{sp}%")
        elif sp > 0:
            earn_score = 15
            factors.append(f"earnings beat +{sp}%")
        elif sp > -5:
            earn_score = -5
            factors.append(f"earnings miss {sp}%")
        else:
            earn_score = -20
            factors.append(f"earnings miss {sp}%")
        if earnings.get("prev_surprise_pct"):
            ps = float(earnings["prev_surprise_pct"])
            if ps > 0 and earn_score > 0:
                earn_score += 5
                factors.append("back-to-back beats")

    score += earn_score * 0.3

    # Price action (30 pts)
    price_score = 0
    if tech.get("change_pct") is not None:
        chg = tech["change_pct"]
        if chg > 2:
            price_score = 15
            factors.append(f"+{chg:.1f}% today")
        elif chg > 0.5:
            price_score = 10
            factors.append(f"+{chg:.1f}% today")
        elif chg > -0.5:
            price_score = 0
            factors.append(f"flat ({chg:+.1f}%)")
        elif chg > -2:
            price_score = -10
            factors.append(f"{chg:.1f}% down")
        else:
            price_score = -15
            factors.append(f"{chg:.1f}% selloff")

    score += price_score * 0.3
    score = max(0, min(100, round(score, 1)))

    if score >= 65:
        signal, color = "STRONG BUY", "#00c853"
    elif score >= 55:
        signal, color = "BUY", "#00e676"
    elif score >= 45:
        signal, color = "NEUTRAL", "#ffd600"
    elif score >= 35:
        signal, color = "SELL", "#ff5252"
    else:
        signal, color = "STRONG SELL", "#d50000"

    return {
        "ticker": ticker,
        "score": score,
        "signal": signal,
        "color": color,
        "factors": factors,
        "earnings": earnings,
        "technicals": {k: v for k, v in tech.items() if k not in ("price", "change_pct")},
        "price": tech.get("price"),
        "change_pct": tech.get("change_pct"),
    }


def get_tech_analysis():
    if not AV_KEY:
        print("      ALPHA_VANTAGE_API_KEY missing — skipping tech analysis")
        return {}

    results = []
    print("      Fetching tech analysis (Alpha Vantage)...")

    for i, ticker in enumerate(TECH_TICKERS):
        print(f"      [{i+1}/{len(TECH_TICKERS)}] {ticker} ...", end=" ")
        try:
            earnings = fetch_earnings(ticker)
            time.sleep(RATE_LIMIT_DELAY)
            tech = fetch_technicals(ticker)
            time.sleep(RATE_LIMIT_DELAY)
            sd = compute_score(ticker, earnings, tech)
            results.append(sd)
            print(f"score={sd['score']} {sd['signal']}")
        except Exception as e:
            print(f"ERROR: {e}")

    if not results:
        return {}

    results.sort(key=lambda x: x["score"], reverse=True)
    avg = round(sum(r["score"] for r in results) / len(results), 1)
    bull = sum(1 for r in results if r["score"] >= 55)
    bear = sum(1 for r in results if r["score"] <= 45)
    tone = (
        "BULLISH" if avg >= 60
        else "CAUTIOUSLY BULLISH" if avg >= 50
        else "NEUTRAL" if avg >= 40
        else "BEARISH"
    )

    return {
        "generated_at": datetime.now().isoformat(),
        "avg_score": avg,
        "tone": tone,
        "bullish_count": bull,
        "bearish_count": bear,
        "tickers": results,
        "top_picks": [r["ticker"] for r in results[:3] if r["score"] >= 55],
    }


if __name__ == "__main__":
    result = get_tech_analysis()
    print(json.dumps(result, indent=2))
