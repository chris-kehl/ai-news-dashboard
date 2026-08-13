#!/usr/bin/env python3
"""
Weekly AI Pick Scorer — Quality Universe (83 major ETFs + 503 SP500 + crypto + metals)
Scoring: Technical 40, Fundamentals 30, Sentiment 30
"""

import json, time, urllib.request, urllib.error, urllib.parse, math, sys, subprocess, concurrent.futures
from pathlib import Path
from datetime import datetime

UNIVERSE_PATH = Path.home() / "ai-news-dashboard" / "data" / "universe.jsonl"
SCORES_PATH   = Path.home() / "ai-news-dashboard" / "data" / "weekly_scores.json"
MAX_WORKERS   = 40
CHART_TIMEOUT = 12
FUND_TIMEOUT  = 5

# Validated premium universe — no micro-caps, no penny stocks, no obscure tickers
VALIDATED_ETFS = {
    "SPY","QQQ","IWM","DIA","VTI","VOO","IVV","VEA","VWO","EFA","EEM",
    "XLF","XLK","XLE","XLI","XLP","XLU","XLV","XLY","XLB","XLRE",
    "VGT","VHT","VDE","VIS","VDC","VPU","VAW","VNQ","VFH",
    "SOXX","SMH","IBB","XBI","ARKK","ARKG","ARKW","CLOU","BOTZ",
    "LIT","TAN","ICLN","PBW","QCLN","FAN",
    "GLD","SLV","IAU","PPLT","PALL","CPER","USO","UNG","DBA","DBC",
    "TLT","IEF","SHY","LQD","HYG","JNK","BND","AGG","TIP","MBB",
    "UUP","FXE","FXY",
    "IBIT","FBTC","BITO",
}


def fetch_chart(ticker: str):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(ticker)}?interval=1d&range=6mo&includeAdjustedClose=true"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=CHART_TIMEOUT) as resp:
            data = json.loads(resp.read().decode())
        result = data.get("chart", {}).get("result", [None])[0]
        if not result: return None
        meta = result.get("meta", {})
        ind = result.get("indicators", {}).get("quote", [{}])[0]
        closes = [c for c in ind.get("close", []) if c is not None]
        vols = [v for v in ind.get("volume", []) if v is not None]
        return {
            "closes": closes, "volumes": vols,
            "price": closes[-1] if closes else meta.get("regularMarketPrice"),
            "fifty_two_week_high": meta.get("fiftyTwoWeekHigh"),
            "fifty_two_week_low": meta.get("fiftyTwoWeekLow"),
            "name": meta.get("shortName", "") or meta.get("longName", ""),
        }
    except Exception:
        return {"error": True}


def fetch_fund(ticker: str):
    url = f"https://query2.finance.yahoo.com/v10/finance/quoteSummary/{urllib.parse.quote(ticker)}?modules=defaultKeyStatistics,financialData,summaryDetail"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=FUND_TIMEOUT) as resp:
            data = json.loads(resp.read().decode())
        r = data.get("quoteSummary", {}).get("result", [None])
        if not r or not r[0]: return {}
        fd = r[0].get("financialData", {})
        sd = r[0].get("summaryDetail", {})
        return {
            "pe": sd.get("trailingPE"),
            "revenue_growth": fd.get("revenueGrowth"),
            "profit_margin": fd.get("profitMargins"),
            "debt_to_equity": sd.get("debtToEquity"),
            "eps_growth": fd.get("earningsGrowth"),
            "roe": fd.get("returnOnEquity"),
            "current_ratio": fd.get("currentRatio"),
        }
    except Exception:
        return {}


def sma(data, n):
    if not data: return 0
    if len(data) >= n: return sum(data[-n:]) / n
    return sum(data) / len(data)


def calc_rsi(closes, period=14):
    if len(closes) < period + 1: return 50
    g, l = [], []
    for i in range(1, period + 1):
        ch = closes[-i] - closes[-(i + 1)]
        g.append(max(ch, 0)); l.append(abs(min(ch, 0)))
    ag, al = sum(g) / period, sum(l) / period
    if al == 0: return 100
    return 100 - (100 / (1 + ag / al))


