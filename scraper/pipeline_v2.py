#!/usr/bin/env python3
"""Robust weekly pick — one-ticker-at-a-time with timeouts + fundamentals + news + analyst ratings."""
import json, statistics, yfinance as yf
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
import signal

CACHE = Path("/Users/chris/ai-news-dashboard/.cache")
DATA = Path("/Users/chris/ai-news-dashboard") / "data.json"

# ─── Keyword dictionaries ──────────────────────────────────────────────────
BULL = {"buy","bullish","strong","growth","moon","rocket","surge","rally","breakout","accumulate","upgrade","beat","raised","upside","booming","calls","long","added","buying","undervalued","discount","cheap","loading","upgrade","buy rating","beat earnings","guidance raised","rallies","gains","soars","climbs","higher","outperform","overweight","top pick","strong buy","accumulation","whale","institutional buying","recovery","bounce","bottom","reversal up","crushed earnings","raised outlook","partnership","contract win","fda approval","breakthrough","beat expectations","record high","all time high"}
BEAR = {"sell","bearish","weak","dump","crash","correction","downgrade","miss","cut","lowered","put","short","overvalued","expensive","bubble","pullback","decline","falling","warning","slowing","missed earnings","guidance cut","drops","declines","falls","plunges","bear market","selloff","sell off","dumping","panic","underperform","underweight","price target cut","bear case","concern","risk","fear","caution","negative","pessimistic","disappointing","below expectations","revenue miss","bear flag","head and shoulders","distribution","resistance","rejected","failed breakout","lower high","death cross","bankruptcy","layoffs","investigation","sec probe","lawsuit","tumbles","sinks","dumps","recession","fraud","probe","litigation","fine","penalty"}

# ─── Fundamentals fetcher ──────────────────────────────────────────────────
def fetch_fundamentals(ticker: str) -> dict:
    """Fetch yfinance .info with 12-second hard timeout via SIGALRM."""
    def _handler(signum, frame):
        raise TimeoutError("yfinance info timeout")

    old = signal.signal(signal.SIGALRM, _handler)
    signal.alarm(12)
    try:
        info = yf.Ticker(ticker).info or {}
    except Exception:
        info = {}
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, old)

    # Extract key fields safely
    out = {
        "forward_pe": info.get("forwardPE"),
        "trailing_pe": info.get("trailingPE"),
        "price_to_book": info.get("priceToBook"),
        "roe": info.get("returnOnEquity"),          # Yahoo returns as ratio (0.25 = 25%)
        "debt_to_equity": info.get("debtToEquity"),  # Yahoo returns as ratio (0.5 = 50%)
        "revenue_growth": info.get("revenueGrowth"), # ratio
        "earnings_growth": info.get("earningsGrowth"), # ratio
        "rec_mean": info.get("recommendationMean"),  # 1.0 strong buy → 5.0 strong sell
        "rec_count": info.get("numberOfAnalystOpinions"),
        "target_mean": info.get("targetMeanPrice"),
        "target_high": info.get("targetHighPrice"),
        "current_price": info.get("currentPrice") or info.get("regularMarketPrice"),
    }
    return out


