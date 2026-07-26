#!/usr/bin/env python3
"""NASDAQ (Nasdaq-100 / NDX) data provider.

Reads from the existing scraper/ticker.json (already fetched by stocks_scraper.py
via CNBC). Computes bullish/bearish signal and generates analysis text.
No extra HTTP calls — avoids 429s.
"""
import json
import os


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
        ticker_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ticker.json")
        with open(ticker_path, "r") as f:
            ticker = json.load(f)

        items = ticker.get("items", [])
        nitem = next((i for i in items if i.get("symbol") == "NDX"), None)
        if not nitem:
            # Fallback: try .NDX or IXIC
            nitem = next(
                (i for i in items if i.get("symbol") in (".NDX", "NDX", "IXIC", ".IXIC")), None
            )
        if not nitem:
            return result

        price = nitem.get("price")
        change_pct = nitem.get("change")

        result["price"] = round(price, 2) if price is not None else None
        result["changePercent"] = round(change_pct, 2) if change_pct is not None else None

        if change_pct is not None:
            result["change"] = round(change_pct, 2)
            if change_pct > 0.5:
                result["signal"] = "BULLISH"
                result[
                    "analysis"
                ] = f"NASDAQ-100 (NDX) at {result['price']:,.2f}, up {change_pct:+.2f}% today — momentum is positive. If this continues, expect a test of recent highs into week-end. Monitor tech earnings and yields for confirmation."
            elif change_pct < -0.5:
                result["signal"] = "BEARISH"
                result[
                    "analysis"
                ] = f"NASDAQ-100 (NDX) at {result['price']:,.2f}, down {change_pct:.2f}% today — under pressure. Risk is to the downside with potential for a retest of support. Watch macro headlines and yield moves for reversal signals."
            else:
                result["signal"] = "NEUTRAL"
                result[
                    "analysis"
                ] = f"NASDAQ-100 (NDX) at {result['price']:,.2f}, nearly flat ({change_pct:+.2f}%) — consolidation mode this week. A breakout above resistance or breakdown below support will set the next direction."

    except Exception as e:
        print(f"      NASDAQ data error: {e}")
    return result


if __name__ == "__main__":
    import json
    print(json.dumps(get_nasdaq_data(), indent=2))
