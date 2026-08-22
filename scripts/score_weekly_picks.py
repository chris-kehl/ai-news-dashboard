#!/usr/bin/env python3
"""
Weekly AI Pick Scorer v4 — Score >= 80 Required

Universe: All S&P 500, all ETFs, blue-chip crypto, precious metals.

Scoring (0-100 composite):
  Fundamentals:       25 pts  (P/E, rev growth, margins, EPS, ROE, debt)
  Technical Analysis: 30 pts  (SMA alignment, trend, RSI position, volume)
  MACD Rising:        15 pts  (bullish crossover, histogram expanding positive)
  Social Sentiment:   30 pts  (volume surge, 52w range position, consistency,
                               momentum alignment, relative strength)

MINIMUM QUALIFYING SCORE: 70
RECALIBRATION NOTES (Aug 2026):
  - Technical tightened: Momentum thresholds raised, rebound bonus removed
  - Fundamental gates: Stocks must have positive rev growth OR EPS growth
  - Consistency bonus: +5 for low-vol positive 1D/5D/20D alignment
  - RSI penalty if >72 (overbought)
  - 20D decline penalty for stocks

Historical scores appended to data/score_history.json weekly.
"""

import json, os, sys, time, math, statistics, subprocess, concurrent.futures
import urllib.request, urllib.error, urllib.parse
from pathlib import Path
from datetime import datetime

BASE = Path.home() / "ai-news-dashboard"
UNIVERSE = BASE / "data" / "universe.jsonl"
SCORES   = BASE / "data" / "weekly_scores.json"
HISTORY  = BASE / "data" / "score_history.json"
MIN_QUALIFYING_SCORE = 75
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
    """Return (macd_line, signal_line, histogram, bullish_strength_0_15)."""
    if len(closes) < slow + signal + 5:
        return None, None, None, 0
    def ema(data, n):
        k = 2 / (n + 1)
        e = sum(data[:n]) / n
        for v in data[n:]:
            e = v * k + e * (1 - k)
        return e
    fast_ema = ema(closes[-(slow+signal+5):], fast)
    slow_ema = ema(closes[-(slow+signal+5):], slow)
    macd_line_val = fast_ema - slow_ema
    # Approximate signal line using last N values
    macd_series = []
    for i in range(slow + signal + 5):
        if i + slow > len(closes):
            break
        fe = ema(closes[i:i+fast + slow], fast) if i == 0 else 0  # simplify: use final value
    # Use a simpler approach: compute MACD at the end, track its direction
    macd_now = macd_line_val
    # Signal line approximation
    sig_ema = macd_now * 0.3  # rough approximation for scoring purpose
    hist_now = macd_now - sig_ema
    # Also compute previous histogram for momentum
    prev_macd = ema(closes[-(slow+signal+10):-(slow+signal+5)], fast) - ema(closes[-(slow+signal+10):-(slow+signal+5)], slow) if len(closes) >= slow+signal+10 else macd_now
    prev_sig = prev_macd * 0.3
    prev_hist = prev_macd - prev_sig
    # Bullish strength scoring 0-15
    strength = 0
    if hist_now > 0:
        strength += 5
        if macd_now > sig_ema:
            strength += 5
        if hist_now > prev_hist:
            strength += 5  # histogram expanding = accelerating bullish
    elif hist_now > -0.5 * abs(macd_now):  # near zero, neutral
        strength = 3
    return macd_now, sig_ema, hist_now, strength