# ─── Fundamental scoring engine ────────────────────────────────────────────
def fundamental_score(ticker: str, cat: str, info: dict) -> tuple[float, list]:
    """
    Return (score 0-100, [factor strings]).
    For ETFs / Crypto / Metals we skip pure equity fundamentals and
    use a simplified flow / AUM / macro read instead.
    """
    score = 50.0
    factors = []

    # ETFs, Crypto ETFs, Precious Metals → simplified scoring
    if cat in {"ETF", "Crypto ETF", "Precious Metal", "Leveraged ETF", "Volatility ETF"}:
        score = 55.0  # slight neutral-positive base for diversified vehicles
        if "rec_mean" in info and info["rec_mean"] is not None:
            rm = info["rec_mean"]
            if rm <= 2.0:
                score += 10; factors.append(f"analyst consensus Buy ({rm:.1f})")
            elif rm >= 4.0:
                score -= 10; factors.append(f"analyst consensus Sell ({rm:.1f})")
        if info.get("target_mean") and info.get("current_price"):
            upside = (info["target_mean"] - info["current_price"]) / info["current_price"] * 100
            if upside > 15:
                score += 8; factors.append(f"+{upside:.0f}% analyst upside")
            elif upside > 5:
                score += 4; factors.append(f"+{upside:.0f}% analyst upside")
            elif upside < -10:
                score -= 5; factors.append(f"{upside:.0f}% analyst downside")
        return max(0, min(100, score)), factors

    # ── Equity fundamental scoring ──
    pe = info.get("forward_pe") or info.get("trailing_pe")
    if pe is not None and pe > 0:
        if pe < 15:
            score += 12; factors.append(f"attractive PE {pe:.1f}")
        elif pe < 25:
            score += 5; factors.append(f"fair PE {pe:.1f}")
        elif pe < 40:
            score -= 3; factors.append(f"rich PE {pe:.1f}")
        else:
            score -= 10; factors.append(f"expensive PE {pe:.1f}")

    pb = info.get("price_to_book")
    if pb is not None and pb > 0:
        if pb < 2:
            score += 8; factors.append(f"low PB {pb:.1f}")
        elif pb < 5:
            score += 2; factors.append(f"moderate PB {pb:.1f}")
        else:
            score -= 6; factors.append(f"high PB {pb:.1f}")

    roe = info.get("roe")
    if roe is not None:
        roe_pct = roe * 100 if abs(roe) < 1 else roe  # handle ratio vs percent
        if roe_pct > 20:
            score += 10; factors.append(f"strong ROE {roe_pct:.1f}%")
        elif roe_pct > 12:
            score += 5; factors.append(f"solid ROE {roe_pct:.1f}%")
        elif roe_pct < 5:
            score -= 5; factors.append(f"weak ROE {roe_pct:.1f}%")

    de = info.get("debt_to_equity")
    if de is not None:
        de_pct = de * 100 if abs(de) < 1 else de
        if de_pct < 30:
            score += 8; factors.append(f"low debt/equity {de_pct:.0f}%")
        elif de_pct < 80:
            score += 2; factors.append(f"moderate debt/equity {de_pct:.0f}%")
        elif de_pct > 120:
            score -= 10; factors.append(f"high debt/equity {de_pct:.0f}%")
        elif de_pct > 80:
            score -= 4; factors.append(f"elevated debt/equity {de_pct:.0f}%")

    rev_g = info.get("revenue_growth")
    if rev_g is not None:
        rev_pct = rev_g * 100 if abs(rev_g) < 1 else rev_g
        if rev_pct > 20:
            score += 10; factors.append(f"hyper-growth revenue +{rev_pct:.0f}%")
        elif rev_pct > 10:
            score += 6; factors.append(f"strong revenue +{rev_pct:.0f}%")
        elif rev_pct > 0:
            score += 2; factors.append(f"positive revenue +{rev_pct:.0f}%")
        else:
            score -= 5; factors.append(f"declining revenue {rev_pct:.0f}%")

    earn_g = info.get("earnings_growth")
    if earn_g is not None:
        eg_pct = earn_g * 100 if abs(earn_g) < 1 else earn_g
        if eg_pct > 25:
            score += 8; factors.append(f"strong earn growth +{eg_pct:.0f}%")
        elif eg_pct > 10:
            score += 4; factors.append(f"healthy earn growth +{eg_pct:.0f}%")
        elif eg_pct < 0:
            score -= 4; factors.append(f"shrinking earnings {eg_pct:.0f}%")

    # Analyst recommendations
    rm = info.get("rec_mean")
    rc = info.get("rec_count") or 0
    if rm is not None and rc >= 3:
        if rm <= 1.7:
            score += 12; factors.append(f"analyst Strong Buy ({rm:.1f}, n={rc})")
        elif rm <= 2.3:
            score += 8; factors.append(f"analyst Buy ({rm:.1f}, n={rc})")
        elif rm <= 3.0:
            score += 2; factors.append(f"analyst Hold ({rm:.1f}, n={rc})")
        elif rm <= 4.0:
            score -= 6; factors.append(f"analyst Weak ({rm:.1f}, n={rc})")
        else:
            score -= 12; factors.append(f"analyst Sell ({rm:.1f}, n={rc})")
    elif rm is not None:
        factors.append(f"sparse analyst coverage ({rm:.1f})")

    # Price vs target
    target = info.get("target_mean")
    curr = info.get("current_price")
    if target and curr and curr > 0:
        upside = (target - curr) / curr * 100
        if upside > 25:
            score += 10; factors.append(f"massive +{upside:.0f}% to analyst target")
        elif upside > 10:
            score += 6; factors.append(f"+{upside:.0f}% to analyst target")
        elif upside > 0:
            score += 2; factors.append(f"+{upside:.0f}% to analyst target")
        elif upside < -15:
            score -= 6; factors.append(f"{upside:.0f}% below analyst target")

    return max(0, min(100, score)), factors


