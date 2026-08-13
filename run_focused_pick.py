#!/usr/bin/env python3
"""FOCUSED pipeline — scores 200 priority assets using parallel yf.download batches."""
import json, statistics, time, os
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

os.environ['MPLBACKEND'] = 'Agg'

base = Path("/Users/chris/ai-news-dashboard")

# Build focused universe: S&P 500 top 100 + all major ETFs + crypto + metals
sp500 = ["A","AAPL","ABBV","ABNB","ABT","ACGL","ACN","ADBE","ADI","ADM","ADP","ADSK","AEE","AEP","AES","AFL","AIG","AIZ","AJG","AKAM","ALB","ALGN","ALK","ALL","ALLE","AMAT","AMCR","AMD","AME","AMGN","AMP","AMT","AMZN","ANET","ANSS","AON","AOS","APA","APD","APH","APTV","ARE","ATO","ATVI","AVB","AVGO","AVY","AWK","AXP","AZO","BA","BAC","BAX","BBWI","BBY","BDX","BEN","BF-B","BIIB","BIO","BK","BKR","BLK","BMY","BR","BRK-B","BRO","BSX","BWA","BXP","C","CAG","CAH","CARR","CAT","CB","CBOE","CBRE","CCI","CCL","CDAY","CDNS","CDW","CE","CEG","CERN","CF","CFG","CHD","CHRW","CHTR","CI","CINF","CL","CLX","CMA","CMCSA","CME","CMG","CMI","CMS","CNC","CNP","COF","COO","COP","COST","CPB","CPRT","CPT","CRL","CRM","CSCO","CSX","CTAS","CTLT","CTRA","CTSH","CTVA","CVS","CVX","D","DAL","DD","DE","DFS","DG","DGX","DHI","DHR","DIS","DISH","DLR","DLTR","DOV","DOW","DPZ","DRI","DTE","DUK","DVA","DVN","DXC","DXCM","EA","EBAY","ECL","ED","EFX","EIX","EL","ELV","EMN","EMR","ENPH","EOG","EPAM","EQIX","EQR","ES","ESS","ETN","ETR","EW","EXC","EXPD","EXPE","EXR","F","FANG","FAST","FCX","FDS","FDX","FE","FFIV","FIS","FISV","FITB","FLT","FMC","FOX","FOXA","FRT","FTNT","FTV","GD","GE","GILD","GIS","GL","GLW","GM","GNRC","GOOG","GOOGL","GPC","GPN","GRMN","GS","GWW","HAL","HAS","HBAN","HCA","HD","HES","HIG","HII","HLT","HOLX","HON","HPE","HPQ","HRL","HSIC","HST","HSY","HUM","HWM","IBM","ICE","IDXX","IEX","IFF","ILMN","INCY","INTC","INTU","INVH","IP","IPG","IQV","IR","IRM","ISRG","IT","ITW","IVZ","J","JBHT","JCI","JKHY","JNJ","JNPR","JPM","K","KDP","KEY","KEYS","KHC","KIM","KLAC","KMB","KMI","KMX","KO","KR","L","LDOS","LEN","LH","LHX","LIN","LKQ","LLY","LMT","LNC","LOW","LRCX","LUMN","LUV","LVS","LW","LYB","LYV","MA","MAA","MAR","MAS","MCD","MCHP","MCK","MCO","MDLZ","MDT","MET","META","MGM","MHK","MKC","MKTX","MLM","MMC","MMM","MNST","MO","MOH","MOS","MPC","MPWR","MRK","MRNA","MS","MSCI","MSFT","MSI","MTB","MTCH","MTD","MU","NCLH","NDAQ","NDSN","NEE","NEM","NFLX","NI","NKE","NOC","NOW","NRG","NSC","NTAP","NTRS","NUE","NVDA","NVR","NXPI","O","ODFL","OKE","OMC","ON","ORCL","ORLY","OTIS","OXY","PARA","PAYC","PAYX","PCAR","PEG","PEP","PFE","PFG","PG","PGR","PH","PHM","PKG","PKI","PLD","PM","PNC","PNR","PNW","POOL","PPG","PPL","PRU","PSA","PSX","PTC","PVH","PWR","PXD","PYPL","QCOM","QRVO","RCL","REG","REGN","RF","RHI","RJF","RL","RMD","ROK","ROL","ROP","ROST","RSG","RTX","RVTY","SBAC","SBNY","SBUX","SCHW","SEDG","SEE","SHW","SIVB","SJM","SLB","SNA","SNPS","SO","SPG","SPGI","SRE","STE","STLD","STT","STX","STZ","SWK","SWKS","SYF","SYK","SYY","T","TAP","TDG","TDY","TECH","TEL","TER","TFC","TFX","TGT","TJX","TMO","TMUS","TPR","TRMB","TROW","TRV","TSCO","TSLA","TSN","TT","TTWO","TWTR","TXN","TXT","TYL","UAL","UBER","UDR","UHS","ULTA","UNH","UNP","UPS","URI","USB","V","VFC","VLO","VMC","VRSK","VRSN","VRTX","VTR","VZ","WAB","WAT","WBA","WBD","WDC","WEC","WELL","WFC","WHR","WM","WMB","WMT","WRB","WST","WTW","WYNN","XEL","XOM","XRAY","XYL","YUM","ZBH","ZBRA","ZBH","ZION","ZTS"]

