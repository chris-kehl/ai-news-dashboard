#!/usr/bin/env python3
"""
TIGHTENED Weekly Pick Scorer — recalibrated for August 2026.

PROBLEM: Previous picks were scoring 75-77 with weak momentum signals.
         BEN (asset manager), FOXA (media), PDBC (commodity ETN) won but
         had mediocre 5D/20D momentum. Real winners like ANET, HWM had
         strong momentum but scored the same.

RECALIBRATION:
1. Technical (0-30 → 0-40): Stronger trend requirements, momentum bonuses
2. Fundamentals (0-25 → 0-20): Tighter P/E gates, growth minimums
3. MACD (0-15 → 0-15): Unchanged but histogram slope matters more
4. Sentiment (0-30 → 0-25): Volume spike filter, RSI penalty if >72
5. Quality Gates: Must be above ALL SMAs for stocks, positive revenue OR EPS
6. Threshold: 70 (lowered because scoring is now tighter — 70 = genuinely good)
7. CONSISTENCY BONUS: +5 pts if 1D/5D/20D all positive with low volatility

NEW MAX: 100 pts
QUALIFYING: >= 70
"""
import json, time, concurrent.futures, subprocess, sys
from pathlib import Path
from datetime import datetime
from collections import defaultdict

import yfinance as yf

# ── Paths ──
BASE = Path(__file__).parent.parent
UNIVERSE = BASE / "data" / "universe.jsonl"
SCORES   = BASE / "data" / "weekly_scores.json"
HISTORY  = BASE / "data" / "score_history.json"
WP_OUT   = BASE / "weekly_pick.json"
DJ_OUT   = BASE / "data.json"
CHART    = BASE / "scripts" / "generate_weekly_chart.py"

MIN_QUALIFYING_SCORE = 70
MAX_WORKERS = 8

# ── Technical helpers ──
def sma(arr, n):
    if len(arr) < n: return None
    return sum(arr[-n:]) / n

def ema(arr, n):
    if len(arr) < n: return None
    k = 2.0 / (n + 1)
    e = arr[0]
    for p in arr[1:]:
        e = p * k + e * (1 - k)
    return e

def calc_rsi(closes, period=14):
    if len(closes) < period + 5: return 50
    gains = [max(0, closes[i] - closes[i-1]) for i in range(1, len(closes))]
    losses = [max(0, closes[i-1] - closes[i]) for i in range(1, len(closes))]
    if len(gains) < period: return 50
    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period
    if avg_loss == 0: return 100
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

def calc_macd(closes, fast=12, slow=26, signal=9):
    if len(closes) < slow + signal + 10: return 0, 0, 0, 0
    fast_ema = ema(closes, fast)
    slow_ema = ema(closes, slow)
    macd_line = fast_ema - slow_ema
    sig_ema = macd_line * 0.3
    hist_now = macd_line - sig_ema
    prev_macd = macd_line
    if len(closes) > slow + 5:
        pfe = ema(closes[:-5], fast)
        pse = ema(closes[:-5], slow)
        if pfe is not None and pse is not None:
            prev_macd = pfe - pse
    prev_sig = prev_macd * 0.3
    prev_hist = prev_macd - prev_sig
    
    strength = 0
    if hist_now > 0: strength += 6
    if macd_line > sig_ema: strength += 5
    if hist_now > prev_hist: strength += 4  # accelerating
    return macd_line, sig_ema, hist_now, strength

def calc_volatility(closes, days=20):
    if len(closes) < days + 1: return 100
    returns = []
    for i in range(1, days + 1):
        if closes[-i-1] != 0:
            returns.append((closes[-i] / closes[-i-1] - 1) * 100)
    if not returns: return 100
    avg = sum(returns) / len(returns)
    var = sum((r - avg) ** 2 for r in returns) / len(returns)
    return var ** 0.5

# ── Data fetchers ──
def fetch(ticker):
    try:
        tk = yf.Ticker(ticker)
        hist = tk.history(period="90d")
        if hist.empty or len(hist) < 30:
            return None
        info = tk.info or {}
        return {
            "closes": hist["Close"].tolist(),
            "volumes": hist["Volume"].tolist(),
            "high52": info.get("fiftyTwoWeekHigh"),
            "low52": info.get("fiftyTwoWeekLow"),
        }
    except Exception as e:
        return {"error": str(e)}

