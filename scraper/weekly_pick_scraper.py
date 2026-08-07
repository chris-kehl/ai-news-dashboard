#!/usr/bin/env python3
"""
Weekly Pick Scraper: Analyzes crypto, stocks, ETFs, and metals,
generates scores, picks the best assets for the week, and writes
to data.json as `weekly_pick`.

Runs every Monday afternoon. No API keys needed — uses Yahoo Finance
free endpoints.
"""
import json
import os
import requests
import time
import sys
from datetime import datetime

# ===== CONFIG =====
DATA_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data.json")
RATE_LIMIT = 1.1  # seconds between YF calls

# Assets to analyze: (ticker, display_name, category)
# All ETFs and crypto that are investable via major brokerages
ASSETS = [
    # === Broad Market ETFs ===
    ("SPY",  "SPY S&P 500",            "ETF"),
    ("QQQ",  "QQQ Nasdaq-100",         "ETF"),
    ("IWM",  "IWM Russell 2000",       "ETF"),
    ("VTI",  "VTI Total Market",       "ETF"),
    ("DIA",  "DIA Dow Jones",          "ETF"),
    # === Sector ETFs ===
    ("XLK",  "XLK Technology",         "ETF"),
    ("XLF",  "XLF Financials",         "ETF"),
    ("XLE",  "XLE Energy",             "ETF"),
    ("XLI",  "XLI Industrials",        "ETF"),
    ("XLV",  "XLV Health Care",        "ETF"),
    ("XLI",  "XLI Industrials",        "ETF"),
    ("XLRE", "XLRE Real Estate",       "ETF"),
    ("XLU",  "XLU Utilities",          "ETF"),
    ("XLP",  "XLP Consumer Staples",   "ETF"),
    ("XLY",  "XLY Consumer Discr.",    "ETF"),
    ("XLB",  "XLB Materials",          "ETF"),
    ("SMH",  "SMH Semiconductors",     "ETF"),
    ("SOXX", "SOXX Semiconductors",    "ETF"),
    ("IBB",  "IBB Biotech",            "ETF"),
    ("ARKK", "ARKK Innovation",        "ETF"),
    # === International ETFs ===
    ("EEM",  "EEM Emerging Markets",   "ETF"),
    ("VEA",  "VEA Developed Mkts",     "ETF"),
    ("IEFA", "IEFA Developed Mkts",    "ETF"),
    ("FXI",  "FXI China Large-Cap",    "ETF"),
    ("INDA", "INDA India MSCI",        "ETF"),
    ("EWZ",  "EWZ Brazil",             "ETF"),
    # === Commodity / Bond / Alternative ETFs ===
    ("GLD",  "GLD Gold",               "ETF"),
    ("SLV",  "SLV Silver",             "ETF"),
    ("USO",  "USO Crude Oil",          "ETF"),
    ("TLT",  "TLT 20+yr Treasuries",   "ETF"),
    ("HYG",  "HYG High-Yield Bonds",   "ETF"),
    ("LQD",  "LQD Inv Grade Bonds",    "ETF"),
    ("BND",  "BND Total Bond",         "ETF"),
    ("SCHD", "SCHD Dividend",          "ETF"),
    ("VNQ",  "VNQ Real Estate",        "ETF"),
    # === Crypto ETFs ===
    ("IBIT", "IBIT Bitcoin ETF",       "Crypto ETF"),
    ("FBTC", "FBTC Fidelity Bitcoin",  "Crypto ETF"),
    ("ARKB", "ARKB ARK Bitcoin",       "Crypto ETF"),
    ("BITO", "BITO Bitcoin Futures",   "Crypto ETF"),
    ("ETHE", "ETHE Ethereum ETF",      "Crypto ETF"),
    ("ETHA", "ETHA BlackRock Ethereum","Crypto ETF"),
    # === Spot Crypto ===
    ("BTC-USD", "Bitcoin",              "Crypto"),
    ("ETH-USD", "Ethereum",             "Crypto"),
    ("SOL-USD", "Solana",               "Crypto"),
    ("XRP-USD", "XRP",                  "Crypto"),
    ("ADA-USD", "Cardano",              "Crypto"),
    ("DOGE-USD","Dogecoin",             "Crypto"),
    ("AVAX-USD","Avalanche",            "Crypto"),
    ("LINK-USD","Chainlink",            "Crypto"),
    ("TAO-USD", "Bittensor (TAO)",      "Crypto"),
    ("HYPE-USD","Hyperliquid",          "Crypto"),
]


