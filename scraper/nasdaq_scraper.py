#!/usr/bin/env python3
"""NASDAQ Composite scraper.  Uses Yahoo Finance (free-ish, no key needed).

Returns:
    {
      "price": float,
      "change": float,
      "changePercent": float,
      "signal": "BULLISH" | "BEARISH" | "NEUTRAL",
      "analysis": str,  # weekly outlook text
    }
"""
import json, os, requests

_NASDAQ_TICKER = "^NDX"
_YF_URL = (
    "https://query1.finance.yahoo.com/v8/finance/chart/"
    "^NDX?interval=1d&range=3mo&indicators=quote&includeAdjustedClose=true"
)
_BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Accept": "application/json",
}


def _ma(prices, window):
    if len(prices) < window:
        return None
    return sum(prices[-window:]) / window


def get_nasdaq_data():
    result = {
        "price": None,
        "change": None,
        "changePercent": None,
        "signal": "NEUTRAL",
        "analysis": "NASDAQ weekly outlook loading...",
        "timestamp": None,
    }
    try:
        r = requests.get(_YF_URL, headers=_BROWSER_HEADERS, timeout=20)
        r.raise_for_status()
        j = r.json()
        chart = j.get("chart", {}).get("result", [{}])[0]
        meta = chart.get("meta", {})
        closes = chart.get("indicators", {}).get("quote", [{}])[0].get("close", [])

        # current price
        price = meta.get("regularMarketPrice")
        prev_close = meta.get("chartPreviousClose")
        if price is None and closes:
            price = closes[-1]
        if prev_close is None and len(closes) >= 2:
            prev_close = closes[-2]

        if price is not None:
            result["price"] = round(float(price), 2)
        if prev_close and price:
            result["change"] = round(float(price) - float(prev_close), 2)
            result["changePercent"] = round(
                (float(price) - float(prev_close)) / float(prev_close) * 100, 2
            )

        # signal: vs 20-day & 50-day moving averages
        if len(closes) >= 50 and all(c is not None for c in closes[-50:]):
            ma20 = _ma(closes, 20)
            ma50 = _ma(closes, 50)
            last = closes[-1]
            if ma20 and ma50 and last:
                if last > ma20 > ma50:
                    result["signal"] = "BULLISH"
                elif last < ma20 < ma50:
                    result["signal"] = "BEARISH"
                else:
                    result["signal"] = "NEUTRAL"

                direction = result["signal"]
                if direction == "BULLISH":
                    result["analysis"] = f"NASDAQ ({result['price']:,.2f}) is trading above both its 20-day ({ma20:,.0f}) and 50-day ({ma50:,.0f}) MAs — a bullish setup. If momentum holds, expect a test of recent highs this week. Watch resistance at Fib extensions and tech earnings calendar."
                elif direction == "BEARISH":
                    result["analysis"] = f"NASDAQ ({result['price']:,.2f}) is below the 20-day ({ma20:,.0f}) and 50-day ({ma50:,.0f}) MAs — bearish posture. Risk is to the downside; a break below the 50-day could target the next Fib retracement level. Monitor yields and macro headlines."
                else:
                    result["analysis"] = f"NASDAQ ({result['price']:,.2f}) is mixed vs the 20-day ({ma20:,.0f}) and 50-day ({ma50:,.0f}) MAs — sideways consolidation likely this week. Range-bound until a clear breakout above resistance or breakdown below support."

        result["timestamp"] = chart.get("meta", {}).get("regularMarketTime")

    except Exception as e:
        print(f"      NASDAQ scraper error: {e}")
    return result


if __name__ == "__main__":
    print(json.dumps(get_nasdaq_data(), indent=2))