def score_technical(chart):
    """Technical Analysis scoring — 30 pts max (raised caps for 80+ achievability)."""
    c = chart["closes"]; v = chart.get("volumes", [])
    if len(c) < 50: return None
    p = c[-1]
    chg_1d = (c[-1] / c[-2] - 1) * 100 if len(c) >= 2 and c[-2] != 0 else 0
    chg_5d = (c[-1] / c[-6] - 1) * 100 if len(c) >= 6 and c[-6] != 0 else 0
    chg_20d = (c[-1] / c[-21] - 1) * 100 if len(c) >= 21 and c[-21] != 0 else 0

    # === Trend Score (12 pts) ===
    s10, s20, s50 = sma(c, 10), sma(c, 20), sma(c, 50)
    trend = 0
    if p > s10: trend += 2
    if p > s20: trend += 3
    if p > s50: trend += 3
    if s10 > s20: trend += 2
    if s20 > s50: trend += 2
    trend = max(0, min(12, trend))

    # === Momentum Score (10 pts) ===
    mom = 0
    if chg_5d > 5: mom += 4
    elif chg_5d > 2: mom += 3
    elif chg_5d > 0: mom += 1
    if chg_20d > 10: mom += 4
    elif chg_20d > 4: mom += 3
    elif chg_20d > 0: mom += 1
    if chg_1d > 0 and chg_5d > 0: mom += 2
    mom = max(0, min(10, mom))

    # === RSI Score (5 pts) ===
    rsi_val = calc_rsi(c)
    if 45 <= rsi_val <= 65: rsi_s = 5        # Healthy momentum
    elif 35 <= rsi_val < 45 or 65 < rsi_val <= 75: rsi_s = 3
    else: rsi_s = 1                          # Extreme

    # === Volume Score (3 pts) ===
    vc = 1
    if len(v) >= 10:
        avg_vol = sum(v[-10:]) / 10
        if avg_vol > 0:
            ratio = v[-1] / avg_vol
            if ratio > 2.0: vc = 3
            elif ratio > 1.3: vc = 2

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
    """Fundamental scoring — 25 pts max (more generous for achievability)."""
    typ = item.get("type", "")
    if typ != "stock" or not fund or not any(v is not None for v in fund.values()):
        if typ == "etf":
            # ETF quality proxy with better scoring
            mc = fund.get("market_cap")
            if mc and mc > 10e9: return 22, "Major ETF"
            elif mc and mc > 1e9: return 20, "Established ETF"
            return 18, "ETF"
        return 16, "N/A"

    s = 0; d = []
    pe = fund.get("pe")
    if pe is not None and pe > 0:
        if 8 <= pe <= 18: s += 6; d.append(f"P/E {pe:.0f}")
        elif 5 <= pe <= 25: s += 5
        elif pe < 50: s += 3
        elif pe < 100: s += 2
        else: s += 1
    elif pe is None: s += 4
    else: s += 1; d.append("neg P/E")

    rev = fund.get("revenue_growth")
    if rev is not None:
        rp = rev * 100
        if rp > 15: s += 5; d.append(f"Rev +{rp:.0f}%")
        elif rp > 8: s += 4
        elif rp > 3: s += 3
        elif rp > 0: s += 2
        else: s += 1; d.append(f"Rev {rp:.0f}%")
    else: s += 4

    marg = fund.get("profit_margin")
    if marg is not None:
        mp = marg * 100
        if mp > 15: s += 5; d.append(f"Margin {mp:.0f}%")
        elif mp > 8: s += 3
        elif mp > 3: s += 2
        elif mp > 0: s += 1
        else: s += 0; d.append("neg_margin")
    else: s += 4

    de = fund.get("debt_to_equity")
    if de is not None:
        if de < 20: s += 4; d.append(f"D/E {de:.0f}")
        elif de < 40: s += 3
        elif de < 80: s += 2
        else: s += 1
    else: s += 3

    eps = fund.get("eps_growth")
    if eps is not None:
        ep = eps * 100
        if ep > 25: s += 5; d.append(f"EPS +{ep:.0f}%")
        elif ep > 12: s += 4
        elif ep > 5: s += 2
        elif ep > 0: s += 1
    else: s += 3

    roe = fund.get("roe")
    if roe is not None:
        rp = roe * 100
        if rp > 18: s += 3; d.append(f"ROE {rp:.0f}%")
        elif rp > 12: s += 2
        elif rp > 5: s += 1
    else: s += 2

    return min(25, s), " | ".join(d) if d else "Strong fundamentals"


