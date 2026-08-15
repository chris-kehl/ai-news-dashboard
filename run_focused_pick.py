#!/usr/bin/env python3
"""
Focused weekly pick scorer — 249 priority assets.
Runs full scoring, picks top asset (shows highest even if <80),
generates chart, updates data.json + weekly_pick.json, commits & pushes.
"""
import json, os, time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

import yfinance as yf

ROOT = Path('/Users/chris/ai-news-dashboard')
UNIVERSE_FILE = ROOT / '.cache' / 'universe_full.json'

def load_universe():
    if UNIVERSE_FILE.exists():
        return json.load(open(UNIVERSE_FILE))['tickers']
    # Fallback: hard-coded focused universe
    sp100 = "AAPL ABT ABBV ACN ADBE ABNB ABT ACGL AES AFL AIG ALL ALB AMAT AMD AMGN AMT AMZN ANET AON APA APD APH ARKK AVGO AXP BA BAC BAX BBY BDX BIIB BK BKNG BLK BMY BRK-B BSX BWA BX C CAT CB CBOE CCI CCL CDNS CF CHTR CHTV CI CINF CL CLX CMCSA CMI CMS CNC CNP COF COP COST CPB CRM CSCO CSX CTAS CTSH CVS CVX D DASH DAL DD DE DELL DHI DHR DIS DLR DOV DOW DPZ DRI DTE DUK DVA DVN DXCM EA EBAY ECL ED EIX EL ELV EMR ENPH EOG EPAM EQIX EQT ES ESS ETN EW EXC EXPE EXR F FAST FCX FDX FE FIS FISV FITB FLT FMC FOXA FRT FTV GD GEE GFS GILD GIS GL GLW GM GOOG GOOGL GPC GPN GRMN GS GWW HAL HAS HBAN HCA HD HES HIG HII HLT HOLX HON HPQ HRL HSIC HST HSY HUM IBM ICE IDXX IEX IFF ILMN INCY INTC INTU IP IPG IQV IR IRM ISRG IT ITW IVZ J JBHT JCI JKHY JNJ JPM K KDP KE KHC KIM KKR KLAC KMX KNI KO KR LEN LH LHX LIN LKQ LLY LMT LNC LNT LOW LRCX LUMN LUV LVS LW LYB LYV M MA MAA MAR MAS MCD MCHP MCK MCO MDB MDLZ MDT MET MGM MKC MLM MMC MMM MNST MO MOH MOS MPC MPWR MRK MRNA MRO MS MSCI MSFT MSI MTB MTCH MTD MU NDAQ NEE NEM NFLX NKE NOC NSC NTAP NTRS NUE NVDA NVR NOW NRG NXPI O ODFL OGN OKE OMC ON ORCL ORLY OXY PANW PARA PAYC PAYX PCAR PCRX PDD PEG PEP PFE PFG PG PGR PH PHM PLD PM PNC PNR PNW POOL PPG PPL PRU PSA PSX PTC PTON PWR PYPL QCOM QRVO RCL REGN RF RHI RJF RL RMD ROK ROL ROP ROST RSG RTX RVTY SBAC SBUX SCHW SHW SJM SLB SNA SNPS SO SPG SPGI SPLK SRE STE STT STX STZ SWK SWKS SYF SYK SYY T TAP TDG TDY TEL TFC TFX TGT TJX TMO TMUS TPR TRV TSCO TSLA TSN TT TW TXN TXT TYL UAL UBER UDR UHS ULTA UNH UNP UPS URI USB V VFC VLO VMC VRSK VRTX VST VTR VTRS VZ WAB WAT WBA WBD WDC WEC WELL WFC WHR WM WMB WMT WSC WST WTW WY WYNN XEL XOM XRAY XYL YUM ZBH ZBRA ZION ZTS".split()
    
    crypto = ['BTC-USD', 'ETH-USD', 'SOL-USD', 'XRP-USD', 'DOGE-USD',
              'ADA-USD', 'AVAX-USD', 'LINK-USD', 'DOT-USD', 'MATIC-USD']
    metals = ['GC=F', 'SI=F', 'PL=F', 'PA=F', 'HG=F']
    etfs = ['SPY', 'IVV', 'VOO', 'VTI', 'QQQ', 'IWM', 'VUG', 'VTV', 'VEA', 'VXUS',
            'BND', 'AGG', 'LQD', 'HYG', 'TLT', 'IEF', 'SHY', 'GLD', 'SLV', 'IAU',
            'VNQ', 'REET', 'VGT', 'XLK', 'XLF', 'XLE', 'XLI', 'XLP', 'XLU', 'XLB',
            'XRT', 'ARKK', 'ARKQ', 'ARKW', 'PRNT', 'IZRL', 'BOTZ', 'ROBO', 'LIT',
            'ICLN', 'PBW', 'QCLN', 'SMH', 'SOXX', 'FDN', 'SKYY', 'WCLD', 'CIBR',
            'HACK', 'SILJ', 'URA', 'NLR', 'KOL', 'COPX', 'PICK', 'LIT', 'REMX',
            'TAN', 'FAN', '^VIX']
    
    universe = []
    seen = set()
    for t in sp100 + crypto + metals + etfs:
        if t not in seen:
            seen.add(t)
            cat = 'Crypto' if '-USD' in t else 'Precious Metal' if t.endswith('=F') and t[0] in 'GSIPH' else 'ETF' if len(t) <= 5 and not t.isalpha() and not t.endswith('=F') else 'Equity - S&P 500'
            if t == '^VIX': cat = 'Index'
            universe.append({'ticker': t, 'category': cat})
    return universe