def yf_prices(ticker, days=35):
    """Fetch daily closes from YF."""
    url = (
        f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
        f"?interval=1d&range={days}d"
    )
    try:
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=20)
        data = r.json()
        result = data.get("chart", {}).get("result", [])
        if not result:
            return []
        q = result[0].get("indicators", {}).get("quote", [{}])[0]
        return [float(c) for c in q.get("close", []) if c is not None]
    except Exception as e:
        print(f"      YF error {ticker}: {e}")
        return []


def calc_rsi(closes, period=14):
    if len(closes) < period + 1:
        return None
    gains, losses = [], []
    for i in range(1, period + 1):
        chg = closes[-i] - closes[-(i + 1)]
        gains.append(max(chg, 0))
        losses.append(abs(min(chg, 0)))
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period or 0.001
    return 100 - (100 / (1 + avg_gain / avg_loss))


def calc_sma(closes, period):
    if len(closes) < period:
        return None
    return sum(closes[-period:]) / period


def calc_volatility(closes):
    if len(closes) < 2:
        return 0
    max_drop = 0
    for i in range(1, len(closes)):
        drop = abs(closes[i] - closes[i - 1]) / closes[i - 1] * 100
        max_drop = max(max_drop, drop)
    return max_drop


def calc_drawdown(closes):
    """Max drawdown from peak over the window."""
    if not closes:
        return 0
    peak = closes[0]
    max_dd = 0
    for c in closes:
        if c > peak:
            peak = c
        dd = (peak - c) / peak * 100
        max_dd = max(max_dd, dd)
    return max_dd