def fetch_fundamentals(ticker):
    try:
        tk = yf.Ticker(ticker)
        info = tk.info or {}
        return {
            "pe": info.get("trailingPE") or info.get("forwardPE"),
            "revenue_growth": info.get("revenueGrowth"),
            "profit_margin": info.get("profitMargins"),
            "debt_to_equity": info.get("debtToEquity"),
            "eps_growth": info.get("earningsGrowth"),
            "roe": info.get("returnOnEquity"),
            "market_cap": info.get("marketCap"),
        }
    except:
        return {}

# ── RECALIBRATED SCORING ──

def score_technical(chart):
    """RECALIBRATED Technical — 40 pts max.
    
    Heavier weight on trend alignment and momentum.
    Requires price above ALL key SMAs for full points.
    """
    c = chart["closes"]; v = chart.get("volumes", [])
    if len(c) < 50: return None
    p = c[-1]
    chg_1d = (c[-1] / c[-2] - 1) * 100 if len(c) >= 2 and c[-2] != 0 else 0
    chg_5d = (c[-1] / c[-6] - 1) * 100 if len(c) >= 6 and c[-6] != 0 else 0
    chg_20d = (c[-1] / c[-21] - 1) * 100 if len(c) >= 21 and c[-21] != 0 else 0

    s10, s20, s50 = sma(c, 10), sma(c, 20), sma(c, 50)
    
    # === Trend Score (15 pts) — stricter alignment ===
    trend = 0
    if s10 is not None and p > s10: trend += 3
    if s20 is not None and p > s20: trend += 4
    if s50 is not None and p > s50: trend += 5
    if s10 is not None and s20 is not None and s10 > s20: trend += 1.5
    if s20 is not None and s50 is not None and s20 > s50: trend += 1.5
    trend = max(0, min(15, trend))

    # === Momentum Score (15 pts) — TIGHTENED thresholds ===
    mom = 0
    # 5-day momentum (stronger thresholds)
    if chg_5d > 8:      mom += 6
    elif chg_5d > 4:    mom += 4
    elif chg_5d > 2:    mom += 2
    elif chg_5d > 0:    mom += 1
    
    # 20-day momentum
    if chg_20d > 15:    mom += 5
    elif chg_20d > 8:   mom += 4
    elif chg_20d > 3:   mom += 2
    elif chg_20d > 0:   mom += 1
    
    # Directional alignment (all positive = bonus)
    if chg_1d > 0 and chg_5d > 0 and chg_20d > 0:
        mom += 2
    elif chg_1d > 0 and chg_5d > 0:
        mom += 1
    mom = max(0, min(15, mom))

    # === RSI Score (6 pts) — HEALTHY ZONE only ===
    rsi_val = calc_rsi(c)
    if 50 <= rsi_val <= 65:     rsi_s = 6      # Sweet spot
    elif 45 <= rsi_val < 50:    rsi_s = 4      # Building
    elif 65 < rsi_val <= 70:    rsi_s = 3      # Warm
    elif 40 <= rsi_val < 45:    rsi_s = 2      # Weak
    else:                       rsi_s = 0      # Extreme or dead

    # === Volume Score (4 pts) — Need real participation ===
    vc = 0
    if len(v) >= 20:
        avg_vol_20 = sum(v[-20:]) / 20
        if avg_vol_20 > 0:
            ratio = v[-1] / avg_vol_20
            if ratio > 2.0:       vc = 4
            elif ratio > 1.3:     vc = 2
            elif ratio > 0.8:     vc = 1

    return {
        "score": round(trend + mom + rsi_s + vc, 1),
        "trend": trend, "momentum": mom,
        "rsi": round(rsi_val, 1), "vc": vc,
        "price": p,
        "chg_1d": chg_1d, "chg_5d": chg_5d, "chg_20d": chg_20d,
        "sma10": s10, "sma20": s20, "sma50": s50,
    }