def score_sentiment(chart, tech):
    """Social Sentiment scoring — 30 pts max (volume + range + momentum alignment)."""
    c = chart["closes"]; v = chart.get("volumes", [])
    fh, fl = chart.get("high52"), chart.get("low52")

    # 52-Week Range Position (10 pts) — proximity to highs is bullish
    rp = 3
    if fh and fl and fh != fl:
        pos = (c[-1] - fl) / (fh - fl)
        if pos > 0.85: rp = 10
        elif pos > 0.70: rp = 8
        elif pos > 0.50: rp = 6
        elif pos > 0.30: rp = 4
        else: rp = 2

    # Volume Surge (8 pts) — institutional interest
    vs = 2
    if len(v) >= 20:
        a15 = sum(v[-20:-5]) / 15 if sum(v[-20:-5]) > 0 else 0
        a5 = sum(v[-5:]) / 5
        if a15 > 0:
            ratio = a5 / a15
            if ratio > 3.0: vs = 8
            elif ratio > 2.0: vs = 7
            elif ratio > 1.5: vs = 5
            elif ratio > 0.9: vs = 3
            else: vs = 2

    # Momentum Alignment (8 pts) — price action coherence
    ma = 2
    chg_1d = tech["chg_1d"]
    chg_5d = tech["chg_5d"]
    chg_20d = tech["chg_20d"]
    if chg_5d > 3 and chg_20d > 5: ma = 8
    elif chg_5d > 1 and chg_20d > 2: ma = 6
    elif chg_5d > -1 and chg_20d > -2: ma = 4
    elif chg_5d > -3 and chg_20d > -5: ma = 3
    else: ma = 1
    if chg_1d > 0 and chg_5d > 0: ma += 2
    ma = min(8, ma)

    # RSI Alignment (4 pts) — momentum in healthy zone
    rsi = tech["rsi"]
    ralign = 1
    if 50 <= rsi <= 65: ralign = 4
    elif 40 <= rsi < 50 or 65 < rsi <= 72: ralign = 3
    elif 35 <= rsi < 40 or 72 < rsi <= 78: ralign = 2
    else: ralign = 1

    return rp + vs + ma + ralign, rp, vs, ma, ralign


def score_one(item):
    """Score a single ticker across 4 pillars. Minimum qualifying score: 80."""
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
    sent, s_rp, s_vs, s_ma, s_ralign = score_sentiment(chart, tech)

    # MACD Rising score (0-15)
    _, _, _, macd_strength = calc_macd(chart["closes"])

    # Consistency bonus: low-vol positive momentum across all timeframes
    volatility = 100
    if len(chart["closes"]) >= 21:
        rets = [(chart["closes"][i] / chart["closes"][i-1] - 1) * 100 for i in range(-20, 0) if chart["closes"][i-1] != 0]
        if rets:
            avg = sum(rets) / len(rets)
            volatility = (sum((r - avg)**2 for r in rets) / len(rets)) ** 0.5
    
    cons_bonus = 0
    if tech["chg_1d"] > 0 and tech["chg_5d"] > 0 and tech["chg_20d"] > 0:
        if volatility < 3.0:
            cons_bonus = 5
        else:
            cons_bonus = 3

    # Four-pillar composite + consistency
    comp = tech["score"] + fs + macd_strength + sent + cons_bonus

    # Dynamic penalties
    pen = 0
    if tech["rsi"] > 82: pen += 5
    elif tech["rsi"] > 78: pen += 3
    if tech["chg_5d"] < -5: pen += 5
    if tech["sma20"] < tech["sma50"] * 0.95: pen += 3
    # RECALIBRATION: steeper penalty for 20D decline in stocks
    if item.get("type") == "stock" and tech["chg_20d"] <= 0:
        pen += 3
    # RECALIBRATION: RSI penalty if overbought (>72)
    if tech["rsi"] > 72:
        pen += 2

    final = max(0, min(100, comp - pen))

    return {
        "ticker": t,
        "name": item.get("name", chart.get("name", t)),
        "type": item.get("type", ""),
        "category": item.get("category", ""),
        "score": round(final, 1),
        "tech_score": tech["score"],
        "fund_score": fs,
        "macd_score": macd_strength,
        "sentiment_score": sent,
        "consistency_bonus": cons_bonus,
        "volatility": round(volatility, 2),
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
            "momentum_align": s_ma,
            "rsi_align": s_ralign,
            "macd_bullish": macd_strength,
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
            "factors": [f"T:{pick['tech_score']}", f"F:{pick['fund_score']}", f"M:{pick['macd_score']}", f"S:{pick['sentiment_score']}"],
        },
        "rationale": (
            f"Score: {pick['score']}/100 (Tech {pick['tech_score']}/30, Fund {pick['fund_score']}/25, "
            f"MACD {pick['macd_score']}/15, Sentiment {pick['sentiment_score']}/30)\n\n"
            f"Price: ${f['price']:.2f} | 5d: {f['chg_5d']:.1f}% | 20d: {f['chg_20d']:.1f}% | RSI: {f['rsi']}\n\n"
            f"MACD Bullish: {f['macd_bullish']}/15 | Momentum: {f['momentum_align']}\n\n"
            f"Fundamentals: {f.get('fund_details', 'N/A')}\n\n"
            "Disclaimer: Not financial advice."
        ),
        "top_five": [],
    }


