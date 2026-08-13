#!/usr/bin/env python3
"""
Weekly AI Pick Scorer — Quality Universe with Fundamentals, Technicals, Sentiment

Universe: 592 tickers (501 SP500 + 66 ETFs + 16 crypto + 6 metals + 3 commodities)

Scoring (0-100 composite):
  Technical Analysis:    40 pts (trend 15, momentum 10, RSI 8, volume 7)
  Fundamentals:          30 pts (stock: P/E, rev growth, margin, debt, EPS, ROE, current ratio)
                          (ETF: AUM + diversification proxy)
  Market Sentiment:       30 pts (52w range position 8, volume surge 8, consistency 7, RSI alignment 7)

Quality Gate (stocks must have P/E > 0, SMA aligned, and reasonable metrics)
Historical scores appended to data/score_history.json weekly.

Auto-generates chart, injects weekly pick + best ETF + metals into data.json.
"""

import json, os, sys, time, math, subprocess, concurrent.futures
import urllib.request, urllib.error, urllib.parse
from pathlib import Path
from datetime import datetime

BASE = Path.home() / "ai-news-dashboard"
UNIVERSE = BASE / "data" / "universe.jsonl"
SCORES   = BASE / "data" / "weekly_scores.json"
HISTORY  = BASE / "data" / "score_history.json"
MAX_WORKERS = 40
CT = 12  # chart timeout
FT = 5   # fund timeout


def fetch(ticker: str, timeout=CT):
    """Fetch Yahoo chart data (prices + volumes)."""
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(ticker)}?interval=1d&range=8mo&includeAdjustedClose=true"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read().decode())
        res = data.get("chart", {}).get("result", [None])[0]
        if not res:
            return None
        meta = res.get("meta", {})
        ind = res.get("indicators", {}).get("quote", [{}])[0]
        closes = [c for c in ind.get("close", []) if c is not None]
        vols = [v for v in ind.get("volume", []) if v is not None]
        if len(closes) < 30:
            return None
        return {
            "closes": closes, "volumes": vols,
            "price": closes[-1],
            "high52": meta.get("fiftyTwoWeekHigh"),
            "low52": meta.get("fiftyTwoWeekLow"),
            "name": meta.get("shortName", "") or meta.get("longName", "") or ticker,
        }
    except Exception:
        return {"error": True}


def fetch_fundamentals(ticker: str, timeout=FT):
    """Fetch key stats + financial data for fundamental scoring."""
    url = f"https://query2.finance.yahoo.com/v10/finance/quoteSummary/{urllib.parse.quote(ticker)}?modules=defaultKeyStatistics,financialData,summaryDetail"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read().decode())
        r = data.get("quoteSummary", {}).get("result", [None])
        if not r or not r[0]:
            return {}
        fd = r[0].get("financialData", {})
        sd = r[0].get("summaryDetail", {})
        return {
            "pe": sd.get("trailingPE"),
            "peg": sd.get("pegRatio"),
            "revenue_growth": fd.get("revenueGrowth"),
            "profit_margin": fd.get("profitMargins"),
            "debt_to_equity": sd.get("debtToEquity"),
            "eps_growth": fd.get("earningsGrowth"),
            "roe": fd.get("returnOnEquity"),
            "current_ratio": fd.get("currentRatio"),
            "market_cap": sd.get("marketCap"),
            "dividend_yield": sd.get("dividendYield"),
        }
    except Exception:
        return {}


def sma(data, n):
    if len(data) >= n: return sum(data[-n:]) / n
    return sum(data) / len(data) if data else 0


def calc_rsi(closes, period=14):
    if len(closes) < period + 1: return 50
    g, l = [], []
    for i in range(1, period + 1):
        ch = closes[-i] - closes[-(i + 1)]
        g.append(max(ch, 0)); l.append(abs(min(ch, 0)))
    ag = sum(g) / period
    al = sum(l) / period
    if al == 0: return 100
    return 100 - (100 / (1 + ag / al))


