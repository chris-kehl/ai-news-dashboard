#!/usr/bin/env python3
"""Auto-update Market Analysis charts and scores every Sunday afternoon.
Fetches live prices from Yahoo Finance, generates score-based analysis,
and patches index.html with fresh data. Run this via cron on Sundays at 2pm.
"""

import os, sys, json, datetime, re
from pathlib import Path

HTML_PATH = Path.home() / "ai-news-dashboard" / "index.html"

def fetch_yf(ticker: str):
    """Fetch recent data from Yahoo Finance public API."""
    import urllib.request, urllib.error
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1d&range=1mo"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
        result = data["chart"]["result"][0]
        meta = result["meta"]
        closes = [c for c in result["indicators"]["quote"][0]["close"] if c is not None]
        return {
            "price": meta.get("regularMarketPrice") or closes[-1],
            "prev_close": meta.get("previousClose") or closes[-2],
            "52w_high": meta.get("fiftyTwoWeekHigh"),
            "52w_low": meta.get("fiftyTwoWeekLow"),
            "closes": closes,
        }
    except Exception as e:
        print(f"WARN: {ticker} fetch failed: {e}")
        return None


def spx_analysis(d):
    closes = d["closes"]
    price = closes[-1]
    wk_ago = closes[-6] if len(closes) >= 6 else closes[0]
    chg_5d = (price / wk_ago - 1) * 100
    # Simple trend score
    score = 6.0
    if chg_5d > 1.5: score += 1.0
    if price > sum(closes[-20:]) / len(closes[-20:]): score += 0.5
    bias = "BULLISH" if score >= 6.5 else "NEUTRAL" if score >= 4.5 else "BEARISH"
    text = (
        f"<strong>Bias: {bias} — Score {score:.1f}/10</strong> — "
        f"S&P 500 at {price:,.0f}, {'+' if chg_5d >= 0 else ''}{chg_5d:.2f}% over 5 sessions. "
        f"The index is {'above' if price > sum(closes[-20:])/len(closes[-20:]) else 'below'} its 20-day moving average. "
        f"Key level: {'hold above prior highs for continuation toward 7,700+' if bias == 'BULLISH' else 'watch 7,400 support; a close below flips bearish' if bias == 'NEUTRAL' else 'breakdown below 7,400 targets 7,250'}. "
        f"Risk: earnings dispersion and Fed-speak."
    )
    return text


def rty_analysis(d):
    closes = d["closes"]
    price = closes[-1]
    wk_ago = closes[-6] if len(closes) >= 6 else closes[0]
    chg_5d = (price / wk_ago - 1) * 100
    score = 6.0
    if chg_5d > 1.0: score += 1.0
    if price > sum(closes[-10:]) / len(closes[-10:]): score += 0.5
    bias = "BULLISH" if score >= 6.5 else "NEUTRAL"
    text = (
        f"<strong>Bias: {bias} — Score {score:.1f}/10</strong> — "
        f"Russell 2000 at ${price:,.2f}, {'+' if chg_5d >= 0 else ''}{chg_5d:.2f}% over 5 sessions. "
        f"Small-caps are {'building momentum above the 10-day MA' if bias == 'BULLISH' else 'consolidating near the 50-day MA'}. "
        f"Target on continuation: ${price * 1.02:,.0f}. Stop: close below ${price * 0.97:,.0f}. "
        f"Risk: SPX correlation drag if large-caps sell off."
    )
    return text


def acwx_analysis(d):
    closes = d["closes"]
    price = closes[-1]
    wk_ago = closes[-6] if len(closes) >= 6 else closes[0]
    chg_5d = (price / wk_ago - 1) * 100
    score = 6.5
    if chg_5d > 1.5: score += 0.5
    if d.get("52w_high") and price >= d["52w_high"] * 0.98: score += 0.5
    bias = "BULLISH" if score >= 6.5 else "NEUTRAL"
    text = (
        f"<strong>Bias: {bias} — Score {score:.1f}/10</strong> — "
        f"ACWX at ${price:.2f}, {'+' if chg_5d >= 0 else ''}{chg_5d:.2f}% over 5 sessions. "
        f"{'Price is pressing the 52-week high — a breakout opens a measured move.' if d.get('52w_high') and price >= d['52w_high'] * 0.98 else 'Price is consolidating near highs; watch for a breakout confirmation.'} "
        f"Tailwind: dollar softness / Fed-cut pricing. Risk: DXY snap-back. "
        f"Stop: close below ${price * 0.96:,.2f}."
    )
    return text


def emxc_analysis(d):
    closes = d["closes"]
    price = closes[-1]
    wk_ago = closes[-6] if len(closes) >= 6 else closes[0]
    chg_5d = (price / wk_ago - 1) * 100
    score = 5.0
    if abs(chg_5d) < 1.0: score -= 0.5  # chop penalty
    if len(closes) >= 20 and abs((price / closes[-20] - 1) * 100) < 2.0: score -= 0.5  # flat month
    bias = "NEUTRAL" if 4.0 <= score <= 6.0 else "BULLISH" if score > 6.0 else "BEARISH"
    text = (
        f"<strong>Bias: {bias} — Score {score:.1f}/10</strong> — "
        f"EMXC at ${price:.2f}, {'+' if chg_5d >= 0 else ''}{chg_5d:.2f}% over 5 sessions. "
        f"Chopping in a tight range with semi-weight dragging. No directional edge yet. "
        f"Flip bullish above ${price * 1.02:,.2f}; flip bearish below ${price * 0.97:,.2f}. "
        f"Catalysts: Samsung/Hynix guidance, India PMI."
    )
    return text


def patch_html(path: Path):
    html = path.read_text()
    
    tickers = {
        "^GSPC": spx_analysis,   # Yahoo uses ^GSPC for S&P 500
        "^RUT": rty_analysis,    # Yahoo uses ^RUT for Russell 2000
        "ACWX": acwx_analysis,
        "EMXC": emxc_analysis,
    }
    
    for ticker_sym, analyzer in tickers.items():
        data = fetch_yf(ticker_sym)
        if not data:
            continue
        analysis_text = analyzer(data)
        
        # Find the tv-desc div that follows the correct sub-tab
        sub_id = {
            "^GSPC": "sub-tab-spx",
            "^RUT": "sub-tab-rty",
            "ACWX": "sub-tab-acwx",
            "EMXC": "sub-tab-emxc",
        }[ticker_sym]
        
        # Pattern: <div id="sub-tab-xxx" ...> ... <div class="tv-desc">OLD_TEXT</div>
        pattern = rf'(<div id="{sub_id}"[^>]*>.*?<div class="tv-desc">)(.*?)(</div>)'
        replacement = rf'\1{analysis_text}\3'
        new_html = re.sub(pattern, replacement, html, count=1, flags=re.DOTALL)
        if new_html != html:
            html = new_html
            print(f"  Patched {ticker_sym}")
        else:
            print(f"  WARN: no patch match for {ticker_sym}")
    
    path.write_text(html)
    print(f"Wrote updated HTML to {path}")


def git_push():
    import subprocess
    wd = HTML_PATH.parent
    subprocess.run(["git", "add", "index.html"], cwd=wd, check=True)
    date_str = datetime.datetime.now().strftime("%Y-%m-%d")
    subprocess.run(["git", "commit", "-m", f"Auto-update Market Analysis ({date_str})"], cwd=wd, check=False)
    subprocess.run(["git", "push", "origin", "main"], cwd=wd, check=False)
    print("Pushed to origin/main")


if __name__ == "__main__":
    print(f"Market Analysis Auto-Update — {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}")
    patch_html(HTML_PATH)
    git_push()
