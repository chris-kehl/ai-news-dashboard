#!/usr/bin/env python3
"""
RECALIBRATED Weekly Scorer — August 17, 2026
Tighter thresholds, consistency bonus, no-rebound rule.
Sequential processing for reliability. Focused universe (top 300 liquid assets).
"""
import json, time, sys, statistics
from pathlib import Path
from datetime import datetime
from collections import OrderedDict

import yfinance as yf

BASE = Path.home() / "ai-news-dashboard"
UNIVERSE = BASE / "data" / "universe.jsonl"
SCORES   = BASE / "data" / "weekly_scores.json"
HISTORY  = BASE / "data" / "score_history.json"
WP_OUT   = BASE / "weekly_pick.json"
DJ_OUT   = BASE / "data.json"
CHART    = BASE / "scripts" / "generate_weekly_chart.py"

MIN_SCORE = 70

def sma(arr, n):
    return sum(arr[-n:]) / n if len(arr) >= n else None

def calc_rsi(closes, period=14):
    if len(closes) < period + 5: return 50
    gains, losses = [], []
    for i in range(1, min(len(closes), period + 15)):
        chg = closes[i] - closes[i-1]
        gains.append(max(0, chg))
        losses.append(max(0, -chg))
    if len(gains) < period: return 50
    avg_g = sum(gains[-period:]) / period
    avg_l = sum(losses[-period:]) / period
    if avg_l == 0: return 100
    return 100 - (100 / (1 + avg_g / avg_l))

def ema(arr, n):
    if len(arr) < n: return None
    k = 2.0 / (n + 1)
    e = arr[0]
    for p in arr[1:]:
        e = p * k + e * (1 - k)
    return e

def calc_macd(closes):
    if len(closes) < 40: return 0, 0, 0, 0
    fe = ema(closes, 12)
    se = ema(closes, 26)
    if fe is None or se is None: return 0, 0, 0, 0
    macd = fe - se
    sig = macd * 0.3
    hist = macd - sig
    # prev
    pm = macd
    if len(closes) > 31:
        pfe = ema(closes[:-5], 12)
        pse = ema(closes[:-5], 26)
        if pfe is not None and pse is not None:
            pm = pfe - pse
    ps = pm * 0.3
    ph = pm - ps
    strength = 0
    if hist > 0: strength += 6
    if macd > sig: strength += 5
    if hist > ph: strength += 4
    return macd, sig, hist, strength

def calc_vol(closes, days=20):
    if len(closes) < days + 1: return 100
    rets = []
    for i in range(1, days + 1):
        if closes[-i-1] != 0:
            rets.append((closes[-i] / closes[-i-1] - 1) * 100)
    if not rets: return 100
    avg = sum(rets) / len(rets)
    return (sum((r - avg)**2 for r in rets) / len(rets)) ** 0.5