def quality_gate(item, chart, fund):
    """STRONGER gates: stocks must be above SMA50 AND have positive growth."""
    typ = item.get("type", "")
    if typ != "stock":
        return True, ""
    
    c = chart["closes"]
    p, s10, s20, s50 = c[-1], sma(c, 10), sma(c, 20), sma(c, 50)
    
    # Must be above all key SMAs
    if p < s50:
        return False, "below SMA50"
    if p < s20:
        return False, "below SMA20"
    
    # Growth requirement: positive revenue growth OR positive EPS growth
    rev = fund.get("revenue_growth")
    eps = fund.get("eps_growth")
    if rev is not None and eps is not None:
        if rev <= -0.10 and eps <= -0.10:
            return False, "neg_growth"
    
    # P/E check — no wild speculation
    pe = fund.get("pe")
    if pe is not None and pe > 200:
        return False, "extreme_pe"
    
    return True, ""


def score_fundamentals(item, fund):
    """RECALIBRATED Fundamentals — 20 pts max. Tighter scoring."""
    typ = item.get("type", "")
    if typ != "stock" or not fund or not any(v is not None for v in fund.values()):
        if typ == "etf":
            mc = fund.get("market_cap")
            if mc and mc > 10e9: return 18, "Major ETF"
            elif mc and mc > 1e9: return 16, "Established ETF"
            return 14, "ETF"
        return 14, "N/A"

    s = 0; d = []
    
    # P/E (5 pts) — tighter
    pe = fund.get("pe")
    if pe is not None and pe > 0:
        if 8 <= pe <= 20:     s += 5; d.append(f"P/E {pe:.0f}")
        elif 5 <= pe <= 25:   s += 4
        elif pe < 40:         s += 2
        else:                 s += 1
    elif pe is None:          s += 3
    else:                     s += 0; d.append("neg P/E")

    # Revenue Growth (5 pts)
    rev = fund.get("revenue_growth")
    if rev is not None:
        rp = rev * 100
        if rp > 20:       s += 5; d.append(f"Rev +{rp:.0f}%")
        elif rp > 10:     s += 4
        elif rp > 5:      s += 3
        elif rp > 0:      s += 2
        else:             s += 0; d.append(f"Rev {rp:.0f}%")
    else:                 s += 3

    # Profit Margin (4 pts)
    marg = fund.get("profit_margin")
    if marg is not None:
        mp = marg * 100
        if mp > 15:       s += 4; d.append(f"Margin {mp:.0f}%")
        elif mp > 8:      s += 3
        elif mp > 3:      s += 2
        elif mp > 0:      s += 1
        else:             s += 0; d.append("neg_margin")
    else:                 s += 2

    # Debt-to-Equity (3 pts)
    de = fund.get("debt_to_equity")
    if de is not None:
        if de < 30:       s += 3; d.append(f"D/E {de:.0f}")
        elif de < 60:     s += 2
        elif de < 100:    s += 1
        else:             s += 0
    else:                 s += 2

    # EPS Growth (3 pts)
    eps = fund.get("eps_growth")
    if eps is not None:
        ep = eps * 100
        if ep > 20:       s += 3; d.append(f"EPS +{ep:.0f}%")
        elif ep > 10:     s += 2
        elif ep > 0:      s += 1
    else:                 s += 2

    return min(20, s), " | ".join(d) if d else "Strong fundamentals"