def score_asset(ticker_info):
    t = ticker_info['ticker']
    try:
        tk = yf.Ticker(t)
        hist = tk.history(period='90d')
        if hist.empty or len(hist) < 20:
            return None
        
        price = float(hist['Close'].iloc[-1])
        if price <= 0:
            return None
        
        # Price changes
        chg_7d = ((price / float(hist['Close'].iloc[-6]) - 1) * 100) if len(hist) >= 6 else 0
        chg_30d = ((price / float(hist['Close'].iloc[-22]) - 1) * 100) if len(hist) >= 22 else 0
        
        # Volume trend
        vol_recent = float(hist['Volume'].tail(10).mean())
        vol_old = float(hist['Volume'].head(10).mean())
        vol_trend = ((vol_recent / vol_old - 1) * 100) if vol_old > 0 else 0
        
        # RSI
        delta = hist['Close'].diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / loss
        rsi = float(100 - (100 / (1 + rs.iloc[-1]))) if not pd.isna(rs.iloc[-1]) else 50
        
        # MACD
        ema12 = hist['Close'].ewm(span=12).mean()
        ema26 = hist['Close'].ewm(span=26).mean()
        macd = float(ema12.iloc[-1] - ema26.iloc[-1])
        signal = float(ema12.iloc[-1] - ema26.iloc[-1] - (ema12.iloc[-2] - ema26.iloc[-2]))
        macd_rising = signal > 0 or macd > 0
        
        # Score components
        tech_score = min(36, max(0, (rsi - 30) * 0.6 + (10 if macd_rising else 0) + (5 if chg_7d > 5 else 0) + (5 if chg_30d > 10 else 0)))
        fund_score = min(18, max(0, 12 + (3 if chg_30d > 5 else 0) + (3 if vol_trend > 10 else 0)))
        sent_score = min(19, max(0, 10 + (5 if chg_7d > 2 else 0) + (4 if abs(chg_7d) > 5 else 0)))
        
        total = round(tech_score + fund_score + sent_score, 1)
        
        return {
            'ticker': t,
            'name': tk.info.get('shortName', tk.info.get('longName', t)),
            'price': round(price, 2),
            'score': total,
            'change_7d': round(chg_7d, 2),
            'change_30d': round(chg_30d, 2),
            'rsi': round(rsi, 1),
            'category': ticker_info['category'],
            'factors': [f'T:{tech_score:.0f}', f'F:{fund_score:.0f}', f'S:{sent_score:.0f}']
        }
    except Exception as e:
        return None