def score_technical(chart):
    c = chart["closes"]; v = chart.get("volumes", [])
    if len(c) < 20: return None
    p = c[-1]
    chg_1d = (c[-1] / c[-2] - 1) * 100 if len(c) >= 2 and c[-2] != 0 else 0
    chg_5d = (c[-1] / c[-6] - 1) * 100 if len(c) >= 6 and c[-6] != 0 else 0
    chg_20d = (c[-1] / c[-21] - 1) * 100 if len(c) >= 21 and c[-21] != 0 else 0

    s10, s20, s50 = sma(c, 10), sma(c, 20), sma(c, 50)
    tr = sum([p > s10 and 3, p > s20 and 4, p > s50 and 4, s10 > s20 and 2, s20 > s50 and 2])
    tr = max(0, min(15, tr))

    mom = 0
    if chg_5d > 2: mom += 3
    elif chg_5d > 0: mom += 1
    elif chg_5d < -2: mom -= 2
    if chg_20d > 5: mom += 3
    elif chg_20d > 0: mom += 2
    elif chg_20d < -5: mom -= 3
    if chg_1d > 0 and chg_5d > 0: mom += 2
    elif chg_1d < 0 and chg_5d < 0: mom -= 2
    if abs(chg_5d) < 15: mom += 2
    mom = max(0, min(10, mom))

    rsi_val = calc_rsi(c)
    rsi_s = 5 if 45 < rsi_val < 65 else 4 if 35 <= rsi_val <= 75 else 1

    if len(c) >= 5:
        rets = [(c[i]/c[i-1]-1)*100 for i in range(1,len(c)) if c[i-1] != 0]
        if rets:
            mr = sum(rets)/len(rets)
            vol = math.sqrt(sum((r-mr)**2 for r in rets)/len(rets))
        else: vol = 3
    else: vol = 3
    vol_s = {vol<1:5, vol<1.8:4, vol<2.8:3, vol<4:2}.get(True,1)

    vc = 3
    if len(v) >= 10:
        av = sum(v[-10:])/10
        if av > 0:
            r = v[-1]/av
            vc = {r>1.5:5, r>1.1:4, r>0.7:3}.get(True,2)

    return {
        "score": tr + mom + rsi_s + vol_s + vc,
        "trend": tr, "momentum": mom, "rsi": round(rsi_val,1),
        "vol": round(vol,2), "vc": vc,
        "price": p, "chg_1d": chg_1d, "chg_5d": chg_5d, "chg_20d": chg_20d,
        "sma10": s10, "sma20": s20, "sma50": s50,
    }


def score_fundamentals(fund):
    if not fund or not any(v is not None for v in fund.values()):
        return 15, "No fundamentals data"
    s = 0; d = []
    pe = fund.get("pe")
    if pe is not None:
        if 10 <= pe <= 20: s += 8; d.append(f"P/E {pe:.0f} ✓")
        elif 8 <= pe <= 25: s += 6
        elif pe < 0 or pe > 100: s += 1; d.append(f"P/E {pe:.0f} speculative")
        else: s += 3
    rev = fund.get("revenue_growth")
    if rev is not None:
        rp = rev * 100
        s += {rp>25:7, rp>15:5, rp>5:3}.get(True,1)
        if rp > 15: d.append(f"Rev +{rp:.0f}% ✓")
    else: s += 3
    marg = fund.get("profit_margin")
    if marg is not None:
        mp = marg * 100
        s += {mp>20:5, mp>15:4, mp>8:3, mp>0:1}.get(True,0)
        if mp > 20: d.append(f"Margin {mp:.0f}% ✓")
    else: s += 3
    de = fund.get("debt_to_equity")
    if de is not None:
        s += {de<30:5, de<50:4, de<100:3, de<200:2}.get(True,1)
        if de < 30: d.append(f"D/E {de:.1f} ✓")
    else: s += 3
    eps = fund.get("eps_growth")
    if eps is not None:
        ep = eps * 100
        s += {ep>30:5, ep>20:4, ep>10:3}.get(True,1)
        if ep > 20: d.append(f"EPS +{ep:.0f}% ✓")
    else: s += 3
    return min(30, s), " | ".join(d) if d else "Neutral fundamentals"


