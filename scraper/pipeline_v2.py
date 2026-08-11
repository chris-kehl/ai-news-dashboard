#!/usr/bin/env python3
"""Robust weekly pick — one-ticker-at-a-time with timeouts."""
import json, statistics, yfinance as yf
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, TimeoutError

CACHE = Path("/Users/chris/ai-news-dashboard/.cache")
DATA = Path("/Users/chris/ai-news-dashboard") / "data.json"

# Sentiment keyword lists
BULL = {"buy","bullish","strong","growth","moon","rocket","surge","rally","breakout","accumulate","upgrade","beat","raised","upside","booming","calls","long","added","buying","undervalued","discount","cheap","loading","upgrade","buy rating","beat earnings","guidance raised","rallies","gains","soars","climbs","higher"}
BEAR = {"sell","bearish","weak","dump","crash","correction","downgrade","miss","cut","lowered","put","short","overvalued","expensive","bubble","pullback","decline","falling","warning","slowing","missed earnings","guidance cut","drops","declines","falls","plunges","bear market"}

def fetch(ticker, days=50):
    """Fetch price history with timeout protection."""
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(lambda: yf.Ticker(ticker).history(period=f"{days}d", interval="1d"))
            hist = future.result(timeout=12)  # 12s max per ticker
        if hist.empty or len(hist) < 15:
            return None
        closes = hist["Close"].dropna().tolist()
        vols = hist["Volume"].dropna().tolist() if "Volume" in hist else []
        return [float(c) for c in closes], [float(v) for v in vols]
    except Exception:
        return None

def rsi(closes, p=14):
    if len(closes) < p+1: return None
    g,l = [],[]
    for i in range(1,p+1):
        d = closes[i]-closes[i-1]
        g.append(max(d,0)); l.append(max(-d,0))
    ag = sum(g)/p; al = sum(l)/p
    if al == 0: return 100.0
    return 100 - (100/(1+ag/al))

def sma(closes, p):
    if len(closes) < p: return None
    return sum(closes[-p:])/p

def macd(closes):
    if len(closes) < 26: return None, None
    def ema(prices, n):
        m = 2/(n+1)
        e = [prices[0]]
        for pr in prices[1:]:
            e.append((pr-e[-1])*m + e[-1])
        return e
    e12, e26 = ema(closes,12), ema(closes,26)
    md = [e12[i]-e26[i] for i in range(len(e26))]
    s = ema(md, 9)
    return md[-1], md[-1]-s[-1]

def vol_score(closes):
    if len(closes) < 10: return 50,"insufficient"
    rets = [(closes[i]-closes[i-1])/abs(closes[i-1]) for i in range(1,min(21,len(closes))) if closes[i-1]!=0]
    if not rets: return 50,"no returns"
    vol = statistics.stdev(rets)*(252**0.5)*100
    peak = max(closes)
    dd = (peak-closes[-1])/peak*100 if peak>0 else 0
    sc = 50
    msg = f"vol {vol:.0f}%"
    if vol<15: sc+=15; msg= f"low vol {vol:.0f}%"
    elif vol<25: sc+=5; msg= f"mod vol {vol:.0f}%"
    elif vol<35: sc-=5; msg= f"elev vol {vol:.0f}%"
    else: sc-=15; msg= f"high vol {vol:.0f}%"
    if dd<3: sc+=10; msg+=", near highs"
    elif dd>15: sc-=10; msg+=f", dd {dd:.0f}%"
    return max(0,min(100,sc)), msg

def sentiment(ticker):
    """Quick yfinance news sentiment."""
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            f = pool.submit(lambda: yf.Ticker(ticker).news)
            news = f.result(timeout=8)
        if not news: return 50, "no news"
        bull=bear=0
        for item in news[:5]:
            text = (item.get("title","")+" "+item.get("summary","")).lower()
            b = sum(1 for w in BULL if w in text)
            be= sum(1 for w in BEAR if w in text)
            if b>be: bull+=1
            elif be>b: bear+=1
        sc = 50 + (bull-bear)*12 if (bull+bear)>0 else 50
        return max(0,min(100,sc)), f"sent {sc:.0f} ({bull} bull, {bear} bear)"
    except Exception:
        return 50, "sent unavailable"