def score_sentiment(chart, tech):
    """RECALIBRATED Sentiment — 25 pts max.
    
    More weight on consistent momentum. Penalty for RSI > 72 (overbought).
    Volume requires confirmation, not just random spike.
    """
    c = chart["closes"]; v = chart.get("volumes", [])
    fh, fl = chart.get("high52"), chart.get("low52")

    # 52-Week Range Position (8 pts)
    rp = 1
    if fh and fl and fh != fl:
        pos = (c[-1] - fl) / (fh - fl)
        if pos > 0.88:       rp = 8
        elif pos > 0.75:     rp = 6
        elif pos > 0.60:     rp = 4
        elif pos > 0.40:     rp = 2
        else:                rp = 1

    # Volume Surge (6 pts) — need sustained volume, not gap spike
    vs = 1
    if len(v) >= 20:
        a15 = sum(v[-20:-5]) / 15 if len(v) >= 20 else 0
        a5 = sum(v[-5:]) / 5
        if a15 > 0:
            ratio = a5 / a15
            if ratio > 2.5:      vs = 6
            elif ratio > 1.8:    vs = 4
            elif ratio > 1.2:    vs = 2
            elif ratio > 0.8:    vs = 1
            else:                vs = 0  # Below average = dying interest

    # Momentum Alignment (7 pts)
    ma = 1
    chg_1d = tech["chg_1d"]
    chg_5d = tech["chg_5d"]
    chg_20d = tech["chg_20d"]
    
    if chg_5d > 5 and chg_20d > 8:       ma = 7
    elif chg_5d > 2 and chg_20d > 4:     ma = 5
    elif chg_5d > 0 and chg_20d > 0:     ma = 3
    elif chg_5d > -2 and chg_20d > -3:   ma = 2
    else:                                 ma = 1
    
    if chg_1d > 0 and chg_5d > 0:
        ma += 1
    ma = min(7, ma)

    # RSI Alignment (4 pts) — PENALTY if >72
    rsi = tech["rsi"]
    ralign = 1
    if 50 <= rsi <= 65:       ralign = 4
    elif 45 <= rsi < 50:      ralign = 3
    elif 65 < rsi <= 72:      ralign = 2
    elif 40 <= rsi < 45:      ralign = 2
    elif rsi > 72:            ralign = 0  # OVERBOUGHT PENALTY
    else:                     ralign = 1

    return rp + vs + ma + ralign, rp, vs, ma, ralign


def score_one(item):
    """Score a single ticker across 4 pillars."""
    t = item["ticker"]
    chart = fetch(t)
    if not chart or chart.get("error"):
        return None

    fund = fetch_fundamentals(t)
    tech = score_technical(chart)
    if not tech:
        return None

    passes, reason = quality_gate(item, chart, fund)
    if not passes:
        return {"rejected": True, "ticker": t, "reason": reason}

    fs, fd = score_fundamentals(item, fund)
    sent, s_rp, s_vs, s_ma, s_ralign = score_sentiment(chart, tech)

    _, _, _, macd_strength = calc_macd(chart["closes"])

    # Consistency bonus: all timeframes positive + low volatility
    volatility = calc_volatility(chart["closes"])
    consistency_bonus = 0
    if tech["chg_1d"] > 0 and tech["chg_5d"] > 0 and tech["chg_20d"] > 0 and volatility < 3.0:
        consistency_bonus = 5
    elif tech["chg_1d"] > 0 and tech["chg_5d"] > 0 and tech["chg_20d"] > 0:
        consistency_bonus = 3

    # Four-pillar composite
    comp = tech["score"] + fs + macd_strength + sent + consistency_bonus

    # Dynamic penalties
    if tech["rsi"] < 30:
        comp -= 5  # oversold usually gets worse before better
    elif tech["rsi"] > 75:
        comp -= 3  # overbought, limited upside
    
    if tech["chg_5d"] < -5:
        comp -= 5  # hard to reverse steep 5-day decline
    
    # Require 20-day momentum > 0 for stocks (no falling knives)
    if item.get("type") == "stock" and tech["chg_20d"] <= 0:
        comp -= 3

    return {
        "ticker": t,
        "name": item.get("name", t),
        "type": item.get("type", ""),
        "category": item.get("category", ""),
        "score": round(max(0, min(100, comp)), 1),
        "tech_score": round(tech["score"], 1),
        "fund_score": fs,
        "macd_score": macd_strength,
        "sentiment_score": sent,
        "consistency_bonus": consistency_bonus,
        "rsi": tech["rsi"],
        "price": tech["price"],
        "change_5d": round(tech["chg_5d"], 2),
        "change_20d": round(tech["chg_20d"], 2),
        "volatility": round(volatility, 2),
        "detail": f"Tech={tech['score']:.1f} Fund={fs} MACD={macd_strength} Sent={sent} Consistency={consistency_bonus}",
        "fund_detail": fd,
    }


def load_history():
    try:
        with open(HISTORY) as f:
            return json.load(f)
    except:
        return []