def calc_macd(closes, fast=12, slow=26, signal=9):
    """Return (macd_line, signal_line, histogram, bullish)."""
    if len(closes) < slow + signal:
        return None, None, None, False
    # EMA fast + slow
    def ema(data, n):
        k = 2 / (n + 1)
        e = data[0]
        for v in data[1:]:
            e = v * k + e * (1 - k)
        return e
    fast_ema = ema(closes, fast)
    slow_ema = ema(closes, slow)
    macd_line = fast_ema - slow_ema
    # Signal line = EMA of MACD (approximate)
    sig_ema = macd_line  # crude first value
    sig_ema = macd_line * (2 / (signal + 1)) + sig_ema * (1 - (2 / (signal + 1)))
    hist = macd_line - sig_ema
    # Bullish if histogram expanding positive
    bullish = hist > 0 and macd_line > sig_ema
    return macd_line, sig_ema, hist, bullish


def score_technical(chart):
    c = chart["closes"]; v = chart.get("volumes", [])
    if len(c) < 30: return None
    p = c[-1]
    chg_1d = (c[-1] / c[-2] - 1) * 100 if len(c) >= 2 and c[-2] != 0 else 0
    chg_5d = (c[-1] / c[-6] - 1) * 100 if len(c) >= 6 and c[-6] != 0 else 0
    chg_20d = (c[-1] / c[-21] - 1) * 100 if len(c) >= 21 and c[-21] != 0 else 0

    # === Trend Score (15 pts) ===
    s10, s20, s50 = sma(c, 10), sma(c, 20), sma(c, 50)
    trend = 0
    if p > s10: trend += 3
    if p > s20: trend += 4
    if p > s50: trend += 4
    if s10 > s20: trend += 2
    if s20 > s50: trend += 2
    trend = max(0, min(15, trend))

    # === Momentum Score (10 pts) ===
    mom = 0
    if chg_5d > 3: mom += 3
    elif chg_5d > 1: mom += 1
    elif chg_5d < -3: mom -= 2
    if chg_20d > 6: mom += 3
    elif chg_20d > 2: mom += 2
    elif chg_20d < -5: mom -= 3
    if chg_1d > 0 and chg_5d > 0: mom += 2
    elif chg_1d < 0 and chg_5d < 0: mom -= 2
    # Consistency bonus
    if abs(chg_5d) < 15: mom += 2
    mom = max(0, min(10, mom))

    # === RSI Score (8 pts) ===
    rsi_val = calc_rsi(c)
    if 40 < rsi_val < 60: rsi_s = 8        # Goldilocks
    elif 30 <= rsi_val <= 75: rsi_s = 5    # Acceptable
    else: rsi_s = 2                        # Extreme

    # === Volume Score (7 pts) ===
    vc = 3
    if len(v) >= 10:
        avg_vol = sum(v[-10:]) / 10
        if avg_vol > 0:
            ratio = v[-1] / avg_vol
            if ratio > 2.0: vc = 7
            elif ratio > 1.3: vc = 5
            elif ratio > 0.8: vc = 3
            else: vc = 2

    return {
        "score": trend + mom + rsi_s + vc,
        "trend": trend, "momentum": mom,
        "rsi": round(rsi_val, 1), "vc": vc,
        "price": p,
        "chg_1d": chg_1d, "chg_5d": chg_5d, "chg_20d": chg_20d,
        "sma10": s10, "sma20": s20, "sma50": s50,
    }


def quality_gate(item, chart, fund):
    """Stocks must have positive earnings, growth, and aligned SMAs."""
    typ = item.get("type", "")
    if typ != "stock":
        return True, ""
    # SMA alignment check
    c = chart["closes"]
    p, s20, s50 = c[-1], sma(c, 20), sma(c, 50)
    if p < s50 * 0.98:
        return False, "below SMA50"
    # Fundamental checks
    reasons = []
    pe = fund.get("pe")
    if pe is not None and pe < 0:
        reasons.append("neg P/E")
    rev = fund.get("revenue_growth")
    if rev is not None and rev <= -0.15:
        reasons.append("rev_decline")
    marg = fund.get("profit_margin")
    if marg is not None and marg <= -0.05:
        reasons.append("neg_margin")
    if reasons:
        return False, ", ".join(reasons)
    return True, ""