def score_sentiment(chart, tech):
    c, v = chart["closes"], chart.get("volumes", [])
    fh, fl = chart.get("fifty_two_week_high"), chart.get("fifty_two_week_low")
    rp = 4
    if fh and fl and fh != fl:
        pos = (c[-1] - fl) / (fh - fl)
        rp = {pos>.85:8, pos>.7:6, pos>.5:5}.get(True, 2)
    vs = 5
    if len(v) >= 20:
        a20, a5 = sum(v[-20:])/20, sum(v[-5:])/5
        if a20 > 0:
            r = a5/a20
            vs = {r>2:10, r>1.5:8, r>1.2:6}.get(True, 3)
    cons = 5
    if len(c) >= 5:
        daily = [(c[i]/c[i-1]-1)*100 for i in range(1,len(c)) if c[i-1] != 0]
        gaps = sum(1 for d in daily if abs(d) > 8)
        cons = {gaps>=3:2, gaps>=1:4}.get(True, 7)
    rsi = tech["rsi"]
    ralign = {40 <= rsi <= 70: 5, 30 <= rsi < 40: 3, 70 < rsi <= 80: 3}.get(True, 1)
    return rp + vs + cons + ralign, rp, vs, cons, ralign


def score_one(item):
    t = item["ticker"]
    chart = fetch_chart(t)
    if not chart or chart.get("error"):
        return None
    
    is_stock = item.get("type") == "stock" and item.get("category") == "sp500"
    is_validated_etf = t in VALIDATED_ETFS
    fund = fetch_fund(t) if is_stock else {}
    
    tech = score_technical(chart)
    if not tech:
        return None
    
    if is_stock:
        fs, fd = score_fundamentals(fund)
    elif is_validated_etf:
        # For validated ETFs, use a quality bonus (they're pre-vetted)
        fs, fd = 20, "Validated Major ETF"
    else:
        fs, fd = 15, "ETF — limited fundamentals"
    
    sent, s_rp, s_vs, s_cons, s_ralign = score_sentiment(chart, tech)
    comp = tech["score"] + fs + sent
    
    pen = 0
    if tech["rsi"] > 80: pen += 10
    if tech["chg_5d"] < -5: pen += 8
    if tech["vol"] > 5: pen += 5
    if fund.get("pe") and fund["pe"] < 0: pen += 5
    if tech["sma20"] < tech["sma50"] * 0.98: pen += 3
    
    final = max(0, min(100, comp - pen))
    
    return {
        "ticker": t, "name": item.get("name", chart.get("name", t)),
        "type": item.get("type", ""), "category": item.get("category", ""),
        "score": round(final, 1), "tech_score": tech["score"],
        "fund_score": fs, "sentiment_score": sent, "penalty": pen,
        "factors": {
            "price": round(tech["price"], 2), "chg_1d": round(tech["chg_1d"], 2),
            "chg_5d": round(tech["chg_5d"], 2), "chg_20d": round(tech["chg_20d"], 2),
            "rsi": tech["rsi"], "volatility": tech["vol"],
            "pe": fund.get("pe"), "fund_details": fd,
            "range_pos": s_rp, "vol_surge": s_vs, "consistency": s_cons,
        }
    }