def analyze_asset(ticker, name, category):
    closes = yf_prices(ticker, days=35)
    time.sleep(RATE_LIMIT)
    if not closes or len(closes) < 5:
        return None

    price = closes[-1]
    chg_7d = (closes[-1] - closes[-7]) / closes[-7] * 100 if len(closes) >= 7 else 0
    chg_30d = (closes[-1] - closes[0]) / closes[0] * 100 if len(closes) >= 30 else 0
    rsi = calc_rsi(closes, 14)
    sma20 = calc_sma(closes, 20)
    sma50 = calc_sma(closes, 50) if len(closes) >= 50 else None
    vola = calc_volatility(closes)
    drawdown = calc_drawdown(closes)

    score = 50
    factors = []

    # Momentum (7d) — 25 pts max
    if chg_7d > 5:     score += 15; factors.append(f"+{chg_7d:.1f}% week")
    elif chg_7d > 3:   score += 12; factors.append(f"+{chg_7d:.1f}% week")
    elif chg_7d > 1.5: score += 8;  factors.append(f"+{chg_7d:.1f}% week")
    elif chg_7d > 0.3: score += 4;  factors.append(f"+{chg_7d:.1f}% week")
    elif chg_7d > -1.5: score -= 3;  factors.append(f"{chg_7d:.1f}% week")
    else:              score -= 8;  factors.append(f"{chg_7d:.1f}% week")

    # Trend (30d) — 20 pts
    if chg_30d > 12:   score += 12; factors.append(f"+{chg_30d:.1f}% month")
    elif chg_30d > 6:  score += 8;  factors.append(f"+{chg_30d:.1f}% month")
    elif chg_30d > 2:  score += 4;  factors.append(f"+{chg_30d:.1f}% month")
    elif chg_30d > -3: score -= 4;  factors.append(f"{chg_30d:.1f}% month")
    else:              score -= 10; factors.append(f"{chg_30d:.1f}% month")

    # RSI — 15 pts
    if rsi is not None:
        if rsi > 70:   score += 6;  factors.append(f"RSI {rsi:.0f} strong")
        elif rsi > 58: score += 3;  factors.append(f"RSI {rsi:.0f} positive")
        elif rsi < 32: score -= 6;  factors.append(f"RSI {rsi:.0f} oversold")
        elif rsi < 42: score -= 3;  factors.append(f"RSI {rsi:.0f} weak")

    # SMA positioning — 10 pts
    if sma20 is not None:
        if price > sma20 * 1.02:   score += 4; factors.append("above SMA20")
        elif price < sma20 * 0.98: score -= 3; factors.append("below SMA20")
    if sma50 is not None:
        if price > sma50 * 1.02:   score += 3; factors.append("above SMA50")
        elif price < sma50 * 0.98: score -= 2; factors.append("below SMA50")

    # Volatility penalty — 10 pts max
    if vola > 6:       score -= 8;  factors.append(f"high vol {vola:.1f}%")
    elif vola > 4:     score -= 4;  factors.append(f"elevated vol {vola:.1f}%")
    elif vola > 2.5:   score -= 2;  factors.append(f"choppy {vola:.1f}%")

    # Drawdown penalty
    if drawdown > 20:  score -= 3;  factors.append(f"deep drawdown -{drawdown:.0f}%")

    # Category-specific bonuses
    if category == "ETF" and chg_7d > 1 and chg_30d > 2:
        score += 2; factors.append("ETF trend strength")
    if category in ("Crypto", "Crypto ETF") and rsi and rsi > 60 and chg_7d > 2:
        score += 3; factors.append("crypto momentum")
    if category == "Crypto ETF" and chg_30d > 5:
        score += 2; factors.append("crypto ETF flow")

    return {
        "ticker": ticker,
        "name": name,
        "category": category,
        "price": round(price, 2),
        "change_7d": round(chg_7d, 2),
        "change_30d": round(chg_30d, 2),
        "rsi": round(rsi, 1) if rsi else None,
        "sma20": round(sma20, 2) if sma20 else None,
        "sma50": round(sma50, 2) if sma50 else None,
        "volatility": round(vola, 2),
        "drawdown": round(drawdown, 2),
        "score": max(0, min(100, round(score, 1))),
        "factors": factors,
    }


