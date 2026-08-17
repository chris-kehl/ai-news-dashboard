#!/usr/bin/env python3
"""Weekly Market Outlook script — scores SPY, IWM, ACWX, EMXC and generates chart + JSON."""
import json, os
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor
import yfinance as yf
import matplotlib
matplotlib.use('agg')
import matplotlib.pyplot as plt

ROOT = os.path.expanduser('~/ai-news-dashboard')
tickers = {
    'SPY': 'S&P 500',
    'IWM': 'Russell 2000', 
    'ACWX': 'ACWX (World ex-US)',
    'EMXC': 'EMXC (EM ex-China)'
}

def analyze(t, label):
    try:
        tk = yf.Ticker(t)
        hist = tk.history(period='90d')
        if hist.empty or len(hist) < 20:
            return None
        price = float(hist['Close'].iloc[-1])
        chg_1d = ((price / float(hist['Close'].iloc[-2]) - 1) * 100) if len(hist) >= 2 else 0
        chg_7d = ((price / float(hist['Close'].iloc[-6]) - 1) * 100) if len(hist) >= 6 else 0
        chg_30d = ((price / float(hist['Close'].iloc[-22]) - 1) * 100) if len(hist) >= 22 else 0
        chg_60d = ((price / float(hist['Close'].iloc[-44]) - 1) * 100) if len(hist) >= 44 else 0
        
        delta = hist['Close'].diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / loss
        rsi = float(100 - (100 / (1 + rs.iloc[-1]))) if rs.iloc[-1] == rs.iloc[-1] else 50
        
        ema12 = hist['Close'].ewm(span=12).mean()
        ema26 = hist['Close'].ewm(span=26).mean()
        macd = float(ema12.iloc[-1] - ema26.iloc[-1])
        sig = float((ema12.iloc[-1] - ema26.iloc[-1]) - (ema12.iloc[-2] - ema26.iloc[-2]))
        macd_rising = sig > 0 or macd > 0
        
        # Signal determination
        score = 0
        if chg_7d > 0: score += 2
        if chg_30d > 2: score += 2
        if rsi > 50 and rsi < 75: score += 2
        if macd_rising: score += 2
        if price > float(hist['Close'].tail(20).mean()): score += 2
        
        if score >= 8:
            signal = 'BULLISH'
        elif score >= 5:
            signal = 'BULLISH' if chg_7d > 0 else 'NEUTRAL'
        elif score >= 3:
            signal = 'NEUTRAL'
        else:
            signal = 'BEARISH'
        
        # Overbooked check
        if rsi > 78:
            signal = 'CAUTION'
        
        # Narrative
        notes = {
            'SPY': f'{"RSI " + str(round(rsi,1)) + " - " if rsi > 70 else ""}At 90d range. {"Bullish momentum above MA20/MA50." if macd_rising else "Consolidating below resistance."}',
            'IWM': f'Small-caps {"leading rotation" if chg_7d > chg_30d else "building base"}. RSI {round(rsi,1)}.',
            'ACWX': f'{"Overbought at RSI " + str(round(rsi,1)) + "." if rsi > 75 else ""} Dollar softness benefiting international.',
            'EMXC': f'{"Explosive +" + str(round(chg_7d,1)) + "% weekly move." if chg_7d > 3 else "Steady accumulation."} RSI {round(rsi,1)}.'
        }[t]
        
        return {
            'ticker': t,
            'name': label,
            'current': round(price, 2),
            'change_1d': round(chg_1d, 2),
            'change_7d': round(chg_7d, 2),
            'change_30d': round(chg_30d, 2),
            'change_60d': round(chg_60d, 2),
            'rsi': round(rsi, 1),
            'signal': signal,
            'notes': notes,
            'prices': [float(c) for c in hist['Close']]
        }
    except Exception as e:
        return {'ticker': t, 'error': str(e)}