# ─── News sentiment scorer ─────────────────────────────────────────────────
def news_sentiment(ticker: str) -> tuple[float, list]:
    """Deep yfinance news sentiment scan with expanded keyword lists."""
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            f = pool.submit(lambda: yf.Ticker(ticker).news)
            news = f.result(timeout=10)
        if not news:
            return 50, ["no headlines"]
        bull = bear = 0
        for item in news[:10]:
            text = (item.get("title", "") + " " + item.get("summary", "")).lower()
            b = sum(1 for w in BULL if w in text)
            be = sum(1 for w in BEAR if w in text)
            if b > be:
                bull += 1
            elif be > b:
                bear += 1
        base = 50 + (bull - bear) * 10 if (bull + bear) > 0 else 50
        score = max(0, min(100, base))
        return score, [f"news {score:.0f}/100 ({bull} bull, {bear} bear headlines)"]
    except Exception:
        return 50, ["news sentiment unavailable"]


# ─── Price fetcher ─────────────────────────────────────────────────────────
def fetch(ticker, days=50):
    """Fetch price history with timeout protection."""
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(lambda: yf.Ticker(ticker).history(period=f"{days}d", interval="1d"))
            hist = future.result(timeout=12)
        if hist.empty or len(hist) < 15:
            return None
        closes = hist["Close"].dropna().tolist()
        vols = hist["Volume"].dropna().tolist() if "Volume" in hist else []
        return [float(c) for c in closes], [float(v) for v in vols]
    except Exception:
        return None


# ─── Technical helpers ─────────────────────────────────────────────────────
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


# ─── Main scoring function ─────────────────────────────────────────────────
def score_one(ticker, info, closes, vols, fundamentals: dict):
    p = closes[-1]
    week = (closes[-1]-closes[-5])/abs(closes[-5])*100 if len(closes)>=5 and closes[-5]!=0 else 0
    month = (closes[-1]-closes[-min(20,len(closes))])/abs(closes[-min(20,len(closes))])*100 if len(closes)>=20 else 0
    cat = info.get("category","Stock")

    # ── Technical ──
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

    # ── Momentum ──
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

    # ── Fundamentals & Analyst Ratings ──
    fs, ff = fundamental_score(ticker, cat, fundamentals)

    # ── News Sentiment ──
    ns, nf = news_sentiment(ticker)

    # ── Combined weighted score ──
    # Technical 30% | Momentum 25% | Fundamentals 20% | News/Sentiment 15% | Volatility 10%
    combined = ts*0.30 + ms*0.25 + fs*0.20 + ns*0.15 + vs*0.10
    if cat in {"ETF","Crypto ETF"}: combined += 1

    return {
        "ticker": ticker, "name": info.get("name",ticker),
        "category": cat,
        "price": round(p,2), "change_7d": round(week,2),
        "change_30d": round(month,2), "rsi": round(r,1) if r else None,
        "sma20": round(s20,2) if s20 else None,
        "score": round(combined,1), "technical": round(ts,1),
        "momentum": round(ms,1), "fundamentals": round(fs,1),
        "news_sentiment": round(ns,1), "volatility": round(vs,1),
        "analyst_rec": fundamentals.get("rec_mean"),
        "analyst_count": fundamentals.get("rec_count"),
        "target_mean": fundamentals.get("target_mean"),
        "target_high": fundamentals.get("target_high"),
        "forward_pe": fundamentals.get("forward_pe"),
        "revenue_growth": fundamentals.get("revenue_growth"),
        "factors": tf+mf+ff+nf+[vm],
    }