def score_one(ticker, info, closes, vols):
    p = closes[-1]
    week = (closes[-1]-closes[-5])/abs(closes[-5])*100 if len(closes)>=5 and closes[-5]!=0 else 0
    month = (closes[-1]-closes[-min(20,len(closes))])/abs(closes[-min(20,len(closes))])*100 if len(closes)>=20 else 0
    
    # Technical
    ts,tf = 40,[]
    r = rsi(closes)
    if r:
        if 50<=r<=65: ts+=12; tf.append(f"RSI {r:.0f} bullish")
        elif r>65 and r<=75: ts+=8; tf.append(f"RSI {r:.0f} strong")
        elif r>75: ts+=3; tf.append(f"RSI {r:.0f} overbought")
        elif r<35: ts-=5; tf.append(f"RSI {r:.0f} oversold")
    s20 = sma(closes,20)
    s50 = sma(closes,50) if len(closes)>=50 else None
    if s20:
        if p>s20*1.03: ts+=10; tf.append("above SMA20")
        elif p<s20*0.97: ts-=5; tf.append("below SMA20")
    if s50 and s20:
        if s20>s50*1.01: ts+=8; tf.append("golden cross")
        elif s20<s50*0.99: ts-=5; tf.append("death cross")
    m,mh = macd(closes)
    if m and mh:
        if mh>0 and m>0: ts+=8; tf.append("MACD bullish")
        elif mh<0: ts-=3; tf.append("MACD weakening")
    vs,vm = vol_score(closes)
    
    # Momentum  
    ms,mf = 40,[]
    if week>=5: ms+=20; mf.append(f"+{week:.1f}% week strong")
    elif week>=2: ms+=10; mf.append(f"+{week:.1f}% week")
    elif week>=0.5: ms+=5; mf.append(f"+{week:.1f}% week")
    elif week<=-5: ms-=15; mf.append(f"{week:.1f}% week breakdown")
    elif week<=-2: ms-=8; mf.append(f"{week:.1f}% week")
    if month>=10: ms+=15; mf.append(f"+{month:.1f}% month powerful")
    elif month>=5: ms+=8; mf.append(f"+{month:.1f}% month")
    elif month<=-10: ms-=10; mf.append(f"{month:.1f}% month correction")
    elif month<=-5: ms-=5; mf.append(f"{month:.1f}% month")
    if len(closes)>=20:
        ma5=sum(closes[-5:])/5; ma20=sum(closes[-20:])/20
        if ma5>ma20*1.02: ms+=10; mf.append("5d>20d accelerating")
        elif ma5<ma20*0.98: ms-=5; mf.append("5d<20d decel")
    
    # Sentiment
    ss,sf = sentiment(ticker)
    
    combined = ts*0.40 + ms*0.30 + vs*0.10 + ss*0.20
    if info.get("category") in {"ETF","Crypto ETF"}: combined += 1
    
    return {
        "ticker": ticker, "name": info.get("name",ticker),
        "category": info.get("category","Stock"),
        "price": round(p,2), "change_7d": round(week,2),
        "change_30d": round(month,2), "rsi": round(r,1) if r else None,
        "sma20": round(s20,2) if s20 else None,
        "score": round(combined,1), "technical": round(ts,1),
        "momentum": round(ms,1), "sentiment": round(ss,1),
        "volatility": round(vs,1), "factors": tf+mf+[vm]+[sf]
    }