def score_one(item):
    t = item["ticker"]
    try:
        tk = yf.Ticker(t)
        hist = tk.history(period="90d")
        if hist.empty or len(hist) < 30:
            return None
        info = tk.info or {}
        c = hist["Close"].tolist()
        v = hist["Volume"].tolist()
        p = c[-1]
        
        # Early SMA gate for stocks
        s10, s20, s50 = sma(c, 10), sma(c, 20), sma(c, 50)
        typ = item.get("type", "")
        
        if typ == "stock":
            if s50 is not None and p < s50: return {"rejected": True, "ticker": t, "reason": "below_SMA50"}
            if s20 is not None and p < s20: return {"rejected": True, "ticker": t, "reason": "below_SMA20"}
        
        chg_1d = (c[-1] / c[-2] - 1) * 100 if len(c) >= 2 and c[-2] != 0 else 0
        chg_5d = (c[-1] / c[-6] - 1) * 100 if len(c) >= 6 and c[-6] != 0 else 0
        chg_20d = (c[-1] / c[-21] - 1) * 100 if len(c) >= 21 and c[-21] != 0 else 0
        
        # TECHNICAL (0-40)
        trend = 0
        if s10 is not None and p > s10: trend += 3
        if s20 is not None and p > s20: trend += 4
        if s50 is not None and p > s50: trend += 5
        if s10 is not None and s20 is not None and s10 > s20: trend += 1.5
        if s20 is not None and s50 is not None and s20 > s50: trend += 1.5
        trend = max(0, min(15, trend))
        
        mom = 0
        if chg_5d > 8: mom += 6
        elif chg_5d > 4: mom += 4
        elif chg_5d > 2: mom += 2
        elif chg_5d > 0: mom += 1
        if chg_20d > 15: mom += 5
        elif chg_20d > 8: mom += 4
        elif chg_20d > 3: mom += 2
        elif chg_20d > 0: mom += 1
        if chg_1d > 0 and chg_5d > 0 and chg_20d > 0: mom += 2
        elif chg_1d > 0 and chg_5d > 0: mom += 1
        mom = max(0, min(15, mom))
        
        rsi = calc_rsi(c)
        if 50 <= rsi <= 65: rsi_s = 6
        elif 45 <= rsi < 50: rsi_s = 4
        elif 65 < rsi <= 70: rsi_s = 3
        elif 40 <= rsi < 45: rsi_s = 2
        else: rsi_s = 0
        
        vc = 0
        if len(v) >= 20:
            a15 = sum(v[-20:-5]) / 15
            a5 = sum(v[-5:]) / 5
            if a15 > 0:
                ratio = a5 / a15
                if ratio > 2.0: vc = 4
                elif ratio > 1.3: vc = 2
                elif ratio > 0.8: vc = 1
        tech = trend + mom + rsi_s + vc
        
        # FUNDAMENTAL (0-20)
        pe = info.get("trailingPE") or info.get("forwardPE")
        rev = info.get("revenueGrowth")
        eps = info.get("earningsGrowth")
        marg = info.get("profitMargins")
        de = info.get("debtToEquity")
        roe = info.get("returnOnEquity")
        mc = info.get("marketCap")
        
        # Gate: stock must have positive rev OR eps growth
        if typ == "stock":
            if rev is not None and eps is not None:
                if rev <= -0.10 and eps <= -0.10:
                    return {"rejected": True, "ticker": t, "reason": "neg_growth"}
            if pe is not None and pe > 200:
                return {"rejected": True, "ticker": t, "reason": "extreme_pe"}
        
        if typ != "stock":
            fs = 16 if typ == "etf" and mc and mc > 10e9 else 14
            fd = []
        elif not pe and not rev and not eps and not marg:
            fs = 14
            fd = []
        else:
            fs = 0; fd = []
            if pe and pe > 0:
                if 8 <= pe <= 20: fs += 5; fd.append(f"P/E {pe:.0f}")
                elif 5 <= pe <= 25: fs += 4
                elif pe < 40: fs += 2
                else: fs += 1
            elif pe is None: fs += 3
            else: fs += 0
            
            if rev is not None:
                rp = rev * 100
                if rp > 20: fs += 5; fd.append(f"Rev +{rp:.0f}%")
                elif rp > 10: fs += 4
                elif rp > 5: fs += 3
                elif rp > 0: fs += 2
                else: fs += 0
            else: fs += 3
            
            if marg is not None:
                mp = marg * 100
                if mp > 15: fs += 4; fd.append(f"Margin {mp:.0f}%")
                elif mp > 8: fs += 3
                elif mp > 3: fs += 2
                elif mp > 0: fs += 1
            else: fs += 2
            
            if de is not None:
                if de < 30: fs += 3; fd.append(f"D/E {de:.0f}")
                elif de < 60: fs += 2
                elif de < 100: fs += 1
            else: fs += 2
            
            if eps is not None:
                ep = eps * 100
                if ep > 20: fs += 3; fd.append(f"EPS +{ep:.0f}%")
                elif ep > 10: fs += 2
                elif ep > 0: fs += 1
            else: fs += 2
            fs = min(20, fs)
        
        # MACD (0-15)
        _, _, _, macd_strength = calc_macd(c)
        
        # SENTIMENT (0-25)
        fh = info.get("fiftyTwoWeekHigh")
        fl = info.get("fiftyTwoWeekLow")
        rp = 1
        if fh and fl and fh != fl:
            pos = (c[-1] - fl) / (fh - fl)
            if pos > 0.88: rp = 8
            elif pos > 0.75: rp = 6
            elif pos > 0.60: rp = 4
            elif pos > 0.40: rp = 2
        
        vs = 1
        if len(v) >= 20:
            a15 = sum(v[-20:-5]) / 15
            a5 = sum(v[-5:]) / 5
            if a15 > 0:
                ratio = a5 / a15
                if ratio > 2.5: vs = 6
                elif ratio > 1.8: vs = 4
                elif ratio > 1.2: vs = 2
                elif ratio > 0.8: vs = 1
                else: vs = 0
        
        ma = 1
        if chg_5d > 5 and chg_20d > 8: ma = 7
        elif chg_5d > 2 and chg_20d > 4: ma = 5
        elif chg_5d > 0 and chg_20d > 0: ma = 3
        elif chg_5d > -2 and chg_20d > -3: ma = 2
        if chg_1d > 0 and chg_5d > 0: ma += 1
        ma = min(7, ma)
        
        ralign = 1
        if 50 <= rsi <= 65: ralign = 4
        elif 45 <= rsi < 50: ralign = 3
        elif 65 < rsi <= 72: ralign = 2
        elif rsi > 72: ralign = 0
        elif 40 <= rsi < 45: ralign = 2
        
        sent = rp + vs + ma + ralign
        
        # CONSISTENCY BONUS
        volatility = calc_vol(c)
        cons_bonus = 0
        if chg_1d > 0 and chg_5d > 0 and chg_20d > 0 and volatility < 3.0:
            cons_bonus = 5
        elif chg_1d > 0 and chg_5d > 0 and chg_20d > 0:
            cons_bonus = 3
        
        # COMPOSITE
        comp = tech + fs + macd_strength + sent + cons_bonus
        
        # PENALTIES
        if rsi < 30: comp -= 5
        elif rsi > 75: comp -= 3
        if chg_5d < -5: comp -= 5
        if typ == "stock" and chg_20d <= 0: comp -= 3
        
        # ATTRACTIVENESS BOOST: if everything is strongly positive
        if chg_5d > 5 and chg_20d > 10 and 45 <= rsi <= 68 and tech >= 25:
            comp += 2
        
        return {
            "ticker": t, "name": item.get("name", t),
            "type": typ, "category": item.get("category", ""),
            "score": round(max(0, min(100, comp)), 1),
            "tech_score": tech, "fund_score": fs,
            "macd_score": macd_strength, "sentiment_score": sent,
            "consistency_bonus": cons_bonus,
            "rsi": round(rsi, 1), "price": p,
            "change_5d": round(chg_5d, 2), "change_20d": round(chg_20d, 2),
            "volatility": round(volatility, 2),
            "detail": f"Tech={tech:.1f} Fund={fs} MACD={macd_strength} Sent={sent} Consistency=+{cons_bonus}",
            "fund_detail": " | ".join(fd) if typ == "stock" and 'fd' in dir() and fd else ("Strong fundamentals" if typ == "stock" else "N/A"),
        }
    except Exception as e:
        return {"rejected": True, "ticker": t, "reason": str(e)[:50]}