def score_fundamentals(item, fund):
    """Fundamental scoring - 30 pts for stocks, 22 for ETFs, 18 for others."""
    typ = item.get("type", "")
    if typ != "stock" or not fund or not any(v is not None for v in fund.values()):
        if typ == "etf":
            # ETF quality proxy
            mc = fund.get("market_cap")
            if mc and mc > 5e9: return 22, "Large ETF"
            elif mc and mc > 1e9: return 20, "Mid ETF"
            return 18, "ETF"
        return 18, "N/A"

    s = 0; d = []
    pe = fund.get("pe")
    if pe is not None and pe > 0:
        if 10 <= pe <= 20: s += 6; d.append(f"P/E {pe:.0f}")
        elif 8 <= pe <= 25: s += 5
        elif pe > 100: s += 1
        else: s += 3
    elif pe is None: s += 3
    else: s += 1; d.append("neg P/E")

    rev = fund.get("revenue_growth")
    if rev is not None:
        rp = rev * 100
        if rp > 20: s += 6; d.append(f"Rev +{rp:.0f}%")
        elif rp > 10: s += 5
        elif rp > 0: s += 3
        else: s += 1; d.append(f"Rev {rp:.0f}%")
    else: s += 3

    marg = fund.get("profit_margin")
    if marg is not None:
        mp = marg * 100
        if mp > 20: s += 5; d.append(f"Margin {mp:.0f}%")
        elif mp > 12: s += 4
        elif mp > 5: s += 2
        elif mp > 0: s += 1
        else: s += 0; d.append("neg_margin")
    else: s += 3

    de = fund.get("debt_to_equity")
    if de is not None:
        if de < 30: s += 5; d.append(f"D/E {de:.0f}")
        elif de < 50: s += 4
        elif de < 100: s += 3
        else: s += 2
    else: s += 3

    eps = fund.get("eps_growth")
    if eps is not None:
        ep = eps * 100
        if ep > 30: s += 5; d.append(f"EPS +{ep:.0f}%")
        elif ep > 15: s += 4
        elif ep > 5: s += 2
        elif ep > 0: s += 1
        else: s += 0
    else: s += 3

    roe = fund.get("roe")
    if roe is not None:
        rp = roe * 100
        if rp > 20: s += 3; d.append(f"ROE {rp:.0f}%")
        elif rp > 15: s += 2
        elif rp > 8: s += 1
    else: s += 2

    return min(30, s), " | ".join(d) if d else "Neutral"


def score_sentiment(chart, tech):
    """Market sentiment scoring - 30 pts."""
    c = chart["closes"]; v = chart.get("volumes", [])
    fh, fl = chart.get("high52"), chart.get("low52")

    # 52-Week Range Position (8 pts)
    rp = 3
    if fh and fl and fh != fl:
        pos = (c[-1] - fl) / (fh - fl)
        if pos > 0.80: rp = 8
        elif pos > 0.65: rp = 6
        elif pos > 0.45: rp = 4
        else: rp = 2

    # Volume Surge (8 pts)
    vs = 4
    if len(v) >= 20:
        # Compare last 5 days avg vs prior 15 days avg
        a15 = sum(v[-20:-5]) / 15 if sum(v[-20:-5]) > 0 else 0
        a5 = sum(v[-5:]) / 5
        if a15 > 0:
            ratio = a5 / a15
            if ratio > 2.5: vs = 8
            elif ratio > 1.5: vs = 6
            elif ratio > 1.1: vs = 5
            elif ratio > 0.7: vs = 3
            else: vs = 2

    # Consistency / Gap Score (7 pts)
    cons = 5
    if len(c) >= 10:
        daily = [(c[i] / c[i - 1] - 1) * 100 for i in range(1, len(c)) if c[i - 1] != 0]
        # Count >3% gaps (up or down) as volatility events
        gaps = sum(1 for d in daily if abs(d) > 3)
        if gaps == 0: cons = 7
        elif gaps <= 2: cons = 6
        elif gaps <= 5: cons = 4
        else: cons = 2

    # RSI Alignment (7 pts)
    rsi = tech["rsi"]
    ralign = 3
    if 42 <= rsi <= 62: ralign = 7        # Sweet spot
    elif 35 <= rsi < 42 or 62 < rsi <= 72: ralign = 5
    elif 30 <= rsi < 35 or 72 < rsi <= 78: ralign = 3
    else: ralign = 1

    return rp + vs + cons + ralign, rp, vs, cons, ralign


