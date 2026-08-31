#!/usr/bin/env python3
"""
Focused weekly pick scorer — batch download version.
Runs full scoring, picks top asset (shows highest even if <80),
generates chart, updates data.json + weekly_pick.json, commits & pushes.
"""
import json, subprocess, time
from datetime import datetime
from pathlib import Path
import warnings
warnings.filterwarnings('ignore')

import yfinance as yf
import pandas as pd

ROOT = Path('/Users/chris/ai-news-dashboard')
UNIVERSE_FILE = ROOT / '.cache' / 'universe_full.json'

# Known delisted/problematic tickers — skip to save time and avoid hangs
DELISTED = frozenset({'BK', 'FLT', 'IPG', 'K', 'MMC'})

def load_universe():
    if UNIVERSE_FILE.exists():
        raw = json.load(open(UNIVERSE_FILE))['tickers']
        return [u for u in raw if u['ticker'] not in DELISTED]
    sp100 = "AAPL ABT ABBV ACN ADBE ABNB ACGL AES AFL AIG ALL ALB AMAT AMD AMGN AMT AMZN ANET AON APA APD APH ARKK AVGO AXP BA BAC BAX BBY BDX BIIB BKNG BLK BMY BRK-B BSX BWA BX C CAT CB CBOE CCI CCL CDNS CF CHTR CI CINF CL CLX CMCSA CMI CMS CNC CNP COF COP COST CPB CRM CSCO CSX CTAS CTSH CVS CVX D DASH DAL DD DE DELL DHI DHR DIS DLR DOV DOW DPZ DRI DTE DUK DVA DVN DXCM EA EBAY ECL ED EIX EL ELV EMR ENPH EOG EPAM EQIX EQT ES ESS ETN EW EXC EXPE EXR F FAST FCX FDX FE FIS FISV FITB FMC FOXA FRT FTV GD GFS GILD GIS GL GLW GM GOOG GOOGL GPC GPN GRMN GS GWW HAL HAS HBAN HCA HD HIG HII HLT HON HPQ HRL HSIC HST HSY HUM IBM ICE IDXX IEX IFF ILMN INCY INTC INTU IQV IR IRM ISRG IT ITW IVZ J JBHT JCI JKHY JNJ JPM KDP KE KHC KIM KKR KLAC KMX KO KR LEN LH LHX LIN LKQ LLY LMT LNC LNT LOW LRCX LUMN LUV LVS LW LYB LYV M MA MAA MAR MAS MCD MCHP MCK MCO MDB MDLZ MDT MET MGM MKC MLM MMM MNST MO MOH MOS MPC MPWR MRK MRNA MS MSCI MSFT MSI MTB MTCH MTD MU NDAQ NEE NEM NFLX NKE NOC NSC NTAP NTRS NUE NVDA NVR NOW NRG NXPI O ODFL OGN OKE OMC ON ORCL ORLY OXY PANW PARA PAYC PAYX PCAR PCRX PDD PEG PEP PFE PFG PG PGR PH PHM PLD PM PNC PNR PNW POOL PPG PPL PRU PSA PSX PTC PTON PWR PYPL QCOM QRVO RCL REGN RF RHI RJF RL RMD ROK ROL ROP ROST RSG RTX RVTY SBAC SBUX SCHW SHW SJM SLB SNA SNPS SO SPG SPGI SRE STE STT STX STZ SWK SWKS SYF SYK SYY T TAP TDG TDY TEL TFC TFX TGT TJX TMO TMUS TPR TRV TSCO TSLA TSN TT TW TXN TXT TYL UAL UBER UDR UHS ULTA UNH UNP UPS URI USB V VFC VLO VMC VRSK VRTX VST VTR VTRS VZ WAB WAT WBA WBD WDC WEC WELL WFC WHR WM WMB WMT WSC WST WTW WY WYNN XEL XOM XRAY XYL YUM ZBH ZBRA ZION ZTS".split()

    crypto = ['BTC-USD', 'ETH-USD', 'SOL-USD', 'XRP-USD', 'DOGE-USD',
              'ADA-USD', 'AVAX-USD', 'LINK-USD', 'DOT-USD']
    metals = ['GC=F', 'SI=F', 'PL=F', 'PA=F', 'HG=F']
    etfs = ['SPY', 'IVV', 'VOO', 'VTI', 'QQQ', 'IWM', 'VUG', 'VTV', 'VEA', 'VXUS',
            'BND', 'AGG', 'LQD', 'HYG', 'TLT', 'IEF', 'SHY', 'GLD', 'SLV', 'IAU',
            'VNQ', 'REET', 'VGT', 'XLK', 'XLF', 'XLE', 'XLI', 'XLP', 'XLU', 'XLB',
            'XRT', 'ARKK', 'ARKQ', 'ARKW', 'PRNT', 'IZRL', 'BOTZ', 'ROBO', 'LIT',
            'ICLN', 'PBW', 'QCLN', 'SMH', 'SOXX', 'FDN', 'SKYY', 'WCLD', 'CIBR',
            'HACK', 'SILJ', 'URA', 'NLR', 'COPX', 'PICK', 'REMX',
            'TAN', 'FAN', '^VIX']
    universe = []
    seen = set()
    etf_tickers = frozenset(etfs)
    for t in sp100 + crypto + metals + etfs:
        if t not in seen and t not in DELISTED:
            seen.add(t)
            if '-USD' in t:
                cat = 'Crypto'
            elif t.endswith('=F') and t[0] in 'GSIPH':
                cat = 'Precious Metal'
            elif t in etf_tickers:
                cat = 'ETF'
            elif t == '^VIX':
                cat = 'Index'
            else:
                cat = 'Equity - S&P 500'
            universe.append({'ticker': t, 'category': cat, 'name': t})
    return universe