def build_pick(s, generated_at):
    signal = "BULLISH" if s["score"] >= 70 else "NEUTRAL" if s["score"] >= 50 else "BEARISH"
    bonus = ""
    if s.get("consistency_bonus", 0) >= 5:
        bonus = "\n\n✅ CONSISTENCY BONUS: Steady low-vol gains across all timeframes."
    elif s.get("consistency_bonus", 0) >= 3:
        bonus = "\n\n✅ Positive momentum across 1D/5D/20D."
    
    target = None
    if s["change_5d"] > 0:
        target = round(s["price"] * (1 + s["change_5d"] * 0.3 / 100), 2)
    
    rationale = f"""🎯 Top Pick: {s['name']} ({s['ticker']})
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Score: {s['score']}/100 | Signal: {signal} | Category: {s.get('category', s.get('type', 'N/A'))}

📊 PRICE ACTION
Current: ${s['price']:.2f} | 5D: {'+' if s['change_5d'] >= 0 else ''}{s['change_5d']:.1f}% | 20D: {'+' if s['change_20d'] >= 0 else ''}{s['change_20d']:.1f}%
RSI: {s['rsi']:.1f} | Volatility: {s.get('volatility', 'N/A')}% (20-day)

📈 SCORE BREAKDOWN
Technical:    {s['tech_score']}/40  (Trend + Momentum + RSI + Volume)
Fundamentals: {s['fund_score']}/20  (P/E, Rev growth, Margin, D/E, EPS)
MACD:         {s['macd_score']}/15  (Histogram + slope)
Sentiment:    {s['sentiment_score']}/25  (Range + Vol + Momentum + RSI)
Consistency:  +{s.get('consistency_bonus', 0)} bonus

💡 RATIONALE
{s['detail']}
{s.get('fund_detail', '')}
{bonus}

{'💰 5-DAY TARGET: $' + str(target) if target else ''}
Generated: {generated_at[:19]}
"""
    return {
        "name": s["name"], "ticker": s["ticker"],
        "score": s["score"], "signal": signal,
        "category": s.get("category", s.get("type", "N/A")),
        "price": s["price"], "change_7d": s["change_5d"],
        "change_30d": s["change_20d"], "rsi": s["rsi"],
        "rationale": rationale,
    }