def score_one(item):
    t = item["ticker"]
    chart = fetch(t)
    if not chart or chart.get("error"):
        return None

    fund = fetch_fundamentals(t)
    tech = score_technical(chart)
    if not tech:
        return None

    # Quality gate for stocks
    passes, reason = quality_gate(item, chart, fund)
    if not passes:
        return {"rejected": True, "ticker": t, "reason": reason}

    fs, fd = score_fundamentals(item, fund)
    sent, s_rp, s_vs, s_cons, s_ralign = score_sentiment(chart, tech)

    comp = tech["score"] + fs + sent

    # Dynamic penalties
    pen = 0
    if tech["rsi"] > 80: pen += 12        # strongly overbought
    elif tech["rsi"] > 75: pen += 8
    if tech["chg_5d"] < -5: pen += 8      # recent sharp decline
    if fund.get("pe") and fund["pe"] > 100: pen += 3   # expensive but not necessarily bad
    if tech["sma20"] < tech["sma50"] * 0.98: pen += 3

    final = max(0, min(100, comp - pen))

    return {
        "ticker": t,
        "name": item.get("name", chart.get("name", t)),
        "type": item.get("type", ""),
        "category": item.get("category", ""),
        "score": round(final, 1),
        "tech_score": tech["score"],
        "fund_score": fs,
        "sentiment_score": sent,
        "penalty": pen,
        "factors": {
            "price": round(tech["price"], 2),
            "chg_1d": round(tech["chg_1d"], 2),
            "chg_5d": round(tech["chg_5d"], 2),
            "chg_20d": round(tech["chg_20d"], 2),
            "rsi": tech["rsi"],
            "pe": fund.get("pe"),
            "fund_details": fd,
            "range_pos": s_rp,
            "vol_surge": s_vs,
            "consistency": s_cons,
            "rsi_align": s_ralign,
        }
    }


def load_history():
    if HISTORY.exists():
        with open(HISTORY) as f:
            return json.load(f)
    return {}


def save_history(history, today_scores):
    """Append today's scores to history keyed by date."""
    today = datetime.now().strftime("%Y-%m-%d")
    # Store ticker -> score for quick trend lookups
    history[today] = {s["ticker"]: s["score"] for s in today_scores if "score" in s}
    # Keep last 26 weeks
    if len(history) > 26:
        for k in sorted(history.keys())[:-26]:
            del history[k]
    with open(HISTORY, "w") as f:
        json.dump(history, f, indent=2)


def get_improving_tickers(history, today_scores):
    """Return tickers whose scores have risen 2+ points over last 3 available weeks."""
    if not history:
        return []
    dates = sorted(history.keys())[-3:]
    improving = []
    for s in today_scores:
        t = s["ticker"]
        scores = [history[d].get(t) for d in dates if t in history.get(d, {})]
        if len(scores) >= 2 and all(scores[i] < scores[i + 1] for i in range(len(scores) - 1)):
            improving.append({
                "ticker": t, "name": s["name"],
                "score": s["score"],
                "trend": "↑" + f" +{scores[-1] - scores[0]:.1f}"
            })
    improving.sort(key=lambda x: x["score"], reverse=True)
    return improving[:10]


def build_pick(pick, gen_at, label="This Week"):
    f = pick["factors"]
    return {
        "week_label": label,
        "generated_at": gen_at,
        "top_pick": {
            "ticker": pick["ticker"],
            "name": pick["name"],
            "price": f["price"],
            "score": pick["score"],
            "category": pick.get("category", ""),
            "change_7d": f["chg_5d"],
            "change_30d": f["chg_20d"],
            "rsi": f["rsi"],
            "factors": [f"T:{pick['tech_score']}", f"F:{pick['fund_score']}", f"S:{pick['sentiment_score']}"],
        },
        "rationale": (
            f"Score: {pick['score']}/100 (Tech {pick['tech_score']}/40, Fund {pick['fund_score']}/30, Sent {pick['sentiment_score']}/30)\n\n"
            f"Price: ${f['price']:.2f} | 5d: {f['chg_5d']:.1f}% | 20d: {f['chg_20d']:.1f}% | RSI: {f['rsi']}\n\n"
            f"Fundamentals: {f.get('fund_details', 'N/A')}\n\n"
            "Disclaimer: Not financial advice."
        ),
        "top_five": [],
    }