def batch_download(tickers, period='90d'):
    try:
        df = yf.download(
            tickers, period=period, group_by='ticker',
            progress=False, timeout=20, threads=False, auto_adjust=True
        )
        result = {}
        if isinstance(tickers, str):
            tickers = [tickers]
        for t in tickers:
            if len(tickers) == 1:
                sub = df
            else:
                if t not in df.columns.get_level_values(0).unique():
                    continue
                sub = df[t]
            sub = sub.dropna()
            if not sub.empty and len(sub) >= 20:
                result[t] = sub
        return result
    except Exception as e:
        print(f'  Batch download error: {e}')
        return {}


def score_one(ticker, info, hist):
    try:
        price = float(hist['Close'].iloc[-1])
        if price <= 0:
            return None

        chg_7d = ((price / float(hist['Close'].iloc[-6]) - 1) * 100) if len(hist) >= 6 else 0
        chg_30d = ((price / float(hist['Close'].iloc[-22]) - 1) * 100) if len(hist) >= 22 else 0

        vol_recent = float(hist['Volume'].tail(10).mean())
        vol_old = float(hist['Volume'].head(10).mean())
        vol_trend = ((vol_recent / vol_old - 1) * 100) if vol_old > 0 else 0

        delta = hist['Close'].diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / loss
        rsi_val = float(100 - (100 / (1 + rs.iloc[-1]))) if not pd.isna(rs.iloc[-1]) else 50

        ema12 = hist['Close'].ewm(span=12).mean()
        ema26 = hist['Close'].ewm(span=26).mean()
        macd = float(ema12.iloc[-1] - ema26.iloc[-1])
        signal = float(ema12.iloc[-1] - ema26.iloc[-1] - (ema12.iloc[-2] - ema26.iloc[-2]))
        macd_rising = signal > 0 or macd > 0

        tech_score = min(36, max(0, (rsi_val - 30) * 0.6 + (10 if macd_rising else 0) + (5 if chg_7d > 5 else 0) + (5 if chg_30d > 10 else 0)))
        fund_score = min(18, max(0, 12 + (3 if chg_30d > 5 else 0) + (3 if vol_trend > 10 else 0)))
        sent_score = min(19, max(0, 10 + (5 if chg_7d > 2 else 0) + (4 if abs(chg_7d) > 5 else 0)))
        total = round(tech_score + fund_score + sent_score, 1)

        return {
            'ticker': ticker,
            'name': info.get('name', ticker),
            'price': round(price, 2),
            'score': total,
            'change_7d': round(chg_7d, 2),
            'change_30d': round(chg_30d, 2),
            'rsi': round(rsi_val, 1),
            'category': info['category'],
            'factors': [f'T:{tech_score:.0f}', f'F:{fund_score:.0f}', f'S:{sent_score:.0f}']
        }
    except Exception:
        return None


