#!/usr/bin/env python3
"""
Advanced tech-sector analysis: earnings + technicals + sentiment scoring.

Uses Yahoo Finance FREE endpoints (no API key needed).
Fetches 60 days of OHLCV history, computes SMA(20), RSI(14), MACD,
gets earnings history, latest quote, and generates composite 0-100 scores.

Tickers: AAPL, AMZN, MSFT, NVDA, GOOGL, META, TSLA, AMD, AVGO, NFLX
"""
import json
import requests
import time
from datetime import datetime

TECH_TICKERS = ["AAPL", "AMZN", "MSFT", "NVDA", "GOOGL", "META", "TSLA", "AMD", "AVGO", "NFLX"]
RATE_LIMIT_DELAY = 2  # Yahoo is tolerant but be polite


def yf_chart(ticker, range_days=60):
    """Fetch daily OHLCV from Yahoo Finance v8 chart API. No key needed."""
    url = (
        f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
        f"?interval=1d&range={range_days}d"
    )
    try:
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=20)
        data = r.json()
        result = data.get("chart", {}).get("result", [])
        if not result:
            return []
        timestamps = result[0].get("timestamp", [])
        quote = result[0].get("indicators", {}).get("quote", [{}])[0]
        closes = quote.get("close", [])
        volumes = quote.get("volume", [])
        out = []
        for i in range(len(timestamps)):
            if closes[i] is not None:
                out.append({
                    "date": datetime.fromtimestamp(timestamps[i]).strftime("%Y-%m-%d"),
                    "close": float(closes[i]),
                    "volume": int(volumes[i]) if volumes[i] else 0,
                })
        return out
    except Exception as e:
        print(f"      YF chart error for {ticker}: {e}")
        return []


def yf_quote(ticker):
    """Fetch latest quote from Yahoo Finance. No key needed."""
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1d&range=1d"
    try:
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=20)
        data = r.json()
        result = data.get("chart", {}).get("result", [])
        if not result:
            return {}
        meta = result[0].get("meta", {})
        if meta.get("chartPreviousClose"):
            chg = ((meta.get("regularMarketPrice", 0) - meta.get("chartPreviousClose", 0))
                   / meta.get("chartPreviousClose", 1) * 100)
        else:
            chg = 0
        return {
            "price": meta.get("regularMarketPrice"),
            "prev_close": meta.get("chartPreviousClose"),
            "change_pct": chg,
        }
    except Exception as e:
        print(f"      YF quote error for {ticker}: {e}")
        return {}


def yf_earnings(ticker):
    """Fetch earnings history from Yahoo Finance. No key needed."""
    url = (
        f"https://query2.finance.yahoo.com/v10/finance/quoteSummary/{ticker}"
        f"?modules=earningsHistory"
    )
    try:
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=20)
        data = r.json()
        hist = (
            data.get("quoteSummary", {}).get("result", [{}])[0]
            .get("earningsHistory", {}).get("history", [])
        )
        if not hist:
            return {}
        latest = hist[0]
        prev = hist[1] if len(hist) > 1 else {}
        eps = latest.get("epsActual", {}).get("raw")
        est = latest.get("epsEstimate", {}).get("raw")
        surprise = latest.get("surprisePercent", {}).get("raw")
        prev_surprise = prev.get("surprisePercent", {}).get("raw")
        return {
            "reported_eps": round(eps, 2) if eps else None,
            "estimated_eps": round(est, 2) if est else None,
            "surprise_pct": round(surprise * 100, 2) if surprise else None,
            "report_date": latest.get("quarter", {}).get("fmt", ""),
            "prev_surprise_pct": round(prev_surprise * 100, 2) if prev_surprise else None,
        }
    except Exception as e:
        print(f"      YF earnings error for {ticker}: {e}")
        return {}


def calc_sma(prices, period=20):
    if len(prices) < period:
        return None
    return sum(p["close"] for p in prices[-period:]) / period


def calc_rsi(prices, period=14):
    if len(prices) < period + 1:
        return None
    gains, losses = [], []
    for i in range(1, period + 1):
        change = prices[-i]["close"] - prices[-(i + 1)]["close"]
        gains.append(max(change, 0))
        losses.append(abs(min(change, 0)))
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def calc_macd(prices):
    """Calculate MACD using EMA(12), EMA(26), signal EMA(9)."""
    closes = [p["close"] for p in prices]
    if len(closes) < 26:
        return None, None, None

    def ema(data, period):
        multiplier = 2 / (period + 1)
        ema_values = [sum(data[:period]) / period]
        for price in data[period:]:
            ema_values.append((price - ema_values[-1]) * multiplier + ema_values[-1])
        return ema_values

    ema12 = ema(closes, 12)
    ema26 = ema(closes, 26)
    macd_line = [e12 - e26 for e12, e26 in zip(ema12[-len(ema26):], ema26)]
    signal_line = ema(macd_line, 9)
    histogram = [m - s for m, s in zip(macd_line[-len(signal_line):], signal_line)]

    return macd_line[-1], signal_line[-1], histogram[-1]


def fetch_technicals(ticker):
    """Fetch history + quote, compute SMA/RSI/MACD."""
    hist = yf_chart(ticker, range_days=60)
    time.sleep(RATE_LIMIT_DELAY)
    quote = yf_quote(ticker)

    if not hist:
        return quote

    results = dict(quote)
    sma20 = calc_sma(hist, 20)
    rsi14 = calc_rsi(hist, 14)
    macd_val, macd_sig, macd_hist = calc_macd(hist)

    if sma20 is not None:
        results["sma20"] = round(sma20, 2)
    if rsi14 is not None:
        results["rsi14"] = round(rsi14, 2)
    if macd_val is not None:
        results["macd"] = round(macd_val, 4)
        results["macd_signal"] = round(macd_sig, 4)
        results["macd_hist"] = round(macd_hist, 4)

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
    if earnings.get("surprise_pct") is not None:
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
        if earnings.get("prev_surprise_pct") is not None:
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
    results = []
    print("      Fetching tech analysis (Yahoo Finance — no key needed)...")

    for i, ticker in enumerate(TECH_TICKERS):
        print(f"      [{i + 1}/{len(TECH_TICKERS)}] {ticker} ...", end=" ", flush=True)
        try:
            earnings = yf_earnings(ticker)
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
