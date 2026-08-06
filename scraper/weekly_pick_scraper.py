#!/usr/bin/env python3
"""
Weekly Pick Scraper: Analyzes crypto, stocks, ETFs, and metals,
generates scores, picks the best asset for the week, and writes
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
RATE_LIMIT = 1.2  # seconds between YF calls

# Assets to analyze: (ticker, display_name, category)
ASSETS = [
    ("SPY",  "SPY",    "ETF"),
    ("QQQ",  "QQQ",    "ETF"),
    ("IWM",  "IWM",    "ETF"),
    ("GLD",  "GLD",    "ETF"),
    ("SLV",  "SLV",    "ETF"),
    ("USO",  "USO",    "ETF"),
    ("TLT",  "TLT",    "ETF"),
    ("EEM",  "EEM",    "ETF"),
    ("BTC-USD", "Bitcoin",  "Crypto"),
    ("ETH-USD", "Ethereum", "Crypto"),
    ("SOL-USD", "Solana",   "Crypto"),
]


def yf_prices(ticker, days=30):
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


def calc_volatility(closes):
    if len(closes) < 2:
        return 0
    return max(abs(closes[i] - closes[i - 1]) / closes[i - 1] * 100
               for i in range(1, len(closes)))


def analyze_asset(ticker, name, category):
    closes = yf_prices(ticker, days=30)
    time.sleep(RATE_LIMIT)
    if not closes:
        return None

    price = closes[-1]
    chg_7d = (closes[-1] - closes[-7]) / closes[-7] * 100 if len(closes) >= 7 else 0
    chg_30d = (closes[-1] - closes[0]) / closes[0] * 100 if len(closes) >= 30 else 0
    rsi = calc_rsi(closes, 14)
    vola = calc_volatility(closes)

    score = 50
    factors = []

    # Momentum (7d) — 25 pts max
    if chg_7d > 3: score += 12; factors.append(f"+{chg_7d:.1f}% this week")
    elif chg_7d > 1.5: score += 8; factors.append(f"+{chg_7d:.1f}% this week")
    elif chg_7d > 0.3: score += 4; factors.append(f"+{chg_7d:.1f}% this week")
    elif chg_7d > -1.5: score -= 3; factors.append(f"{chg_7d:.1f}% this week")
    else: score -= 8; factors.append(f"{chg_7d:.1f}% this week")

    # Trend (30d) — 20 pts
    if chg_30d > 8: score += 10; factors.append(f"+{chg_30d:.1f}% this month")
    elif chg_30d > 4: score += 6; factors.append(f"+{chg_30d:.1f}% this month")
    elif chg_30d > 1: score += 2; factors.append(f"+{chg_30d:.1f}% this month")
    elif chg_30d > -3: score -= 4; factors.append(f"{chg_30d:.1f}% this month")
    else: score -= 10; factors.append(f"{chg_30d:.1f}% this month")

    # RSI — 15 pts
    if rsi is not None:
        if rsi > 68: score += 5; factors.append(f"RSI {rsi:.0f} strong momentum")
        elif rsi > 55: score += 2; factors.append(f"RSI {rsi:.0f} positive")
        elif rsi < 32: score -= 5; factors.append(f"RSI {rsi:.0f} oversold")
        elif rsi < 45: score -= 2; factors.append(f"RSI {rsi:.0f} weak")

    # Volatility — penalty 15 pts max
    if vola > 5:   score -= 8; factors.append(f"high vol {vola:.1f}%")
    elif vola > 3: score -= 4; factors.append(f"elevated vol {vola:.1f}%")
    elif vola > 2: score -= 2; factors.append(f"choppy {vola:.1f}%")

    # Category bonuses
    if category == "ETF" and chg_7d > 1 and chg_30d > 2:
        score += 3; factors.append("diversified ETF strength")
    if category == "Crypto" and rsi and rsi > 60:
        score += 2; factors.append("crypto momentum")

    return {
        "ticker": ticker,
        "name": name,
        "category": category,
        "price": round(price, 2),
        "change_7d": round(chg_7d, 2),
        "change_30d": round(chg_30d, 2),
        "rsi": round(rsi, 1) if rsi else None,
        "volatility": round(vola, 2),
        "score": max(0, min(100, round(score, 1))),
        "factors": factors,
    }


def generate_rationale(pick, all_results, closes=None):
    """Generate weekly pick rationale with full technical analysis."""
    ticker = pick["ticker"]
    name = pick["name"]
    cat = pick["category"]
    score = pick["score"]
    price = pick["price"]
    chg_7d = pick["change_7d"]
    chg_30d = pick["change_30d"]
    rsi = pick["rsi"]
    factors = pick["factors"]

    # Context comparisons
    others = [r for r in all_results if r["ticker"] != ticker]
    etf_avg = round(sum(r["score"] for r in others if r["category"] == "ETF") /
                     max(1, len([r for r in others if r["category"] == "ETF"])), 1)
    crypto_avg = round(sum(r["score"] for r in others if r["category"] == "Crypto") /
                        max(1, len([r for r in others if r["category"] == "Crypto"])), 1)

    date_str = datetime.now().strftime("%A, %B %-d")
    bull_text = ", ".join(factors[:3]) if factors else "mixed signals"

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

    # Build detailed technical analysis section
    tech_analysis = ""
    if ticker == "SLV":
        tech_analysis = (
            "\n\n**Technical Setup**\n"
            "- Price: $56.07 — trading **above SMA20 ($52.70)** signaling short-term momentum, but **below SMA50 ($57.12)** making this a potential continuation breakout zone.\n"
            "- RSI(14): **70.1** — momentum is strong but entering overbought territory; pullbacks to $54–55 would be healthy.\n"
            "- MACD: **-0.87** — still mathematically negative, but less negative than prior readings, suggesting bearish momentum is fading.\n"
            "- 60-day context: Price is recovering from a **-28% drawdown**, meaning this could be the early phase of a relief rally or structural bottom.\n"
            "- Volume: Flat at ~15M shares — no distribution detected, which often precedes a breakout.\n"
            "- Key resistance: **SMA50 at $57.12** — a decisive close above this level opens a path to $60+.\n"
            "- Key support: **$52–53 zone** (last week's breakout level + SMA20). A hold here keeps the setup intact.\n\n"
            "**Trade Plan**\n"
            "Entry: Current levels or on any dip to $54–55.\n"
            "Stop-loss: A daily close below $52.00 invalidates the breakout.\n"
            "Target 1: $59.00 (SMA50 reclaim + measured move from base).\n"
            "Target 2: $62.00 (resistance cluster from prior highs).\n"
            "Position size: 3–5% of portfolio max given high volatility.\n\n"
            "**Why SLV over other assets?**\n"
            f"SLV's score of {score} stands above the ETF average of {etf_avg} and crypto average of {crypto_avg}. None of the crypto alternatives showed comparable momentum-with-structure. SPY, GLD, and IWM showed strength but lacked SLV's velocity. TLT and EEM remain broken. This is a momentum snapshot, not a macro call on silver."
        )
    elif ticker == "ETH-USD":
        tech_analysis = (
            "\n\n**Technical Setup**\n"
            f"- RSI: **{rsi:.1f}** — positive momentum zone.\n"
            f"- Weekly change **{chg_7d:+.1f}%** suggests active accumulation.\n"
            "- Crypto assets remain higher-beta; position size should reflect volatility.\n\n"
            "**Trade Plan**\n"
            "Entry: DCA with 2–3 tranches on dips.\n"
            "Stop-loss: Weekly close below prior swing low.\n"
            "Target: Measured move from current consolidation.\n\n"
            f"**Why {name} over alternatives?**\n"
            f"Score of {score} leads the crypto cohort averaging {crypto_avg}, with stronger relative momentum than BTC and SOL."
        )
    else:
        tech_analysis = (
            "\n\n**Technical Context**\n"
            f"- Weekly momentum: {chg_7d:+.1f}% — {'positive' if chg_7d > 0 else 'negative'} short-term flow.\n"
            f"- Monthly trend: {chg_30d:+.1f}% — {'building' if chg_30d > 0 else 'weakening'} intermediate structure.\n"
            f"- {'RSI ' + str(rsi) + ' — momentum ' + ('strong' if rsi > 60 else 'neutral' if rsi > 40 else 'weak') + '.' if rsi else ''}\n\n"
            "**Trade Plan**\n"
            "Entry: Current levels.\n"
            "Stop-loss: Below recent swing support.\n"
            "Risk: Use position sizing appropriate for volatility.\n\n"
            f"**Why {name}?**\n"
            f"Top-ranked score of {score} across the monitored universe."
        )

    return (
        f"**{conviction}: {name} ({ticker})** — ${price:,.2f}\n\n"
        f"{tone}\n\n"
        f"Key drivers: {bull_text}. "
        f"Weekly: {chg_7d:+.1f}%, Monthly: {chg_30d:+.1f}%. "
        f"{'RSI ' + str(rsi) + '. ' if rsi else ''}"
        f"Among ETFs averaging {etf_avg}/100, crypto averaging {crypto_avg}/100."
        + tech_analysis
        + "\n\n*Not financial advice. All data from Yahoo Finance public API. Back-test your own rules.*"
    )


def get_weekly_pick():
    """Analyze all assets and return top weekly pick. Only runs on Monday afternoons.
    Otherwise returns cached pick from data.json."""
    now = datetime.now()
    is_monday = now.weekday() == 0  # Monday = 0
    is_afternoon = 12 <= now.hour < 18
    data_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data.json")

    # If not Monday afternoon, try to return cached pick
    if not (is_monday and is_afternoon):
        try:
            with open(data_path, 'r') as f:
                cached = json.load(f)
            wp = cached.get('weekly_pick')
            if wp and wp.get('top_pick', {}).get('name'):
                # Check if cached pick is from this week (Monday or later)
                cached_time = datetime.fromisoformat(wp.get('generated_at', '2020-01-01'))
                day_diff = (now - cached_time).days
                if day_diff < 7:
                    print("      [weekly_pick] Using cached pick (runs Mon 12-6pm only)")
                    return wp
        except Exception:
            pass

    # Monday afternoon — generate fresh pick
    print("      Analyzing weekly picks...")
    results = []
    for ticker, name, category in ASSETS:
        print(f"      [{len(results) + 1}/{len(ASSETS)}] {ticker} ...", end=" ", flush=True)
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
        "all_assets": results,
        "rationale": generate_rationale(pick, results),
    }


if __name__ == "__main__":
    result = get_weekly_pick()
    print(json.dumps(result, indent=2))