def run():
    print(f'[{datetime.now().strftime("%H:%M:%S")}] Starting focused weekly pick scorer (batch mode)')
    universe = load_universe()
    print(f'Universe: {len(universe)} assets')

    BATCH_SIZE = 35
    results = []
    total_batches = (len(universe) + BATCH_SIZE - 1) // BATCH_SIZE
    for batch_idx in range(0, len(universe), BATCH_SIZE):
        batch = universe[batch_idx:batch_idx + BATCH_SIZE]
        tickers = [u['ticker'] for u in batch]
        print(f'  Batch {batch_idx//BATCH_SIZE + 1}/{total_batches}: downloading {len(tickers)} tickers...')
        hists = batch_download(tickers)
        print(f'    Got data for {len(hists)} tickers, scoring...')
        for u in batch:
            t = u['ticker']
            if t in hists:
                r = score_one(t, u, hists[t])
                if r:
                    results.append(r)
        print(f'    Running total: {len(results)} scored')
        if batch_idx + BATCH_SIZE < len(universe):
            time.sleep(0.3)

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

    week_label = f'Week of {datetime.now().strftime("%b %d, %Y")}'

    etf_scores = [r for r in results if r['category'] == 'ETF']
    best_etf = etf_scores[0] if etf_scores else None

    wp = {
        'generated_at': datetime.now().isoformat(),
        'week_label': week_label,
        'top_pick': top,
        'top_five': results[:5],
    }
    if best_etf:
        wp['best_etf_of_week'] = best_etf

    wp_file = ROOT / 'weekly_pick.json'
    json.dump(wp, open(wp_file, 'w'), indent=2)
    print(f'\n[OK] Written to {wp_file.name}: {top["name"]} ({top["ticker"]}) Score {top["score"]}')

    data_file = ROOT / 'data.json'
    data = json.load(open(data_file)) if data_file.exists() else {}
    data['weekly_pick'] = wp
    if best_etf:
        data['best_etf_of_week'] = {
            'ticker': best_etf['ticker'], 'name': best_etf['name'],
            'display_name': best_etf['name'],
            'price': best_etf['price'], 'score': best_etf['score'],
            'change_7d': best_etf['change_7d'],
            'change_30d': best_etf['change_30d'],
            'category': best_etf['category'],
            'rationale': f'Score: {best_etf["score"]}/100 ({" | ".join(best_etf["factors"])})\n\nPrice: ${best_etf["price"]} | 7d: {best_etf["change_7d"]:+.2f}% | 30d: {best_etf["change_30d"]:+.2f}% | RSI: {best_etf["rsi"]}\n\nDisclaimer: Not financial advice.'
        }
    data['timestamp'] = datetime.now().isoformat()
    json.dump(data, open(data_file, 'w'), indent=2)
    print(f'[OK] Updated data.json with {top["ticker"]} + {best_etf["ticker"] if best_etf else "no ETF"}')

    try:
        chart_cmd = [str(ROOT / 'venv' / 'bin' / 'python3'),
                     str(ROOT / 'generate_weekly_pick_chart.py'),
                     top['ticker'], top['name']]
        subprocess.run(chart_cmd, cwd=str(ROOT), check=True, capture_output=True)
        print(f'[OK] Chart generated for {top["ticker"]}')
    except Exception as e:
        print(f'[WARN] Chart generation failed: {e}')

    try:
        subprocess.run(['git', 'add', '-A'], cwd=str(ROOT), check=True, capture_output=True)
        subprocess.run(['git', 'commit', '-m', f'weekly: {top["ticker"]} score {top["score"]} ({week_label})'],
                       cwd=str(ROOT), check=False, capture_output=True)
        subprocess.run(['git', 'push'], cwd=str(ROOT), check=True, capture_output=True)
        print('[OK] Pushed to GitHub')
    except Exception as e:
        print(f'[WARN] Git push failed: {e}')

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
    run()