def run():
    print(f'[{datetime.now().strftime("%H:%M:%S")}] Generating Weekly Market Outlook...')
    
    # Analyze all 4
    results = {}
    with ThreadPoolExecutor(max_workers=4) as ex:
        futures = {ex.submit(analyze, t, l): t for t, l in tickers.items()}
        for f in futures:
            t = futures[f]
            r = f.result()
            if r and 'error' not in r:
                results[t] = r
                print(f'  {t}: {r["signal"]} | Price: ${r["current"]} | 7D: {r["change_7d"]:+.2f}% | RSI: {r["rsi"]}')
    
    if len(results) < 4:
        print('WARNING: Only got', len(results), 'of 4 benchmarks')
    
    analysis_date = datetime.now().strftime('%B %d, %Y')
    
    # Generate chart
    fig, ax = plt.subplots(figsize=(12, 6))
    fig.patch.set_facecolor('#0d1117')
    ax.set_facecolor('#0d1117')
    colors = {'SPY': '#22c55e', 'IWM': '#3b82f6', 'ACWX': '#f59e0b', 'EMXC': '#ef4444'}
    
    for t in ['SPY', 'IWM', 'ACWX', 'EMXC']:
        if t in results:
            prices = results[t]['prices']
            base = prices[0]
            pct = [(p/base - 1)*100 for p in prices]
            ax.plot(range(len(prices)), pct, color=colors[t], linewidth=2.5, label=tickers[t])
    
    ax.axhline(y=0, color='#30363d', linewidth=0.5, linestyle='--')
    ax.set_title(f'Weekly Market Outlook — {analysis_date}', color='#f0f6fc', fontsize=14, pad=15)
    ax.set_ylabel('% Change from 90D Ago', color='#9198a1')
    ax.legend(loc='upper left', facecolor='#161b22', edgecolor='#30363d', labelcolor='#f0f6fc', fontsize=10)
    ax.tick_params(colors='#9198a1')
    ax.grid(True, alpha=0.15, color='#30363d')
    plt.tight_layout()
    
    chart_path = os.path.join(ROOT, 'weekly_outlook_chart.png')
    plt.savefig(chart_path, dpi=130, facecolor='#0d1117', edgecolor='none')
    plt.close()
    print(f'Chart saved: {chart_path}')
    
    # Build outlook JSON
    outlook = {
        'analysis_date': analysis_date,
        'generated_at': datetime.now().isoformat(),
        'benchmarks': {t: {k: v for k, v in results[t].items() if k != 'prices'} for t in results}
    }
    
    json_path = os.path.join(ROOT, 'weekly_outlook_data.json')
    json.dump(outlook, open(json_path, 'w'), indent=2)
    print(f'Data saved: {json_path}')
    
    # Update data.json
    data_path = os.path.join(ROOT, 'data.json')
    data = json.load(open(data_path)) if os.path.exists(data_path) else {}
    data['weekly_outlook'] = outlook
    data['timestamp'] = datetime.now().isoformat()
    json.dump(data, open(data_path, 'w'), indent=2)
    print(data_path)
    
    # Git push
    import subprocess
    try:
        subprocess.run(['git', 'add', '-A'], cwd=ROOT, check=True, capture_output=True)
        subprocess.run(['git', 'commit', '-m', f'weekly-outlook: {analysis_date}'], cwd=ROOT, check=False, capture_output=True)
        subprocess.run(['git', 'push'], cwd=ROOT, check=True, capture_output=True)
        print('[OK] Deployed')
    except Exception as e:
        print(f'[WARN] Git push: {e}')
    
    print(f'\n{"="*50}')
    print(f'WEEKLY OUTLOOK: {analysis_date}')
    for t in ['SPY', 'IWM', 'ACWX', 'EMXC']:
        if t in results:
            r = results[t]
            print(f'  {t:5s}: {r["signal"]:9s} | ${r["current"]:>8.2f} | 7D: {r["change_7d"]:>+6.2f}% | RSI: {r["rsi"]:>5.1f}')
    print(f'{"="*50}')

if __name__ == '__main__':
    run()
