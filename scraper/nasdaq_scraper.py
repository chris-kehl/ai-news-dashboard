import json
import os
import requests
from datetime import datetime

def yf_ticker_data(ticker, range_days=60):
    """Fetch v8 data for any ticker."""
    url = (
        "https://query1.finance.yahoo.com/v8/finance/chart/"
        + ticker
        + "?interval=1d&range="
        + str(range_days)
        + "d"
    )
    try:
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=20)
        data = r.json()
        result = data.get("chart", {}).get("result", [])
        if not result:
            return None
        meta = result[0]["meta"]
        timestamps = result[0]["timestamp"]
        quote = result[0]["indicators"]["quote"][0]
        closes = quote["close"]
        volumes = quote["volume"]
        history = []
        for i in range(len(timestamps)):
            if closes[i] is not None:
                history.append({
                    "date": datetime.fromtimestamp(timestamps[i]).strftime("%Y-%m-%d"),
                    "close": float(closes[i]),
                    "volume": int(volumes[i]) if volumes[i] else 0,
                })
        return {
            "ticker": ticker,
            "price": meta.get("regularMarketPrice"),
            "prev_close": meta.get("chartPreviousClose"),
            "change_pct": None,  # computed from history below
            "history": history,
        }
    except Exception as e:
        print("YF " + ticker + " error: " + str(e))
        return None


def yf_ndx_data(range_days=60):
    # Try NDX direct first, then QQQ as proxy
    data = yf_ticker_data("^NDX", range_days)
    if data and data.get("price") is not None:
        return data
    data = yf_ticker_data("QQQ", range_days)
    if data and data.get("price") is not None:
        # QQQ tracks NDX roughly 1/40th the value; optionally normalize
        data["is_proxy"] = True
        data["proxy_ticker"] = "QQQ"
        return data
    return None

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
    hist = [m - s for m, s in zip(macd_line[-len(signal_line):], signal_line)]
    return macd_line[-1], signal_line[-1], hist[-1]

def get_nasdaq_data():
    result = {
        "price": None,
        "change": None,
        "changePercent": None,
        "signal": "NEUTRAL",
        "analysis": "NASDAQ-100 data unavailable.",
        "timestamp": datetime.now().isoformat(),
    }
    try:
        data = yf_ndx_data(range_days=60)
        if not data or data.get("price") is None:
            ticker_path = os.path.join(os.path.dirname(__file__), "ticker.json")
            with open(ticker_path, "r") as f:
                ticker = json.load(f)
            items = ticker.get("items", [])
            nitem = next((i for i in items if i.get("symbol") == "NDX"), None)
            if not nitem:
                nitem = next((i for i in items if i.get("symbol") in (".NDX", "NDX", "IXIC", ".IXIC")), None)
            if nitem:
                price = nitem.get("price")
                change_pct = nitem.get("change")
                if price is not None:
                    result["price"] = round(price, 2)
                if change_pct is not None:
                    result["change"] = round(change_pct, 2)
                    result["changePercent"] = round(change_pct, 2)
            return result

        price = data["price"]
        history = data.get("history", [])
        # Compute change_pct from last two history entries (Yahoo's meta value is often stale)
        if len(history) >= 2:
            last_close = history[-1]["close"]
            prev_close = history[-2]["close"]
            change_pct = ((last_close - prev_close) / prev_close) * 100 if prev_close else 0
        else:
            change_pct = 0
        result["price"] = round(price, 2) if price else None
        result["change"] = round(change_pct, 2) if change_pct else None
        result["changePercent"] = round(change_pct, 2) if change_pct else None

        sma20 = calc_sma(history, 20)
        rsi14 = calc_rsi(history, 14)
        macd, macd_sig, macd_hist = calc_macd(history)

        bull_factors = []
        bear_factors = []

        if price and sma20:
            if price > sma20:
                bull_factors.append("price above SMA20")
            else:
                bear_factors.append("price below SMA20")
        if rsi14 is not None:
            if rsi14 > 60:
                bull_factors.append("RSI " + str(round(rsi14, 1)) + " strong")
            elif rsi14 > 50:
                bull_factors.append("RSI " + str(round(rsi14, 1)) + " building")
            elif rsi14 < 40:
                bear_factors.append("RSI " + str(round(rsi14, 1)) + " weak")
            else:
                bear_factors.append("RSI " + str(round(rsi14, 1)) + " neutral-bearish")
        if macd_hist is not None:
            if macd_hist > 0:
                bull_factors.append("MACD bullish")
            else:
                bear_factors.append("MACD bearish")
        if change_pct > 1.0:
            bull_factors.append("strong +" + str(round(change_pct, 2)) + "% move")
        elif change_pct > 0.3:
            bull_factors.append("modest +" + str(round(change_pct, 2)) + "% up")
        elif change_pct < -1.0:
            bear_factors.append("strong " + str(round(change_pct, 2)) + "% selloff")
        elif change_pct < -0.3:
            bear_factors.append("modest " + str(round(change_pct, 2)) + "% down")

        bull_count = len(bull_factors)
        bear_count = len(bear_factors)

        if change_pct > 0.5 and bull_count >= bear_count:
            signal = "BULLISH"
        elif change_pct < -0.5 and bear_count >= bull_count:
            signal = "BEARISH"
        elif change_pct > 0:
            signal = "BULLISH"
        elif change_pct < 0:
            signal = "BEARISH"
        else:
            signal = "NEUTRAL"
        result["signal"] = signal

        date_str = datetime.now().strftime("%a %-d %b")
        bull_txt = ", ".join(bull_factors) if bull_factors else "none"
        bear_txt = ", ".join(bear_factors) if bear_factors else "none"

        if signal == "BULLISH":
            result["analysis"] = "NASDAQ-100 (NDX) " + date_str + ": " + "{:,.2f}".format(price) + ", up " + "{:+.2f}%".format(change_pct) + " -- BULLISH. " + bull_txt + ". Counter: " + bear_txt + ". Ride momentum with stops below session low."
        elif signal == "BEARISH":
            result["analysis"] = "NASDAQ-100 (NDX) " + date_str + ": " + "{:,.2f}".format(price) + ", down " + "{:.2f}%".format(change_pct) + " -- BEARISH. " + bear_txt + ". Counter: " + bull_txt + ". Watch for SMA20 reclaim to flip bias."
        else:
            result["analysis"] = "NASDAQ-100 (NDX) " + date_str + ": " + "{:,.2f}".format(price) + ", flat (" + "{:+.2f}%".format(change_pct) + ") -- NEUTRAL. Bullish: " + bull_txt + ". Bearish: " + bear_txt + ". Waiting for directional break."
    except Exception as e:
        print("NASDAQ data error: " + str(e))
    return result

if __name__ == "__main__":
    print(json.dumps(get_nasdaq_data(), indent=2))