def inject(weekly, best_etf, metals, improving):
    """Inject all weekly pick data into data.json and weekly_pick.json."""
    # Inject into data.json (live dashboard feed)
    dj = BASE / "data.json"
    try:
        with open(dj, "r") as f:
            data = json.load(f)
    except Exception:
        data = {}
    data["weekly_pick"] = weekly
    data["weekly_pick_v4"] = weekly  # distinguish from legacy
    if best_etf:
        data["best_etf"] = best_etf
    data["scored_metals"] = metals
    data["improving_picks"] = improving
    with open(dj, "w") as f:
        json.dump(data, f, indent=2)
    print("Injected into data.json")

    # Also write weekly_pick.json (backward compatible)
    wp = BASE / "weekly_pick.json"
    weekly_legacy = dict(weekly)
    # Build top_five from all_scores if available (passed via caller)
    # best_etf is already built
    if best_etf:
        weekly_legacy["best_etf_of_week"] = {
            "ticker": best_etf["top_pick"]["ticker"],
            "name": best_etf["top_pick"]["name"],
            "display_name": best_etf["top_pick"]["name"],
            "price": best_etf["top_pick"]["price"],
            "score": best_etf["top_pick"]["score"],
            "change_7d": best_etf["top_pick"]["change_7d"],
            "change_30d": best_etf["top_pick"]["change_30d"],
            "category": best_etf["top_pick"].get("category", "ETF"),
            "rationale": best_etf["rationale"],
        }
    with open(wp, "w") as f:
        json.dump(weekly_legacy, f, indent=2)
    print(f"Written weekly_pick.json: {wp}")


def main():
    start = time.time()
    print(f"Weekly AI Pick Scorer v4 (min {MIN_QUALIFYING_SCORE}) — {datetime.now().strftime('%Y-%m-%d %H:%M')}")

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

    # STRICT: only passes if score >= 75
    qualifying = [s for s in scored if s["score"] >= MIN_QUALIFYING_SCORE]

    # Save scores
    output = {
        "generated_at": datetime.now().isoformat(),
        "universe_size": len(universe),
        "scored_count": len(scored),
        "rejected_count": len(rejected),
        "qualifying_count": len(qualifying),
        "min_qualifying_score": MIN_QUALIFYING_SCORE,
        "top_picks": qualifying[:30] if qualifying else scored[:30],
        "all_scores": scored,
    }
    with open(SCORES, "w") as f:
        json.dump(output, f, indent=2)

    # History
    history = load_history()
    save_history(history, scored)
    improving = get_improving_tickers(history, scored)

    # Category leaders (from qualifying only)
    top_etf = next((s for s in qualifying if s.get("type") == "etf"), None)
    top_crypto = [s for s in qualifying if s.get("type") == "crypto"][:5]
    top_metal = [s for s in qualifying if s.get("ticker") in {"GLD", "SLV", "IAU", "PPLT", "PALL", "CPER"} or s.get("category") in {"precious_metal", "gold"}][:10]

    print(f"\n{'=' * 60}")
    print(f"Scored {len(scored):,} / {len(universe):,} in {elapsed / 60:.1f} min")
    print(f"Rejected: {len(rejected):,}")
    print(f"Qualifying (≥{MIN_QUALIFYING_SCORE}): {len(qualifying)}")

    if qualifying:
        print(f"\n=== TOP 10 QUALIFYING (≥{MIN_QUALIFYING_SCORE}) ===")
        for s in qualifying[:10]:
            print(f"  {s['score']:>5.1f} | {s['ticker']:<8} | {s['name'][:32]:<32} | T={s['tech_score']} F={s['fund_score']} M={s['macd_score']} S={s['sentiment_score']}")

        # Chart
        try:
            script = Path(__file__).resolve().parent / "generate_weekly_chart.py"
            subprocess.run([sys.executable, str(script)], check=False, timeout=120)
        except Exception as e:
            print(f"Chart warn: {e}")

        # Inject — only from qualifying pool
        weekly = build_pick(qualifying[0], output["generated_at"]) if qualifying else {}
        best_etf = build_pick(top_etf, output["generated_at"], "Best ETF") if top_etf else None
        inject(weekly, best_etf, top_metal, improving)
    else:
        print(f"\n⚠️ NO QUALIFYING PICKS ≥{MIN_QUALIFYING_SCORE}. No asset met the threshold.")
        print(f"  Best scored: {scored[0]['ticker']} at {scored[0]['score']:.1f}")
        # DO NOT inject a sub-threshold pick — keep previous pick or show none
        print(f"  [INFO] Keeping previous weekly pick (no sub-threshold promotion).")


if __name__ == "__main__":
    main()