def inject(wp, generated_at):
    out = {
        "generated_at": generated_at,
        "week_label": datetime.now().strftime("Week of %b %d, %Y"),
        "top_pick": wp,
    }
    with open(WP_OUT, "w") as f:
        json.dump(out, f, indent=2)
    
    with open(DJ_OUT, "r+") as f:
        data = json.load(f)
        data["weekly_pick"] = out
        data["timestamp"] = generated_at
        f.seek(0)
        json.dump(data, f, indent=2, default=str)
        f.truncate()
    print("✅ Injected into data.json + weekly_pick.json")


def main():
    start = time.time()
    now = datetime.now().isoformat()
    print(f"🔧 RECALIBRATED Weekly Scorer v5 — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    
    universe = []
    with open(UNIVERSE) as f:
        for line in f:
            try:
                item = json.loads(line)
                # FOCUSED: only score stocks and major ETFs (skip microcaps / illiquid)
                typ = item.get("type", "")
                if typ in ("stock", "etf"):
                    universe.append(item)
            except:
                pass
    
    print(f"Focused universe: {len(universe):,} (stocks + ETFs only)")
    
    scored = []
    rejected = []
    for i, item in enumerate(universe, 1):
        r = score_one(item)
        if r:
            if r.get("rejected"):
                rejected.append(r)
            else:
                scored.append(r)
        if i % 100 == 0:
            print(f"  {i}/{len(universe)}... {len(scored)} scored, {len(rejected)} rejected")
    
    scored.sort(key=lambda x: x["score"], reverse=True)
    qualifying = [s for s in scored if s["score"] >= MIN_SCORE]
    
    print(f"\n{'=' * 60}")
    print(f"Scored {len(scored):,} in {(time.time()-start)/60:.1f} min")
    print(f"Rejected: {len(rejected):,}")
    print(f"Qualifying (≥{MIN_SCORE}): {len(qualifying)}")
    
    if qualifying:
        print(f"\n🏆 TOP 10 QUALIFYING (≥{MIN_SCORE})")
        for s in qualifying[:10]:
            mark = "★" if s.get('consistency_bonus', 0) >= 5 else ""
            print(f"  {s['score']:>5.1f} | {s['ticker']:<6} | {s['name'][:26]:<26} | 5D={s['change_5d']:>+5.1f}% 20D={s['change_20d']:>+5.1f}% RSI={s['rsi']:>4.1f} {mark}")
        
        # Pick #1
        wp = build_pick(qualifying[0], now)
        inject(wp, now)
        
        print(f"\n📋 TOP 3 ANALYSIS")
        for i, s in enumerate(qualifying[:3], 1):
            print(f"\n  #{i} {s['ticker']} (Score: {s['score']:.1f})")
            print(f"     5D: {'+' if s['change_5d'] >= 0 else ''}{s['change_5d']:.1f}% | 20D: {'+' if s['change_20d'] >= 0 else ''}{s['change_20d']:.1f}% | RSI: {s['rsi']:.1f}")
            print(f"     {s['detail']}")
    else:
        print(f"\n⚠️ NO QUALIFYING PICKS ≥{MIN_SCORE}")
        print(f"  Best: {scored[0]['ticker']} at {scored[0]['score']:.1f}")


if __name__ == "__main__":
    main()