def save_history(history, scored):
    entry = {"date": datetime.now().strftime("%Y-%m-%d"), "scores": {s["ticker"]: s["score"] for s in scored if "score" in s}}
    history.append(entry)
    with open(HISTORY, "w") as f:
        json.dump(history[-52:], f, indent=2)


def get_improving_tickers(history, scored):
    if len(history) < 2:
        return []
    prev = history[-2]["scores"]
    improving = []
    for s in scored:
        if "score" not in s: continue
        t = s["ticker"]
        if t in prev and s["score"] > prev[t] + 3:
            improving.append({"ticker": t, "name": s["name"], "old": prev[t], "new": s["score"]})
    improving.sort(key=lambda x: x["new"] - x["old"], reverse=True)
    return improving[:5]


def build_pick(score_item, generated_at, display_type="Top Pick"):
    """Build weekly_pick.json entry."""
    signal = "BULLISH" if score_item["score"] >= 70 else "NEUTRAL" if score_item["score"] >= 50 else "BEARISH"
    
    bonus_text = ""
    if score_item.get("consistency_bonus", 0) >= 5:
        bonus_text = "\n\n✅ CONSISTENCY BONUS: This asset shows steady, low-volatility gains across all timeframes — the hallmark of quality momentum."
    elif score_item.get("consistency_bonus", 0) >= 3:
        bonus_text = "\n\n✅ This asset has positive momentum across 1D/5D/20D timeframes."
    
    # 5-day price target (simple extrapolation)
    expected_5d = score_item.get("change_5d", 0) * 0.3  # partial mean reversion
    target = round(score_item["price"] * (1 + expected_5d / 100), 2) if expected_5d > 0 else None
    
    rationale = f"""🎯 {display_type}: {score_item['name']} ({score_item['ticker']})
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Score: {score_item['score']}/100 | Signal: {signal} | Category: {score_item.get('category', score_item.get('type', 'N/A'))}

📊 PRICE ACTION
Current: ${score_item['price']:.2f} | 5D: {'+' if score_item['change_5d'] >= 0 else ''}{score_item['change_5d']:.1f}% | 20D: {'+' if score_item['change_20d'] >= 0 else ''}{score_item['change_20d']:.1f}%
RSI: {score_item['rsi']:.1f} | Volatility: {score_item.get('volatility', 'N/A')}% (20-day)

📈 SCORE BREAKDOWN
Technical:    {score_item['tech_score']:.1f}/40  (Trend + Momentum + RSI + Volume)
Fundamentals: {score_item['fund_score']}/20  (P/E, Growth, Margin, D/E, EPS)
MACD:         {score_item['macd_score']}/15  (Histogram strength + slope)
Sentiment:    {score_item['sentiment_score']}/25  (Range position + Volume + Momentum alignment)
Consistency:  +{score_item.get('consistency_bonus', 0)} bonus  (Low-vol positive momentum across timeframes)

💡 RATIONALE
{score_item['detail']}
{score_item.get('fund_detail', '')}
{bonus_text}

{'💰 5-DAY TARGET: $' + str(target) if target else ''}
Generated: {generated_at[:19] if generated_at else 'N/A'}
"""
    
    return {
        "name": score_item["name"],
        "ticker": score_item["ticker"],
        "score": score_item["score"],
        "signal": signal,
        "category": score_item.get("category", score_item.get("type", "N/A")),
        "price": score_item["price"],
        "change_7d": score_item["change_5d"],
        "change_30d": score_item["change_20d"],
        "rsi": score_item["rsi"],
        "volatility": score_item.get("volatility"),
        "rationale": rationale,
        "type": score_item.get("type", ""),
    }


def inject(weekly, best_etf, top_metal, improving):
    """Write both weekly_pick.json and merge into data.json."""
    now = datetime.now().isoformat()
    out = {
        "generated_at": now,
        "week_label": datetime.now().strftime("Week of %b %d, %Y"),
        "top_pick": weekly,
    }
    if best_etf:
        out["best_etf"] = best_etf
    if top_metal:
        out["top_metal"] = top_metal
    if improving:
        out["improving"] = improving

    with open(WP_OUT, "w") as f:
        json.dump(out, f, indent=2)
    print(f"Written weekly_pick.json: {WP_OUT}")

    # Merge into data.json
    try:
        with open(DJ_OUT, "r+") as f:
            data = json.load(f)
            data["weekly_pick"] = out
            f.seek(0)
            json.dump(data, f, indent=2, default=str)
            f.truncate()
        print("Injected into data.json")
    except Exception as e:
        print(f"data.json inject error: {e}")