def main():
    print(f"[pipeline] Start {datetime.now().strftime('%H:%M')}")
    with open(CACHE/"universe.json") as f:
        universe = json.load(f)
    print(f"[pipeline] {len(universe)} assets")
    
    # Fetch prices one at a time to avoid rate limits
    prices = {}
    tickers = list(universe.keys())
    for i,ticker in enumerate(tickers,1):
        data = fetch(ticker, 50)
        if data:
            prices[ticker] = data
        if i % 20 == 0:
            print(f"      {i}/{len(tickers)} done, {len(prices)} valid")
    print(f"[pipeline] Fetched {len(prices)}/{len(tickers)} valid")
    
    if not prices:
        print("[pipeline] ERROR: no prices")
        return
    
    # Score all
    results = []
    for ticker,(closes,vols) in prices.items():
        info = universe.get(ticker,{})
        results.append(score_one(ticker, info, closes, vols))
    
    results.sort(key=lambda x: x["score"], reverse=True)
    
    top = results[0]
    top5 = results[:5]
    
    # ── Best ETF of the Week ──
    etf_only = [r for r in results if r["category"] in {"ETF","Crypto ETF","Precious Metal","Leveraged ETF","Volatility ETF"}]
    if etf_only:
        etf_only.sort(key=lambda x: x["score"], reverse=True)
        best_etf = etf_only[0]
    else:
        best_etf = None
    
    etf_rationale = None
    if best_etf:
        etf_rationale = (
            f"**BEST ETF: {best_etf['name']} ({best_etf['ticker']})** — ${best_etf['price']}\n\n"
            f"Combined score: **{best_etf['score']}/100** across {len(etf_only)} ETF-type assets.\n\n"
            f"**Signal Breakdown:**\n"
            f"• Technical: {best_etf['technical']}/100\n"
            f"• Momentum: {best_etf['momentum']}/100 ({best_etf['change_7d']:+.1f}% week, {best_etf['change_30d']:+.1f}% month)\n"
            f"• Sentiment: {best_etf['sentiment']}/100\n"
            f"• Volatility: {best_etf['volatility']}/100\n\n"
            f"**Key Drivers:**\n" + "\n".join(f"• {f}" for f in best_etf['factors'][:6]) + "\n\n"
            f"**Trade Plan:** Entry at current or SMA20 (${best_etf['sma20'] or 'N/A'}).\n"
            f"Stop: Close below SMA20 or -5%. Target: continuation.\n\n"
            f"*Not financial advice. DYOR.*"
        )

    rationale = (
        f"**HIGHEST CONVICTION: {top['name']} ({top['ticker']})** — ${top['price']}\n\n"
        f"Combined score: **{top['score']}/100** (analyzed {len(results)} premium assets).\n\n"
        f"**Signal Breakdown:**\n"
        f"• Technical: {top['technical']}/100 (RSI, trend, volume)\n"
        f"• Momentum: {top['momentum']}/100 ({top['change_7d']:+.1f}% week, {top['change_30d']:+.1f}% month)\n"
        f"• Sentiment: {top['sentiment']}/100 (news scan)\n"
        f"• Volatility: {top['volatility']}/100 (risk-adjusted)\n\n"
        f"**Key Drivers:**\n" + "\n".join(f"• {f}" for f in top['factors'][:6]) + "\n\n"
        f"**Trade Plan:** Entry at current or SMA20 (${top['sma20'] or 'N/A'}).\n"
        f"Stop: Close below SMA20 or -5%. Target: continuation.\n\n"
        f"*Not financial advice. DYOR.*"
    )
    
    weekly = {
        "generated_at": datetime.now().isoformat(),
        "week_label": datetime.now().strftime("Week of %b %d, %Y"),
        "top_pick": {
            "name": top["ticker"], "display_name": top["name"],
            "price": top["price"], "signal": "BULLISH" if top["score"]>65 else "NEUTRAL-BULLISH" if top["score"]>55 else "NEUTRAL",
            "score": top["score"], "rationale": rationale,
            "key_levels": f"Support: ${top['sma20']}" if top['sma20'] else "Watch SMA20",
            "timeframe": "Swing (1-4 weeks)", "factors": top["factors"],
            "sub_scores": {
                "technical": top["technical"], "momentum": top["momentum"],
                "sentiment": top["sentiment"], "volatility": top["volatility"]
            },
            "sentiment_score": top["sentiment"],
        },
        "best_etf_of_week": {
            "name": best_etf["ticker"], "display_name": best_etf["name"],
            "price": best_etf["price"], "category": best_etf["category"],
            "signal": "BULLISH" if best_etf["score"]>65 else "NEUTRAL-BULLISH" if best_etf["score"]>55 else "NEUTRAL",
            "score": best_etf["score"], "rationale": etf_rationale,
            "change_7d": best_etf["change_7d"], "change_30d": best_etf["change_30d"],
            "rsi": best_etf["rsi"], "sma20": best_etf["sma20"],
            "factors": best_etf["factors"],
            "sub_scores": {
                "technical": best_etf["technical"], "momentum": best_etf["momentum"],
                "sentiment": best_etf["sentiment"], "volatility": best_etf["volatility"],
            },
        } if best_etf else None,
        "top_five": [
            {"ticker":r["ticker"], "name":r["name"], "category":r["category"],
             "score":r["score"], "price":r["price"], "change_7d":r["change_7d"],
             "change_30d":r["change_30d"]}
            for r in top5
        ],
        "rationale": rationale,
        "meta": {"total_analyzed": len(results), "universe_size": len(universe),
                 "weights": {"technical":0.40,"momentum":0.30,"sentiment":0.20,"volatility":0.10}}
    }
    
    # Write data.json
    try:
        with open(DATA) as f:
            existing = json.load(f)
    except:
        existing = {}
    existing["weekly_pick"] = weekly
    existing["generated_at"] = datetime.now().isoformat()
    with open(DATA, "w") as f:
        json.dump(existing, f, indent=2, default=str)
    with open(CACHE/"weekly_pick_cache.json", "w") as f:
        json.dump(weekly, f, indent=2, default=str)
    
    print(f"\n{'='*60}")
    print(f"🏆 TOP PICK: {top['ticker']} ({top['name']})")
    print(f"📊 Score: {top['score']}/100 | Technical: {top['technical']} | Momentum: {top['momentum']}")
    print(f"💰 ${top['price']} | Week: {top['change_7d']:+.1f}% | Month: {top['change_30d']:+.1f}%")
    print(f"🥈 Top 5: {[r['ticker'] for r in top5]}")
    print(f"{'='*60}")

if __name__ == "__main__":
    main()