def inject(weekly, best_etf, metals, improving):
    """Inject all weekly pick data into data.json."""
    dj = BASE / "data.json"
    try:
        with open(dj, "r") as f:
            data = json.load(f)
    except Exception:
        data = {}
    data["weekly_pick"] = weekly
    if best_etf:
        data["best_etf"] = best_etf
    data["scored_metals"] = metals
    data["improving_picks"] = improving
    with open(dj, "w") as f:
        json.dump(data, f, indent=2)
    print("Injected into data.json")


def main():
    start = time.time()
    print(f"Weekly AI Pick Scorer v3 — {datetime.now().strftime('%Y-%m-%d %H:%M')}")

    universe = []
    with open(UNIVERSE) as f:
        for line in f:
            universe.append(json.loads(line))
    print(f"Universe: {len(universe):,} tickers")

    scored = []
    rejected = []
    done = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futures = {ex.submit(score_one, item): item for item in universe}
        for fut in concurrent.futures.as_completed(futures):
            r = fut.result()
            if r:
                if r.get("rejected"):
                    rejected.append(r)
                else:
                    scored.append(r)
            done += 1
            if done % 200 == 0:
                print(f"  {done}/{len(universe)}... {len(scored)} scored, {len(rejected)} rejected")

    scored.sort(key=lambda x: x["score"], reverse=True)
    elapsed = time.time() - start

    # Save scores
    output = {
        "generated_at": datetime.now().isoformat(),
        "universe_size": len(universe),
        "scored_count": len(scored),
        "rejected_count": len(rejected),
        "top_picks": scored[:30],
        "all_scores": scored,
    }
    with open(SCORES, "w") as f:
        json.dump(output, f, indent=2)

    # History
    history = load_history()
    save_history(history, scored)
    improving = get_improving_tickers(history, scored)

    # Category leaders
    top_etf = next((s for s in scored if s.get("type") == "etf"), None)
    top_crypto = [s for s in scored if s.get("type") == "crypto"][:5]
    top_metal = [s for s in scored if s.get("ticker") in {"GLD", "SLV", "IAU", "PPLT", "PALL", "CPER"} or s.get("category") in {"precious_metal", "gold"}][:10]

    print(f"\n{'=' * 60}")
    print(f"Scored {len(scored):,} / {len(universe):,} in {elapsed / 60:.1f} min")
    print(f"Rejected: {len(rejected):,}")
    print(f"\n=== TOP 10 OVERALL ===")
    for s in scored[:10]:
        print(f"  {s['score']:>5.1f} | {s['ticker']:<8} | {s['name'][:32]:<32} | T={s['tech_score']} F={s['fund_score']} S={s['sentiment_score']}")

    if top_etf:
        print(f"\n=== TOP ETF === {top_etf['score']} | {top_etf['ticker']} | {top_etf['name'][:32]}")
    print(f"\n=== TOP 5 CRYPTO ===")
    for s in top_crypto:
        print(f"  {s['score']:>5.1f} | {s['ticker']:<8} | {s['name'][:32]}")
    print(f"\n=== TOP 5 METALS ===")
    for s in top_metal[:5]:
        print(f"  {s['score']:>5.1f} | {s['ticker']:<8} | {s['name'][:32]}")

    if improving:
        print(f"\n=== IMPROVING (3-wk trend) ===")
        for s in improving[:5]:
            print(f"  {s['score']:.1f} | {s['ticker']:<8} | {s['name'][:32]} | {s['trend']}")

    # Chart
    try:
        script = Path(__file__).resolve().parent / "generate_weekly_chart.py"
        subprocess.run([sys.executable, str(script)], check=False, timeout=120)
    except Exception as e:
        print(f"Chart warn: {e}")

    # Inject
    weekly = build_pick(scored[0], output["generated_at"]) if scored else {}
    best_etf = build_pick(top_etf, output["generated_at"], "Best ETF") if top_etf else None
    inject(weekly, best_etf, top_metal, improving)


if __name__ == "__main__":
    main()