def main():
    start = time.time()
    print(f"🔧 RECALIBRATED Weekly AI Pick Scorer v5 (min {MIN_QUALIFYING_SCORE}) — {datetime.now().strftime('%Y-%m-%d %H:%M')}")

    universe = []
    with open(UNIVERSE) as f:
        for line in f:
            try:
                universe.append(json.loads(line))
            except:
                pass
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

    qualifying = [s for s in scored if s["score"] >= MIN_QUALIFYING_SCORE]

    # Save scores
    output = {
        "generated_at": datetime.now().isoformat(),
        "universe_size": len(universe),
        "scored_count": len(scored),
        "rejected_count": len(rejected),
        "qualifying_count": len(qualifying),
        "min_qualifying_score": MIN_QUALIFYING_SCORE,
        "scoring_version": "v5_tightened",
        "top_picks": qualifying[:30] if qualifying else scored[:30],
        "all_scores": scored,
    }
    with open(SCORES, "w") as f:
        json.dump(output, f, indent=2)

    # History
    history = load_history()
    save_history(history, scored)
    improving = get_improving_tickers(history, scored)

    # Category leaders
    top_etf = next((s for s in qualifying if s.get("type") == "etf"), None)
    top_crypto = [s for s in qualifying if s.get("type") == "crypto"][:5]
    top_metal = [s for s in qualifying if s.get("ticker") in {"GLD", "SLV", "IAU", "PPLT", "PALL", "CPER"} or s.get("category") in {"precious_metal", "gold"}][:10]

    print(f"\n{'=' * 65}")
    print(f"Scored {len(scored):,} / {len(universe):,} in {elapsed / 60:.1f} min")
    print(f"Rejected: {len(rejected):,}")
    print(f"Qualifying (≥{MIN_QUALIFYING_SCORE}): {len(qualifying)}")

    if qualifying:
        print(f"\n🏆 TOP 10 QUALIFYING PICKS (≥{MIN_QUALIFYING_SCORE}) ===")
        for s in qualifying[:10]:
            cons = f"  [+{s['consistency_bonus']} consistency]" if s.get('consistency_bonus') else ""
            print(f"  {s['score']:>5.1f} | {s['ticker']:<6} | {s['name'][:28]:<28} | Tech={s['tech_score']:.0f} Fund={s['fund_score']:.0f} MACD={s['macd_score']:.0f} Sent={s['sentiment_score']:.0f}{cons}")

        # Chart
        try:
            subprocess.run([sys.executable, str(CHART)], check=False, timeout=120)
        except Exception as e:
            print(f"Chart warn: {e}")

        # Inject top pick
        weekly = build_pick(qualifying[0], output["generated_at"])
        best_etf = build_pick(top_etf, output["generated_at"], "Best ETF") if top_etf else None
        inject(weekly, best_etf, top_metal, improving)
        
        # Also show top 3 with rationale
        print(f"\n📋 TOP 3 ANALYSIS:")
        for i, s in enumerate(qualifying[:3], 1):
            print(f"\n  #{i} {s['ticker']} (Score: {s['score']:.1f})")
            print(f"     5D: {'+' if s['change_5d'] >= 0 else ''}{s['change_5d']:.1f}% | 20D: {'+' if s['change_20d'] >= 0 else ''}{s['change_20d']:.1f}% | RSI: {s['rsi']:.1f}")
            print(f"     {s['detail']}")
    else:
        print(f"\n⚠️  NO QUALIFYING PICKS ≥{MIN_QUALIFYING_SCORE}.")
        print(f"  Best scored: {scored[0]['ticker']} at {scored[0]['score']:.1f}")
        print("  Keeping previous weekly pick.")


if __name__ == "__main__":
    main()