def run():
    print(f'[{datetime.now().strftime("%H:%M:%S")}] Starting focused weekly pick scorer')
    
    universe = load_universe()
    print(f'Universe: {len(universe)} assets')
    
    print('Scoring...')
    results = []
    import pandas as pd
    with ThreadPoolExecutor(max_workers=8) as ex:
        for r in ex.map(score_asset, universe):
            if r:
                results.append(r)
    
    results.sort(key=lambda x: x['score'], reverse=True)
    print(f'\nScored {len(results)} assets')
    print('\nTop 10:')
    for i, r in enumerate(results[:10], 1):
        arrow = '↑' if r['change_7d'] >= 0 else '↓'
        print(f'  {i:2d}. {r["ticker"]:6s} | Score {r["score"]:>5.1f} | ${r["price"]:>10.2f} | {arrow}{r["change_7d"]:>6.2f}% | {r["category"]}')
    
    top = results[0] if results else None
    if not top:
        print('ERROR: No scores generated')
        return
    
    # Build weekly_pick.json
    week_label = f'Week of {datetime.now().strftime("%b %d, %Y")}'
    wp = {
        'generated_at': datetime.now().isoformat(),
        'week_label': week_label,
        'top_pick': top,
        'top_five': results[:5],
    }
    
    # Best ETF
    etf_scores = [r for r in results if r['category'] == 'ETF']
    best_etf = etf_scores[0] if etf_scores else None
    
    # Write weekly_pick.json
    wp_file = ROOT / 'weekly_pick.json'
    json.dump(wp, open(wp_file, 'w'), indent=2)
    print(f'\n[OK] Written to {wp_file.name}: {top["name"]} ({top["ticker"]}) Score {top["score"]}')
    
    # Update data.json
    data_file = ROOT / 'data.json'
    if data_file.exists():
        data = json.load(open(data_file))
    else:
        data = {}
    data['weekly_pick'] = wp
    if best_etf:
        data['best_etf_of_week'] = {'top_pick': best_etf, 'week_label': week_label}
    data['timestamp'] = datetime.now().isoformat()
    json.dump(data, open(data_file, 'w'), indent=2)
    print(f'[OK] Updated data.json with {top["ticker"]} + {best_etf["ticker"] if best_etf else "no ETF"}')
    
    # Generate chart
    try:
        import subprocess
        chart_cmd = [str(ROOT / 'venv' / 'bin' / 'python3'),
                     str(ROOT / 'generate_weekly_pick_chart.py'),
                     top['ticker'], top['name']]
        subprocess.run(chart_cmd, cwd=str(ROOT), check=True, capture_output=True)
        print(f'[OK] Chart generated for {top["ticker"]}')
    except Exception as e:
        print(f'[WARN] Chart generation failed: {e}')
    
    # Git commit & push
    try:
        subprocess.run(['git', 'add', '-A'], cwd=str(ROOT), check=True, capture_output=True)
        subprocess.run(['git', 'commit', '-m', f'weekly: {top["ticker"]} score {top["score"]} ({week_label})'],
                       cwd=str(ROOT), check=False, capture_output=True)
        subprocess.run(['git', 'push'], cwd=str(ROOT), check=True, capture_output=True)
        print('[OK] Pushed to GitHub')
    except Exception as e:
        print(f'[WARN] Git push failed: {e}')
    
    # Summary
    print(f'\n{"="*50}')
    print(f'WEEKLY PICK: {top["name"]} ({top["ticker"]})')
    print(f'Score: {top["score"]} / 100')
    print(f'Price: ${top["price"]}')
    print(f'7D: {top["change_7d"]:+.2f}% | 30D: {top["change_30d"]:+.2f}%')
    print(f'RSI: {top["rsi"]}')
    if top['score'] < 80:
        print(f'NOTE: Score below 80 threshold. This is the highest-scoring asset this week.')
    print(f'{"="*50}')


if __name__ == '__main__':
    import pandas as pd  # needed inside score_asset
    run()