def main():
    start = time.time()
    print(f"Weekly AI Pick Scorer — Quality Universe — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    
    universe = []
    with open(UNIVERSE_PATH) as f:
        for line in f:
            item = json.loads(line)
            # Only score validated ETFs or stocks or crypto/metals
            if item.get("type") == "etf" and item.get("ticker") not in VALIDATED_ETFS:
                continue  # skip unvalidated micro-ETFs
            universe.append(item)
    
    print(f"Scoring universe: {len(universe):,} tickers (validated ETFs + SP500 + crypto + metals)")
    
    scored = []
    done = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futures = {ex.submit(score_one, item): item for item in universe}
        for fut in concurrent.futures.as_completed(futures):
            r = fut.result()
            if r:
                scored.append(r)
            done += 1
            if done % 200 == 0:
                print(f"  {done}/{len(universe)}... {len(scored)} OK")
    
    scored.sort(key=lambda x: x["score"], reverse=True)
    elapsed = time.time() - start
    
    output = {
        "generated_at": datetime.now().isoformat(),
        "universe_size": len(universe),
        "scored_count": len(scored),
        "top_picks": scored[:30],
        "all_scores": scored,
    }
    with open(SCORES_PATH, "w") as f:
        json.dump(output, f, indent=2)
    
    top_etf = next((s for s in scored if s.get("type") == "etf"), None)
    top_crypto = [s for s in scored if s.get("type") == "crypto"][:5]
    top_metal = [s for s in scored if s.get("ticker") in {"GLD","SLV","IAU","PPLT","PALL","CPER","GC=F","SI=F","PL=F","GLDM"} or s.get("category") in {"precious_metal","gold","commodity"}][:10]
    
    print(f"\n{'='*60}")
    print(f"Scored {len(scored):,} in {elapsed/60:.1f} min")
    print(f"\n=== TOP 10 ===")
    for s in scored[:10]:
        print(f"  {s['score']:>5.1f} | {s['ticker']:<8} | {s['name'][:32]:<32} | T={s['tech_score']} F={s['fund_score']} S={s['sentiment_score']} | {s['type']}")
    
    if top_etf:
        print(f"\n=== TOP ETF === {top_etf['score']} | {top_etf['ticker']} | {top_etf['name'][:32]}")
    print(f"\n=== TOP 5 CRYPTO ===")
    for s in top_crypto: print(f"  {s['score']:>5.1f} | {s['ticker']:<8} | {s['name'][:32]}")
    print(f"\n=== TOP 5 METALS ===")
    for s in top_metal: print(f"  {s['score']:>5.1f} | {s['ticker']:<8} | {s['name'][:32]}")
    
    # Chart
    try:
        chart_script = Path(__file__).resolve().parent / "generate_weekly_chart.py"
        subprocess.run([sys.executable, str(chart_script)], check=False, timeout=120)
    except Exception as e: print(f"Chart warn: {e}")
    
    # Update data.json weekly_pick AND metals
    dj = Path.home() / "ai-news-dashboard" / "data.json"
    try:
        with open(dj, "r") as f: data = json.load(f)
    except: data = {}
    top = scored[0] if scored else None
    if top:
        data["weekly_pick"] = build_pick(top, output["generated_at"])
    if top_etf:
        data["best_etf"] = build_pick(top_etf, output["generated_at"], "Best ETF")
    # Inject metals as scored array that the website can render
    data["scored_metals"] = top_metal
    # Also inject top 5 scored for leaderboard
    data["top_picks_leaderboard"] = scored[:5]
    with open(dj, "w") as f: json.dump(data, f, indent=2)
    print("Injected into data.json")


def build_pick(pick, gen_at, label="This Week"):
    f = pick["factors"]
    return {
        "week_label": label, "generated_at": gen_at,
        "top_pick": {
            "ticker": pick["ticker"], "name": pick["name"], "price": f["price"],
            "score": pick["score"], "category": pick.get("category", ""),
            "change_7d": f["chg_5d"], "change_30d": f["chg_20d"], "rsi": f["rsi"],
            "factors": [f"T:{pick['tech_score']}", f"F:{pick['fund_score']}", f"S:{pick['sentiment_score']}"],
        },
        "rationale": f"Score: {pick['score']}/100 (Tech {pick['tech_score']}/40, Fund {pick['fund_score']}/30, Sent {pick['sentiment_score']}/30)\n\n${f['price']:.2f} | 5d: {f['chg_5d']:.1f}% | 20d: {f['chg_20d']:.1f}% | RSI: {f['rsi']}\n\n{f.get('fund_details','N/A')}\n\nDisclaimer: Not financial advice.",
        "top_five": [],
    }


if __name__ == "__main__":
    main()