def generate_rationale(pick, all_results):
    """Generate weekly pick rationale dynamically from data."""
    ticker = pick["ticker"]
    name = pick["name"]
    cat = pick["category"]
    score = pick["score"]
    price = pick["price"]
    chg_7d = pick["change_7d"]
    chg_30d = pick["change_30d"]
    rsi = pick["rsi"]
    sma20 = pick.get("sma20")
    sma50 = pick.get("sma50")
    factors = pick["factors"]

    # Compute cohort averages
    def avg_score(filter_fn):
        vals = [r["score"] for r in all_results if filter_fn(r)]
        return round(sum(vals) / max(1, len(vals)), 1)

    etf_avg = avg_score(lambda r: r["category"] == "ETF")
    crypto_avg = avg_score(lambda r: r["category"] == "Crypto")
    crypto_etf_avg = avg_score(lambda r: r["category"] == "Crypto ETF")
    overall_avg = avg_score(lambda r: True)

    bull_text = ", ".join(factors[:4]) if factors else "mixed signals"

    # Conviction level
    if score >= 70:
        conviction = "HIGHEST CONVICTION"
        tone = f"{name} scores {score}/100 — the strongest setup across all tracked assets."
    elif score >= 60:
        conviction = "STRONG BUY"
        tone = f"{name} leads with {score}/100 — best risk/reward among the cohort."
    elif score >= 50:
        conviction = "MODERATE BUY"
        tone = f"{name} edges ahead at {score}/100 — modest edge in a mixed environment."
    else:
        conviction = "CAUTIOUS"
        tone = f"{name} tops the list at {score}/100 — best of a weak field."

    # Dynamic technical analysis
    tech_lines = []
    tech_lines.append(f"- Price: ${price:,.2f}")
    if sma20:
        rel20 = (price - sma20) / sma20 * 100
        tech_lines.append(f"- SMA20: ${sma20:,.2f} ({rel20:+.1f}%)")
    if sma50:
        rel50 = (price - sma50) / sma50 * 100
        tech_lines.append(f"- SMA50: ${sma50:,.2f} ({rel50:+.1f}%)")
    if rsi:
        rsi_state = "overbought" if rsi > 70 else "strong" if rsi > 55 else "neutral" if rsi > 40 else "oversold"
        tech_lines.append(f"- RSI(14): {rsi:.1f} — {rsi_state} momentum")
    tech_lines.append(f"- Weekly: {chg_7d:+.1f}%, Monthly: {chg_30d:+.1f}%")
    tech_lines.append(f"- Volatility (max daily): {pick['volatility']:.1f}%")
    if pick.get("drawdown"):
        tech_lines.append(f"- Max drawdown (window): {pick['drawdown']:.1f}%")

    # Build comparison paragraph
    comp_parts = [f"Overall cohort average: {overall_avg}/100."]
    if cat == "ETF":
        comp_parts.append(f"ETF cohort averages {etf_avg}/100.")
    elif cat == "Crypto":
        comp_parts.append(f"Spot crypto averages {crypto_avg}/100.")
    elif cat == "Crypto ETF":
        comp_parts.append(f"Crypto ETF cohort averages {crypto_etf_avg}/100.")

    return (
        f"**{conviction}: {name} ({ticker})** — ${price:,.2f}\n\n"
        f"{tone}\n\n"
        f"Key drivers: {bull_text}.\n\n"
        f"**Technical Setup**\n" + "\n".join(tech_lines) + "\n\n"
        f"**Trade Plan**\n"
        f"Entry: Current levels or on dip to SMA20 zone.\n"
        f"Stop-loss: Daily close below SMA20 or prior swing low.\n"
        f"Target: Upside continuation toward prior resistance.\n"
        f"Position size: Size to volatility — max 5% for high-vol assets.\n\n"
        f"**Why {name}?** "
        f"Top score of {score} across {len(all_results)} tracked assets. "
        + " ".join(comp_parts) +
        "\n\n*Not financial advice. All data from Yahoo Finance public API. Back-test your own rules.*"
    )


def get_weekly_pick():
    """Analyze all assets and return top weekly pick. Only runs on Monday afternoons.
    Otherwise returns cached pick from data.json."""
    now = datetime.now()
    is_monday = now.weekday() == 0  # Monday = 0
    is_afternoon = 12 <= now.hour < 22
    data_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data.json")

    # If not Monday afternoon, try to return cached pick
    if not (is_monday and is_afternoon):
        try:
            with open(data_path, 'r') as f:
                cached = json.load(f)
            wp = cached.get('weekly_pick')
            if wp and wp.get('top_pick', {}).get('name'):
                cached_time = datetime.fromisoformat(wp.get('generated_at', '2020-01-01'))
                day_diff = (now - cached_time).days
                if day_diff < 7:
                    print("      [weekly_pick] Using cached pick (runs Mon 12-10pm only)")
                    return wp
        except Exception:
            pass

    # Monday afternoon — generate fresh pick
    print(f"      Analyzing {len(ASSETS)} weekly picks...")
    results = []
    for ticker, name, category in ASSETS:
        print(f"      [{len(results) + 1}] {ticker} ...", end=" ", flush=True)
        r = analyze_asset(ticker, name, category)
        if r:
            results.append(r)
            print(f"score={r['score']}")
        else:
            print("no data")

    if not results:
        return {}

    results.sort(key=lambda x: x["score"], reverse=True)
    pick = results[0]

    return {
        "generated_at": datetime.now().isoformat(),
        "week_label": datetime.now().strftime("Week of %b %-d, %Y"),
        "top_pick": pick,
        "top_five": results[:5],
        "all_assets": results,
        "rationale": generate_rationale(pick, results),
    }


if __name__ == "__main__":
    result = get_weekly_pick()
    print(json.dumps(result, indent=2))