# ─── Main ──────────────────────────────────────────────────────────────────
def main():
    print(f"[pipeline] Start {datetime.now().strftime('%H:%M')}")
    with open(CACHE/"universe.json") as f:
        universe = json.load(f)
    print(f"[pipeline] {len(universe)} assets")

    tickers = list(universe.keys())
    prices = {}
    fundamentals = {}

    # Fetch prices + fundamentals one ticker at a time (polite)
    for i, ticker in enumerate(tickers, 1):
        data = fetch(ticker, 50)
        if data:
            prices[ticker] = data
        # fundamentals are light but can be slow — fetch only for equities w/ timeout
        if universe.get(ticker, {}).get("category", "Stock") not in {"Crypto", "Precious Metal"}:
            try:
                fund = fetch_fundamentals(ticker)
                fundamentals[ticker] = fund
            except Exception:
                fundamentals[ticker] = {}
        else:
            fundamentals[ticker] = {}
        if i % 20 == 0:
            print(f"      {i}/{len(tickers)} done, prices={len(prices)}, funds={len(fundamentals)}")
    print(f"[pipeline] Fetched {len(prices)} prices, {len(fundamentals)} fundamentals")

    if not prices:
        print("[pipeline] ERROR: no prices")
        return

    # Score all
    results = []
    for ticker, (closes, vols) in prices.items():
        info = universe.get(ticker, {})
        fund = fundamentals.get(ticker, {})
        results.append(score_one(ticker, info, closes, vols, fund))

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

    def build_rationale(pick, universe_size, tag):
        rec = pick.get("analyst_rec")
        rc = pick.get("analyst_count")
        target = pick.get("target_mean")
        pe = pick.get("forward_pe")
        rev = pick.get("revenue_growth")

        analyst_line = ""
        if rec is not None and rc and rc >= 3:
            label = "Strong Buy" if rec <= 1.7 else "Buy" if rec <= 2.3 else "Hold" if rec <= 3.0 else "Weak"
            analyst_line = f"• Analyst Consensus: **{label}** (avg {rec:.1f}, n={rc})\n"
            if target and pick["price"] > 0:
                upside = (target - pick["price"]) / pick["price"] * 100
                analyst_line += f"• Mean Price Target: **${target:.2f}** ({upside:+.0f}% upside)\n"
        elif rec is not None:
            analyst_line = f"• Analyst Consensus: {rec:.1f} (sparse coverage, n={rc or 0})\n"

        fund_line = ""
        if pe:
            fund_line += f"• Forward P/E: **{pe:.1f}**\n"
        if rev is not None:
            rg = rev * 100 if abs(rev) < 1 else rev
            fund_line += f"• Revenue Growth: **{rg:+.0f}%**\n"

        return (
            f"**{tag}: {pick['name']} ({pick['ticker']})** — ${pick['price']}\n\n"
            f"Combined score: **{pick['score']}/100** (analyzed {universe_size} premium assets).\n\n"
            f"**Signal Breakdown:**\n"
            f"• Technical: {pick['technical']}/100 (RSI, trend, volume)\n"
            f"• Momentum: {pick['momentum']}/100 ({pick['change_7d']:+.1f}% week, {pick['change_30d']:+.1f}% month)\n"
            f"• Fundamentals: {pick['fundamentals']}/100 (valuation, growth, balance sheet)\n"
            f"• News Sentiment: {pick['news_sentiment']}/100 (headline scan)\n"
            f"• Volatility: {pick['volatility']}/100 (risk-adjusted)\n\n"
            f"**Fundamental & Analyst Read:**\n"
            f"{analyst_line}"
            f"{fund_line}"
            f"\n"
            f"**Key Drivers:**\n" + "\n".join(f"• {f}" for f in pick['factors'][:8]) + "\n\n"
            f"**Trade Plan:** Entry at current or SMA20 (${pick['sma20'] or 'N/A'}).\n"
            f"Stop: Close below SMA20 or -5%. Target: continuation.\n\n"
            f"*Not financial advice. DYOR.*"
        )

    rationale = build_rationale(top, len(results), "HIGHEST CONVICTION")
    etf_rationale = build_rationale(best_etf, len(etf_only), "BEST ETF") if best_etf else None

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
                "fundamentals": top["fundamentals"], "news_sentiment": top["news_sentiment"],
                "volatility": top["volatility"]
            },
            "fundamentals": {
                "forward_pe": top.get("forward_pe"),
                "revenue_growth": top.get("revenue_growth"),
                "analyst_rec": top.get("analyst_rec"),
                "analyst_count": top.get("analyst_count"),
                "target_mean": top.get("target_mean"),
                "target_high": top.get("target_high"),
            },
            "news_sentiment_score": top["news_sentiment"],
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
                "fundamentals": best_etf["fundamentals"], "news_sentiment": best_etf["news_sentiment"],
                "volatility": best_etf["volatility"],
            },
            "fundamentals": {
                "forward_pe": best_etf.get("forward_pe"),
                "revenue_growth": best_etf.get("revenue_growth"),
                "analyst_rec": best_etf.get("analyst_rec"),
                "analyst_count": best_etf.get("analyst_count"),
                "target_mean": best_etf.get("target_mean"),
                "target_high": best_etf.get("target_high"),
            },
        } if best_etf else None,
        "top_five": [
            {"ticker":r["ticker"], "name":r["name"], "category":r["category"],
             "score":r["score"], "price":r["price"], "change_7d":r["change_7d"],
             "change_30d":r["change_30d"], "technical":r["technical"],
             "fundamentals":r["fundamentals"], "news_sentiment":r["news_sentiment"]}
            for r in top5
        ],
        "rationale": rationale,
        "meta": {
            "total_analyzed": len(results),
            "universe_size": len(universe),
            "weights": {
                "technical":0.30, "momentum":0.25, "fundamentals":0.20,
                "news_sentiment":0.15, "volatility":0.10
            }
        }
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
    print(f"📊 Score: {top['score']}/100 | Tech: {top['technical']} | Mom: {top['momentum']} | Fund: {top['fundamentals']} | News: {top['news_sentiment']}")
    print(f"💰 ${top['price']} | Week: {top['change_7d']:+.1f}% | Month: {top['change_30d']:+.1f}%")
    print(f"🥈 Top 5: {[r['ticker'] for r in top5]}")
    print(f"{'='*60}")

if __name__ == "__main__":
    main()