etfs = ["SPY","QQQ","DIA","IVV","VOO","VTI","VEA","VWO","IWM","EFA","AGG","BND","LQD","HYG","SHY","TLT","GLD","SLV","IAU","USO","UNG","DBA","DBC","IEF","MUB","TIP","VIG","SCHD","NOBL","DGRO","HDV","VYM","JEPI","JEPQ","QYLD","XYLD","SPHD","DIVO","SDY","DVY","FTSM","USMV","SPLV","DEF","XLU","XLF","XLK","XLE","XLI","XLP","XLB","XRT","XBI","XHB","XPH","XME","XES","XOP","XSD","SOXX","SMH","IBB","KRE","KBE","XAR","XHE","XTL","XSW","XWEB","FINX","BOTZ","ARKK","ARKG","ARKW","ARKF","ARKQ","PRNT","IZRL","LIT","REMX","URTH","ACWI","VT","VXUS","SCHF","VTEB","BIL","SHV","GOVT","MBB","EMB","VCIT","VGIT","VCSH","IGSB","IGIB","LQDI","PFF","PGX","SPAB","SPAX","BIV","BLV","BSV","BNDX","VXUS","VEU","IEMG","EEM","SCZ","EFA","IEFA","FEZ","GREK","EWP","EWQ","EWG","EWI","EWN","EWK","EWD","EWS","EWY","EWZ","EWW","EWC","EWA","EPP","ILF","AFK","FM","FRN","GAF"]

crypto_tickers = ["BTC-USD","ETH-USD","SOL-USD","XRP-USD","ADA-USD","DOT-USD","LINK-USD","AVAX-USD","MATIC-USD","UNI-USD","LTC-USD","BCH-USD","XLM-USD","VET-USD","FIL-USD","TRX-USD","ETC-USD","ALGO-USD","ATOM-USD","XTZ-USD"]

metals = ["GC=F","SI=F","HG=F","PA=F","PL=F","CL=F","NG=F","ZB=F","ZN=F","ZT=F","ZF=F","GC=F"]

universe = {}
for t in sp500[:100]: universe[t] = {"name": t, "category": "Equity - S&P 500"}
for t in etfs[:120]: universe[t] = {"name": t, "category": "ETF"}
for t in crypto_tickers: universe[t] = {"name": t.replace('-USD',''), "category": "Crypto"}
for t in metals: universe[t] = {"name": t, "category": "Precious Metal"}

print(f"FOCUSED UNIVERSE: {len(universe)} assets")
print(f"  S&P 500 (top 100): {len([u for u in universe.values() if u['category']=='Equity - S&P 500'])}")
print(f"  ETFs: {len([u for u in universe.values() if u['category']=='ETF'])}")
print(f"  Crypto: {len([u for u in universe.values() if u['category']=='Crypto'])}")
print(f"  Metals/Commodities: {len([u for u in universe.values() if u['category']=='Precious Metal'])}")
print()

