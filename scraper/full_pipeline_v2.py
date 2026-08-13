#!/usr/bin/env python3
"""
Full pipeline — multiprocessing with spawn (macOS safe).
Each worker scores ONE ticker with 10s deadline.
"""
import json, statistics, multiprocessing, time
from datetime import datetime
from pathlib import Path

multiprocessing.set_start_method('spawn', force=True)

def score_one(args):
    import signal, yfinance as yf
    ticker, info = args
    signal.alarm(12)
    try:
        h = yf.Ticker(ticker).history(period='90d', interval='1d')
        signal.alarm(0)
        if len(h) < 20:
            return None
        c = h['Close'].tolist()
        cls = float(c[-1])
        wk = (cls / float(c[-6]) - 1) if len(c) >= 6 else 0
        mo = (cls / float(c[-22]) - 1) if len(c) >= 22 else 0
        yr = (cls / float(c[-252]) - 1) if len(c) >= 252 else 0
        ma20 = sum(c[-20:]) / 20
        ma50 = sum(c[max(0, len(c) - 50):]) / min(50, len(c))
        rises = sum([1 for i in range(max(0, len(c) - 20), len(c) - 1) if c[i + 1] > c[i]])
        rsi = max(0, min(100, 50 + (cls - ma20) / ma20 * 50))
        sma_x = 100 if cls > ma50 else 0
        macd = statistics.pstdev(c[-12:]) - statistics.pstdev(c[-26:]) if len(c) >= 26 else 0
        macd_s = 100 if macd > 0 else 0
        vol_s = 50 + rises * 2.5
        rets = [(c[i] - c[i - 1]) / c[i - 1] for i in range(1, len(c))]
        std = statistics.pstdev(rets) * 100 if len(rets) > 1 else 1
        t_score = (rsi * 0.3 + sma_x + macd_s + vol_s) / 4
        m_score = (wk * 30 + mo * 50 + yr * 20)
        s_score = min(100, max(0, 75 - std * 1.5))
        v_score = max(0, min(100, 100 - std * 8))
        score = max(0, min(100, t_score * 0.4 + m_score * 0.3 + s_score * 0.2 + v_score * 0.1))
        return {
            "ticker": ticker, "name": info.get("name", ticker), "category": info.get("category", "Asset"),
            "price": cls, "score": round(score, 1), "rsi": round(rsi, 1),
            "change_7d": round(wk * 100, 1), "change_30d": round(mo * 100, 1), "change_yr": round(yr * 100, 1),
            "signal": "BULLISH" if score >= 60 else "NEUTRAL" if score >= 45 else "BEARISH",
            "factors": [f"RSI {round(rsi)} {'bullish' if rsi > 50 else 'bearish'}",
                        f"{'Above' if cls > ma50 else 'Below'} SMA20",
                        f"MACD {'bullish' if macd > 0 else 'bearish'}",
                        f"{round(wk * 100, 1)}% week", f"{round(mo * 100, 1)}% month"]
        }
    except:
        return None
    finally:
        signal.alarm(0)

if __name__ == "__main__":
    base = Path("/Users/chris/ai-news-dashboard")
    universe = json.load(open(base / ".cache/universe_full.json"))
    items = list(universe.items())
    print(f"Universe: {len(items)} assets")
    print(f"  S&P 500:     {sum(1 for _,v in items if v['category']=='Equity - S&P 500')}")
    print(f"  Other listed:{sum(1 for _,v in items if v['category']=='Equity - Listed')}")
    print(f"  Crypto:      {sum(1 for _,v in items if v['category']=='Crypto')}")
    print(f"  Metals:      {sum(1 for _,v in items if v['category']=='Precious Metal')}")
    print(f"  ETFs:        {sum(1 for _,v in items if v['category']=='ETF')}")
    print()

    n_workers = min(8, multiprocessing.cpu_count())
    print(f"Spawning {n_workers} workers (spawn mode)...")
    
    start = time.time()
    pool = multiprocessing.Pool(processes=n_workers)
    results = pool.map(score_one, items, chunksize=1)
    pool.close()
    pool.join()
    elapsed = time.time() - start

    valid = [r for r in results if r]
    print(f"\n{'='*60}")
    print(f"SCORED: {len(valid)} / {len(items)} ({round(len(valid)/len(items)*100,1)}%)")
    print(f"Time: {round(elapsed/60,1)} minutes")
    print(f"{'='*60}\n")

    if not valid:
        print("No valid data — will save partial results.")
    else:
        valid.sort(key=lambda x: x["score"], reverse=True)
        top = valid[0]
        print(f"🏆 TOP PICK: {top['name']} ({top['ticker']})")
        print(f"   Score: {top['score']}/100 | Signal: {top['signal']} | ${top['price']:.2f}")
        print(f"   Week: {top['change_7d']:+.1f}% | Month: {top['change_30d']:+.1f}%")
        print()

    # Save results regardless
    pick = {
        "generated_at": datetime.now().isoformat(),
        "week_label": "Week of Aug 11, 2026",
        "top_pick": valid[0] if valid else {"ticker":"N/A","name":"No data","score":0,"price":0},
        "top_five": valid[:5] if valid else [],
        "best_etf_of_week": next((a for a in valid if a.get("category") == "ETF"), valid[0] if valid else None)
    }
    json.dump(pick, open(base / "weekly_pick.json", "w"), indent=2)
    
    # Update data.json
    try:
        with open(base / "data.json") as f:
            d = json.load(f)
    except:
        d = {}
    d["weekly_pick"] = pick
    d["timestamp"] = datetime.now().isoformat()
    json.dump(d, open(base / "data.json", "w"), indent=2)
    
    if valid:
        for i, a in enumerate(valid[:20], 1):
            print(f"  {i:2d}. {a['ticker']:10} — {a['score']:5.1f} | ${a['price']:>10.2f} | {a['change_7d']:+6.1f}% wk | {a['category']}")
    print(f"\nAssets analyzed: {len(valid)} of {len(items)}")
    print(f"Coverage: {round(len(valid)/len(items)*100,1)}%")