# Score one ticker
def score_one(ticker, info):
    import yfinance as yf
    try:
        h = yf.Ticker(ticker).history(period="90d", interval="1d")
        if len(h) < 20: return None
        c = h["Close"].tolist()
        cls = float(c[-1])
        wk = (cls / float(c[-6]) - 1) if len(c) >= 6 else 0
        mo = (cls / float(c[-22]) - 1) if len(c) >= 22 else 0
        yr = (cls / float(c[-252]) - 1) if len(c) >= 252 else 0
        ma20 = sum(c[-20:]) / 20
        ma50 = sum(c[max(0, len(c)-50):]) / min(50, len(c))
        rises = sum([1 for i in range(max(0, len(c)-20), len(c)-1) if c[i+1] > c[i]])
        rsi = max(0, min(100, 50 + (cls - ma20) / ma20 * 50))
        sma_x = 100 if cls > ma50 else 0
        macd = statistics.pstdev(c[-12:]) - statistics.pstdev(c[-26:]) if len(c) >= 26 else 0
        macd_s = 100 if macd > 0 else 0
        vol_s = 50 + rises * 2.5
        rets = [(c[i] - c[i-1]) / c[i-1] for i in range(1, len(c))]
        std = statistics.pstdev(rets)*100 if len(rets) > 1 else 1
        t_score = (rsi * 0.3 + sma_x + macd_s + vol_s) / 4
        m_score = (wk * 30 + mo * 50 + yr * 20)
        s_score = min(100, max(0, 75 - std * 1.5))
        v_score = max(0, min(100, 100 - std * 8))
        score = max(0, min(100, t_score * 0.4 + m_score * 0.3 + s_score * 0.2 + v_score * 0.1))
        return {
            "ticker": ticker, "name": info.get("name", ticker), "category": info.get("category", "Asset"),
            "price": cls, "score": round(score, 1), "rsi": round(rsi, 1),
            "change_7d": round(wk*100, 1), "change_30d": round(mo*100, 1), "change_yr": round(yr*100, 1),
            "signal": "BULLISH" if score >= 60 else "NEUTRAL" if score >= 45 else "BEARISH",
            "factors": [f"RSI {round(rsi)} {'bullish' if rsi > 50 else 'bearish'}",
                        f"{'Above' if cls > ma50 else 'Below'} SMA20",
                        f"MACD {'bullish' if macd > 0 else 'bearish'}",
                        f"{round(wk*100, 1)}% week"]
        }
    except:
        return None

# ThreadPool approach — each thread has full 30s timeout via yfinance
tickers = list(universe.keys())
print(f"Scoring {len(tickers)} assets with ThreadPool...\n")

start = time.time()
results = []
with ThreadPoolExecutor(max_workers=10) as ex:
    futures = {ex.submit(score_one, t, universe[t]): t for t in tickers}
    done = 0
    for fut in futures:
        try:
            r = fut.result(timeout=35)
            if r:
                results.append(r)
            done += 1
            if done % 50 == 0:
                print(f"  Progress: {done}/{len(tickers)} ({round(time.time()-start)}s)")
        except:
            done += 1

elapsed = time.time() - start
print(f"\n{'='*60}")
print(f"SCORED: {len(results)} / {len(tickers)} ({round(len(results)/len(tickers)*100,1)}%)")
print(f"Time: {round(elapsed/60,1)} minutes")
print(f"{'='*60}\n")

results.sort(key=lambda x: x["score"], reverse=True)
top = results[0] if results else None

if top:
    print(f"🏆 TOP PICK: {top['name']} ({top['ticker']})")
    print(f"   Score: {top['score']}/100 | Signal: {top['signal']} | ${top['price']:.2f}")
    print(f"   Category: {top['category']}")
    print(f"   Week: {top['change_7d']:+.1f}% | Month: {top['change_30d']:+.1f}%")

    pick = {
        "generated_at": datetime.now().isoformat(),
        "week_label": "Week of Aug 11, 2026",
        "top_pick": top,
        "rationale": f"Technical: {round(top['score']*0.4)}/100 | Momentum: {round(top['score']*0.3)}/100 | Sentiment: {round(top['score']*0.2)}/100 | Volatility: {round(top['score']*0.1)}/100",
        "top_five": results[:5],
        "best_etf_of_week": next((a for a in results if a.get("category") == "ETF"), top)
    }
    json.dump(pick, open(base / "weekly_pick.json", "w"), indent=2)
    
    # Update data.json too
    try:
        with open(base / "data.json") as f:
            d = json.load(f)
    except:
        d = {}
    d["weekly_pick"] = pick
    d["timestamp"] = datetime.now().isoformat()
    json.dump(d, open(base / "data.json", "w"), indent=2)
    
    print(f"\nFiles saved:")
    print(f"  weekly_pick.json → {base/'weekly_pick.json'}")
    print(f"  data.json → {base/'data.json'}")
    print()
    print("Top 20:")
    for i, a in enumerate(results[:20], 1):
        print(f"  {i:2d}. {a['ticker']:10} {a['score']:5.1f} | ${a['price']:>10.2f} | {a['change_7d']:+6.1f}% | {a['category']}")
else:
    print("No valid results!")
