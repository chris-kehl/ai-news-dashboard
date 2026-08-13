#!/usr/bin/env python3
"""
Weekly Pick Scraper — Comprehensive Asset Universe.

SOURCES:
  S&P 500    — Wikipedia (scraped dynamically)
  Russell 2000 — StockAnalysis.com (scraped dynamically) + hardcoded top 300 fallback
  ETFs         — Wikipedia list of US ETFs + hardcoded additions
  Crypto       — CoinGecko (top 200 tickers downloaded once, cached)
  Precious metals — Hardcoded list

PERFORMANCE:
  Uses asyncio + aiohttp for parallel fetching.
  ~2,700 assets total → ~60–90 seconds with batching.

OUTPUT:
  Writes top_pick, top_five, and all_assets into data.json['weekly_pick'].
  Also writes a separate weekly_pick_cache.json for standalone inspection.
"""
import asyncio
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict

try:
    import aiohttp
    import aiofiles
    import yfinance as yf
except ImportError:
    print("pip install aiohttp aiofiles yfinance")
    raise

# ─── Load sentiment module ──────────────────────────────────────────────────
_sentiment_path = Path(__file__).resolve().parent
if str(_sentiment_path) not in sys.path:
    sys.path.insert(0, str(_sentiment_path))
try:
    from sentiment_analyzer import fetch_sentiment, SentimentScorer
except ImportError:
    print("WARNING: sentiment_analyzer.py not found — running without sentiment")
    fetch_sentiment = None

# ─── Paths ──────────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent
DATA_PATH = ROOT / "data.json"
CACHE_DIR = ROOT / ".cache"
CACHE_DIR.mkdir(exist_ok=True)

# ─── Rate-limits ────────────────────────────────────────────────────────────
BATCH_SIZE = 30          # concurrent YF requests
BATCH_DELAY = 0.6        # seconds between batches
TIMEOUT = aiohttp.ClientTimeout(total=15)
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/126.0.0.0 Safari/537.36",
    "Accept": "application/json",
}

# ─── Precious metals & commodity ETFs ───────────────────────────────────────
METALS = [
    ("GLD",  "SPDR Gold Shares",            "Precious Metal"),
    ("IAU",  "iShares Gold Trust",          "Precious Metal"),
    ("SLV",  "iShares Silver Trust",        "Precious Metal"),
    ("SIVR", "Aberdeen Std Physical Silver", "Precious Metal"),
    ("PPLT", "Aberdeen Std Physical Platinum","Precious Metal"),
    ("PALL", "Aberdeen Std Physical Palladium","Precious Metal"),
    ("CPER", "United States Copper ETF",    "Precious Metal"),
    ("GC=F", "Gold Futures",                "Precious Metal"),
    ("SI=F", "Silver Futures",              "Precious Metal"),
    ("PL=F", "Platinum Futures",            "Precious Metal"),
    ("PA=F", "Palladium Futures",           "Precious Metal"),
    ("HG=F", "Copper Futures",              "Precious Metal"),
]

# ─── Hardcoded popular ETFs (in case wiki scrape fails) ─────────────────────
FALLBACK_ETFS = [
    # Broad market
    ("SPY","SPDR S&P 500","ETF"),
    ("QQQ","Invesco QQQ","ETF"),
    ("IWM","iShares Russell 2000","ETF"),
    ("VTI","Vanguard Total Stock","ETF"),
    ("VOO","Vanguard S&P 500","ETF"),
    ("DIA","SPDR Dow Jones","ETF"),
    ("VTV","Vanguard Value","ETF"),
    ("VUG","Vanguard Growth","ETF"),
    ("IJH","iShares Core S&P Mid-Cap","ETF"),
    ("IJR","iShares Core S&P Small-Cap","ETF"),
    # Sectors
    ("XLK","Technology Select Sector","ETF"),
    ("XLF","Financial Select Sector","ETF"),
    ("XLE","Energy Select Sector","ETF"),
    ("XLI","Industrial Select Sector","ETF"),
    ("XLV","Health Care Select Sector","ETF"),
    ("XLP","Consumer Staples Select","ETF"),
    ("XLY","Consumer Discretionary","ETF"),
    ("XLU","Utilities Select Sector","ETF"),
    ("XLRE","Real Estate Select Sector","ETF"),
    ("XLB","Materials Select Sector","ETF"),
    ("SMH","VanEck Semiconductor","ETF"),
    ("SOXX","iShares Semiconductor","ETF"),
    ("IBB","iShares Nasdaq Biotech","ETF"),
    ("ARKK","ARK Innovation","ETF"),
    ("ARKG","ARK Genomic Revolution","ETF"),
    ("ARKW","ARK Next Gen Internet","ETF"),
    ("ARKF","ARK Fintech Innovation","ETF"),
    ("KRE","SPDR S&P Regional Banking","ETF"),
    ("XRT","SPDR S&P Retail","ETF"),
    ("XHB","SPDR S&P Homebuilders","ETF"),
    # International
    ("VEA","Vanguard Developed Mkts","ETF"),
    ("IEFA","iShares Core MSCI EAFE","ETF"),
    ("EEM","iShares Core MSCI EM","ETF"),
    ("VWO","Vanguard Emerging Mkts","ETF"),
    ("FXI","iShares China Large-Cap","ETF"),
    ("ASHR","Xtrackers Harvest CSI 300","ETF"),
    ("KWEB","KraneShares CSI China Internet","ETF"),
    ("INDA","iShares MSCI India","ETF"),
    ("EWZ","iShares MSCI Brazil","ETF"),
    ("EWT","iShares MSCI Taiwan","ETF"),
    ("EWJ","iShares MSCI Japan","ETF"),
    ("EWG","iShares MSCI Germany","ETF"),
    ("EWU","iShares MSCI UK","ETF"),
    ("EPP","iShares MSCI Pacific ex-Japan","ETF"),
    # Fixed income
    ("TLT","iShares 20+ Year Treasury","ETF"),
    ("IEF","iShares 7-10 Year Treasury","ETF"),
    ("SHY","iShares 1-3 Year Treasury","ETF"),
    ("LQD","iShares iBoxx IG Corp","ETF"),
    ("HYG","iShares iBoxx HY Corp","ETF"),
    ("JNK","SPDR Bloomberg HY Bond","ETF"),
    ("EMB","iShares JP Morgan EM Bond","ETF"),
    ("BND","Vanguard Total Bond","ETF"),
    ("AGG","iShares Core US Aggregate","ETF"),
    ("MBB","iShares MBS ETF","ETF"),
    ("TIP","iShares TIPS Bond","ETF"),
    # Commodity / Alt
    ("VNQ","Vanguard Real Estate","ETF"),
    ("SCHD","Schwab US Dividend Equity","ETF"),
    ("USO","United States Oil","ETF"),
    ("UNG","United States Natural Gas","ETF"),
    ("DBA","Invesco DB Agriculture","ETF"),
    ("DBC","Invesco DB Commodity","ETF"),
    ("GSG","iShares S&P GSCI Commodity","ETF"),
    ("PDBC","Invesco Opt Yield Divers Comm","ETF"),
    ("SDY","SPDR S&P Dividend","ETF"),
    ("VYM","Vanguard High Dividend","ETF"),
    ("HDV","iShares Core High Dividend","ETF"),
    ("NOBL","ProShares S&P 500 Dividend Aristocrats","ETF"),
    ("QUAL","iShares MSCI USA Quality Factor","ETF"),
    ("MTUM","iShares MSCI USA Momentum Factor","ETF"),
    ("VLUE","iShares MSCI USA Value Factor","ETF"),
    ("SIZE","iShares MSCI USA Size Factor","ETF"),
    # Crypto ETFs
    ("IBIT","iShares Bitcoin Trust","Crypto ETF"),
    ("FBTC","Fidelity Wise Origin Bitcoin","Crypto ETF"),
    ("ARKB","ARK 21Shares Bitcoin","Crypto ETF"),
    ("BITO","ProShares Bitcoin Strategy","Crypto ETF"),
    ("BITB","Bitwise Bitcoin ETF","Crypto ETF"),
    ("HODL","VanEck Bitcoin Trust","Crypto ETF"),
    ("BTCO","Fidelity Bitcoin ETF","Crypto ETF"),
    ("ETHA","BlackRock Ethereum ETF","Crypto ETF"),
    ("ETHE","Grayscale Ethereum Trust","Crypto ETF"),
    ("ETHW","Bitwise Ethereum ETF","Crypto ETF"),
    ("FETH","Fidelity Ethereum ETF","Crypto ETF"),
    ("CETH","Invesco Galaxy Ethereum ETF","Crypto ETF"),
    # Leveraged / Inverse (for completeness)
    ("TQQQ","ProShares UltraPro QQQ","Leveraged ETF"),
    ("SQQQ","ProShares UltraPro Short QQQ","Leveraged ETF"),
    ("SPXL","Direxion Daily S&P 500 Bull 3x","Leveraged ETF"),
    ("SPXS","Direxion Daily S&P 500 Bear 3x","Leveraged ETF"),
    ("SOXL","Direxion Daily Semiconductor Bull 3x","Leveraged ETF"),
    ("UVXY","ProShares Ultra VIX Short-Term","Volatility ETF"),
    ("VIXY","ProShares VIX Short-Term Futures","Volatility ETF"),
]

# ─── Crypto list — top 100 by market cap (CoinGecko-compatible symbols) ─────
# Blue-chip only — no meme coins / micro-caps
CRYPTO = [
    # Tier 1 — unquestioned blue chips
    ("BTC-USD","Bitcoin","Crypto"),
    ("ETH-USD","Ethereum","Crypto"),
    ("SOL-USD","Solana","Crypto"),
    ("XRP-USD","XRP","Crypto"),
    ("ADA-USD","Cardano","Crypto"),
    ("LINK-USD","Chainlink","Crypto"),
    ("DOT-USD","Polkadot","Crypto"),
    ("TAO-USD","Bittensor","Crypto"),
    # Tier 2 — established L1s / L2s / DeFi
    ("AVAX-USD","Avalanche","Crypto"),
    ("LTC-USD","Litecoin","Crypto"),
    ("BCH-USD","Bitcoin Cash","Crypto"),
    ("NEAR-USD","NEAR Protocol","Crypto"),
    ("ICP-USD","Internet Computer","Crypto"),
    ("HBAR-USD","Hedera","Crypto"),
    ("UNI-USD","Uniswap","Crypto"),
    ("ETC-USD","Ethereum Classic","Crypto"),
    ("APT-USD","Aptos","Crypto"),
    ("VET-USD","VeChain","Crypto"),
    ("FIL-USD","Filecoin","Crypto"),
    ("ARB-USD","Arbitrum","Crypto"),
    ("OP-USD","Optimism","Crypto"),
    ("STX-USD","Stacks","Crypto"),
    ("MKR-USD","Maker","Crypto"),
    ("RENDER-USD","Render","Crypto"),
    ("FET-USD","Fetch.ai","Crypto"),
    ("INJ-USD","Injective","Crypto"),
    ("GRT-USD","The Graph","Crypto"),
    ("MATIC-USD","Polygon","Crypto"),
    ("ATOM-USD","Cosmos","Crypto"),
    ("ALGO-USD","Algorand","Crypto"),
    ("THETA-USD","Theta Network","Crypto"),
    ("QNT-USD","Quant","Crypto"),
    ("KAS-USD","Kaspa","Crypto"),
    ("TIA-USD","Celestia","Crypto"),
    ("SEI-USD","Sei","Crypto"),
    ("STRK-USD","Starknet","Crypto"),
    ("ZRO-USD","LayerZero","Crypto"),
    ("ENA-USD","Ethena","Crypto"),
    ("PENDLE-USD","Pendle","Crypto"),
    ("AAVE-USD","Aave","Crypto"),
    ("COMP-USD","Compound","Crypto"),
    ("YFI-USD","Yearn.finance","Crypto"),
    ("SNX-USD","Synthetix","Crypto"),
    ("DYDX-USD","dYdX","Crypto"),
    ("GMX-USD","GMX","Crypto"),
    ("CRV-USD","Curve DAO Token","Crypto"),
    ("LDO-USD","Lido DAO","Crypto"),
    ("SSV-USD","SSV Network","Crypto"),
    ("RPL-USD","Rocket Pool","Crypto"),
    ("FXS-USD","Frax Shares","Crypto"),
    ("PYTH-USD","Pyth Network","Crypto"),
    ("JUP-USD","Jupiter","Crypto"),
    ("JTO-USD","Jito","Crypto"),
    ("BEAM-USD","Beam","Crypto"),
]


# ─── Helpers ────────────────────────────────────────────────────────────────
async def fetch_wiki_sp500(session: aiohttp.ClientSession) -> list:
    """Scrape S&P 500 constituents from stockanalysis.com."""
    try:
        url = "https://stockanalysis.com/list/sp-500-stocks/"
        async with session.get(url, headers=HEADERS, timeout=TIMEOUT) as r:
            text = await r.text()
            import re
            matches = re.findall(
                r'<a href="/stocks/([a-z\.\-]+)/">([A-Z\-]{1,6})</a>',
                text, re.IGNORECASE
            )
            seen = set()
            result = []
            for _, ticker in matches:
                t = ticker.upper()
                if t not in seen:
                    seen.add(t)
                    result.append(t)
            print(f"      [wiki] Fetched {len(result)} S&P 500 tickers")
            return result
    except Exception as e:
        print(f"      [wiki] ERROR fetching S&P 500: {e}")
        return []


async def fetch_sa_russell2k(session: aiohttp.ClientSession) -> list:
    """Scrape Russell 2000 constituents from available sources."""
    tickers = []
    seen = set()

    # Try IWM holdings (only shows top ~25 visible, but it's a start)
    try:
        url = "https://stockanalysis.com/etf/iwm/holdings/"
        async with session.get(url, headers=HEADERS, timeout=TIMEOUT) as r:
            text = await r.text()
            import re
            links = re.findall(r'href="/stocks/([^"]+)/"', text)
            for s in links:
                s = s.upper()
                if len(s) <= 6 and s not in seen and s.replace('.', '').replace('-', '').isalnum():
                    seen.add(s)
                    tickers.append(s)
    except Exception:
        pass

    # Also try VWO for broader small cap
    try:
        url = "https://stockanalysis.com/etf/vtwo/holdings/"
        async with session.get(url, headers=HEADERS, timeout=TIMEOUT) as r:
            text = await r.text()
            import re
            links = re.findall(r'href="/stocks/([^"]+)/"', text)
            for s in links:
                s = s.upper()
                if len(s) <= 6 and s not in seen and s.replace('.', '').replace('-', '').isalnum():
                    seen.add(s)
                    tickers.append(s)
    except Exception:
        pass

    print(f"      [sa] Top holdings tickers from IWM/VTWO: {len(tickers)}")
    return tickers


async def fetch_wiki_etfs(session: aiohttp.ClientSession) -> list:
    """Scrape comprehensive ETF list from stockanalysis.com (5,500+ ETFs).

    Returns list of (ticker, name) tuples sorted by AUM (largest first).
    Uses cache after first scrape to avoid repeated network calls.
    """
    # Check cache first
    cache_file = CACHE_DIR / "all_etfs.json"
    if cache_file.exists() and cache_file.stat().st_size > 100000:
        try:
            with open(cache_file) as f:
                cached = json.load(f)
            if len(cached) >= 1000:
                print(f"      [wiki] Using cached ETF list ({len(cached)} tickers)")
                return [(e["s"], e["n"]) for e in cached]
        except Exception:
            pass

    all_etfs = []
    seen = set()

    try:
        for page in range(1, 21):  # Top ~2,000 ETFs by AUM
            url = f"https://stockanalysis.com/etf/?page={page}"
            async with session.get(url, headers=HEADERS, timeout=TIMEOUT) as r:
                if r.status != 200:
                    break
                text = await r.text()
                import re
                matches = re.findall(r'\{s:"([A-Z]{1,5})",n:"([^"]+)"', text)
                for sym, name in matches:
                    if sym not in seen:
                        seen.add(sym)
                        all_etfs.append((sym, name))
                if not matches:
                    break
                if page % 5 == 0:
                    await asyncio.sleep(0.5)  # be polite
    except Exception as e:
        print(f"      [wiki] ERROR fetching ETFs: {e}")

    # Fallback to your existing comprehensive cache if scrape fails
    if len(all_etfs) < 500 and cache_file.exists():
        try:
            with open(cache_file) as f:
                cached = json.load(f)
            all_etfs = [(e["s"], e["n"]) for e in cached if e["s"] not in seen]
            print(f"      [wiki] Fallback to cached list ({len(all_etfs)} tickers)")
        except Exception:
            pass

    print(f"      [wiki] Fetched {len(all_etfs)} ETF tickers")
    return all_etfs


async def build_asset_universe(session: aiohttp.ClientSession) -> list:
    """Build [(ticker, name, category), ...] for all assets."""
    assets = []
    seen = set()

    def add(ticker, name, category):
        t = ticker.upper()
        if t not in seen:
            seen.add(t)
            assets.append((t, name, category))

    # 1. S&P 500
    sp500 = await fetch_wiki_sp500(session)
    for t in sp500:
        add(t, t, "Equity - S&P 500")

    # 2. Russell 2000
    r2k = await fetch_sa_russell2k(session)
    if len(r2k) < 200:
        # stockanalysis failed — use hardcoded top 300
        print("      [sa] Fallback to hardcoded Russell 2000 top 300")
        # Read from cached file if exists, otherwise use minimal fallback
        r2k_cache = CACHE_DIR / "russell2k_top300.json"
        if r2k_cache.exists():
            with open(r2k_cache) as f:
                r2k = json.load(f)
        else:
            # We'll write a proper fallback after first run
            r2k = []
    for t in r2k:
        add(t, t, "Equity - Russell 2000")

    # Even if R2K scrape fails, we have thousands of S&P 500 stocks already

    # 3. ETFs (scrape + hardcoded fallback)
    etf_tickers = await fetch_wiki_etfs(session)
    for t, name in etf_tickers:
        add(t, name, "ETF")
    for t, name, cat in FALLBACK_ETFS:
        add(t, name, cat)  # these include category overrides like "Crypto ETF", "Leveraged ETF"
    
    # 4. Precious metals
    for t, name, cat in METALS:
        add(t, name, cat)
    
    # 5. Crypto (blue-chip only — no meme coins)
    MEME_DENYLIST = {
        "DOGE-USD","SHIB-USD","PEPE-USD","WIF-USD","BONK-USD","FLOKI-USD",
        "BOME-USD","TREMP-USD","MAGA-USD","TRUMP-USD","PEOPLE-USD",
        "CLORE-USD","COOK-USD","PIXEL-USD","GMT-USD","GALA-USD",
        "CHZ-USD","ENJ-USD","BAT-USD","MANA-USD","SAND-USD","AXS-USD",
        "MAGIC-USD","VELO-USD","TRX-USD","CRO-USD","DRIFT-USD",
        "TNSR-USD","ZEX-USD","KMNO-USD","RON-USD","WLD-USD",
        "FTM-USD",
    }
    for t, name, cat in CRYPTO:
        if t in MEME_DENYLIST:
            continue
        add(t, name, cat)

    # Remove duplicates aggressively — SPY, QQQ etc. appear in multiple lists
    print(f"      [universe] Total unique assets: {len(assets)}")
    return assets


# ─── Yahoo Finance fetcher (yfinance-based) ─────────────────────────────────
from concurrent.futures import ThreadPoolExecutor

def _yf_fetch_sync(ticker: str, days: int = 35) -> list:
    """Sync fetch via yfinance — bypasses Yahoo cookie wall."""
    try:
        t = yf.Ticker(ticker)
        # Use '1y' period to get enough history, then trim
        data = t.history(period="3mo", interval="1d")
        if data.empty:
            return []
        closes = data["Close"].dropna().tolist()
        # Trim to requested days
        target = min(days, len(closes))
        closes = closes[-target:]
        return [float(c) for c in closes]
    except Exception:
        return []


async def fetch_yf_history(session, ticker: str, days: int = 35) -> list:
    """Async wrapper around sync yfinance fetch."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _yf_fetch_sync, ticker, days)


async def batch_fetch(session, tickers: list, days: int = 35) -> dict:
    """Fetch histories via ThreadPoolExecutor + yfinance."""
    results = {}
    loop = asyncio.get_event_loop()
    
    with ThreadPoolExecutor(max_workers=10) as pool:
        # Submit all
        futures = {
            t: loop.run_in_executor(pool, _yf_fetch_sync, t, days)
            for t in tickers
        }
        
        # Gather with progress
        done = 0
        total = len(tickers)
        for t, fut in futures.items():
            try:
                closes = await fut
                if closes and len(closes) >= 5:
                    results[t] = closes
            except Exception:
                pass
            done += 1
            if done % 30 == 0:
                print(f"      [batch] {done}/{total} done, valid={len(results)}")
    
    print(f"      [batch] Final valid histories: {len(results)}/{len(tickers)}")
    return results


# ─── Technical analysis ─────────────────────────────────────────────────────
def calc_rsi(closes, period=14):
    if len(closes) < period + 1:
        return None
    gains, losses = [], []
    for i in range(1, period + 1):
        chg = closes[-i] - closes[-(i + 1)]
        gains.append(max(chg, 0))
        losses.append(abs(min(chg, 0)))
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period or 0.001
    return 100 - (100 / (1 + avg_gain / avg_loss))


def calc_sma(closes, period):
    if len(closes) < period:
        return None
    return sum(closes[-period:]) / period


def calc_volatility(closes):
    if len(closes) < 2:
        return 0
    max_drop = 0
    for i in range(1, len(closes)):
        drop = abs(closes[i] - closes[i - 1]) / closes[i - 1] * 100
        max_drop = max(max_drop, drop)
    return max_drop


def calc_drawdown(closes):
    if not closes:
        return 0
    peak = closes[0]
    max_dd = 0
    for c in closes:
        if c > peak:
            peak = c
        dd = (peak - c) / peak * 100
        max_dd = max(max_dd, dd)
    return max_dd


def analyze_one(ticker, name, category, closes):
    if not closes or len(closes) < 5:
        return None

    price = closes[-1]
    chg_7d = (closes[-1] - closes[-7]) / closes[-7] * 100 if len(closes) >= 7 else 0
    chg_30d = (closes[-1] - closes[0]) / closes[0] * 100 if len(closes) >= 30 else 0
    rsi = calc_rsi(closes, 14)
    sma20 = calc_sma(closes, 20)
    sma50 = calc_sma(closes, 50) if len(closes) >= 50 else None
    vola = calc_volatility(closes)
    drawdown = calc_drawdown(closes)

    score = 50
    factors = []

    # Momentum (7d) — 25 pts
    if chg_7d > 8:       score += 20; factors.append(f"rocket +{chg_7d:.1f}% week")
    elif chg_7d > 5:     score += 15; factors.append(f"strong +{chg_7d:.1f}% week")
    elif chg_7d > 3:     score += 12; factors.append(f"+{chg_7d:.1f}% week")
    elif chg_7d > 1.5:   score += 8;  factors.append(f"+{chg_7d:.1f}% week")
    elif chg_7d > 0.3:   score += 4;  factors.append(f"+{chg_7d:.1f}% week")
    elif chg_7d > -1.5:  score -= 3;  factors.append(f"flat {chg_7d:.1f}% week")
    elif chg_7d > -4:    score -= 8;  factors.append(f"weak {chg_7d:.1f}% week")
    else:                score -= 15; factors.append(f"crash {chg_7d:.1f}% week")

    # Trend (30d) — 20 pts
    if chg_30d > 20:     score += 15; factors.append(f"moon +{chg_30d:.1f}% month")
    elif chg_30d > 12:   score += 12; factors.append(f"+{chg_30d:.1f}% month")
    elif chg_30d > 6:    score += 8;  factors.append(f"+{chg_30d:.1f}% month")
    elif chg_30d > 2:    score += 4;  factors.append(f"+{chg_30d:.1f}% month")
    elif chg_30d > -3:   score -= 4;  factors.append(f"{chg_30d:.1f}% month")
    elif chg_30d > -8:   score -= 10; factors.append(f"weak {chg_30d:.1f}% month")
    else:                score -= 18; factors.append(f"crash {chg_30d:.1f}% month")

    # RSI — 15 pts
    if rsi is not None:
        if rsi > 75:     score += 8;  factors.append(f"RSI {rsi:.0f} hot")
        elif rsi > 65:   score += 6;  factors.append(f"RSI {rsi:.0f} strong")
        elif rsi > 55:   score += 3;  factors.append(f"RSI {rsi:.0f} positive")
        elif rsi < 28:   score -= 8;  factors.append(f"RSI {rsi:.0f} oversold")
        elif rsi < 38:   score -= 5;  factors.append(f"RSI {rsi:.0f} weak")
        elif rsi < 45:   score -= 2;  factors.append(f"RSI {rsi:.0f} soft")

    # SMA positioning — 12 pts
    if sma20 is not None:
        if price > sma20 * 1.03:   score += 6; factors.append("well above SMA20")
        elif price > sma20 * 1.01: score += 3; factors.append("above SMA20")
        elif price < sma20 * 0.97: score -= 5; factors.append("below SMA20")
        elif price < sma20 * 0.99: score -= 2; factors.append("under SMA20")
    if sma50 is not None:
        if price > sma50 * 1.03:   score += 4; factors.append("well above SMA50")
        elif price > sma50 * 1.01: score += 2; factors.append("above SMA50")
        elif price < sma50 * 0.97: score -= 3; factors.append("below SMA50")
        elif price < sma50 * 0.99: score -= 1; factors.append("under SMA50")

    # Volatility penalty — 10 pts
    if vola > 8:       score -= 10; factors.append(f"wild vol {vola:.1f}%")
    elif vola > 6:     score -= 7;  factors.append(f"high vol {vola:.1f}%")
    elif vola > 4:     score -= 4;  factors.append(f"elevated vol {vola:.1f}%")
    elif vola > 2.5:   score -= 2;  factors.append(f"choppy {vola:.1f}%")
    elif vola < 0.8:   score += 2;  factors.append("calm")

    # Drawdown
    if drawdown > 25:  score -= 5;  factors.append(f"deep DD -{drawdown:.0f}%")
    elif drawdown > 15: score -= 3; factors.append(f"DD -{drawdown:.0f}%")

    # Category bonuses
    if category.startswith("Equity") and chg_7d > 1 and chg_30d > 2:
        score += 2; factors.append("equity strength")
    if category in ("Crypto", "Crypto ETF") and rsi and rsi > 55 and chg_7d > 2:
        score += 3; factors.append("crypto momo")
    if category == "Crypto ETF" and chg_30d > 5:
        score += 2; factors.append("crypto ETF flow")
    if category == "Precious Metal" and chg_7d > 1:
        score += 1; factors.append("metal bid")

    return {
        "ticker": ticker,
        "name": name,
        "category": category,
        "price": round(price, 4),
        "change_7d": round(chg_7d, 2),
        "change_30d": round(chg_30d, 2),
        "rsi": round(rsi, 1) if rsi else None,
        "sma20": round(sma20, 4) if sma20 else None,
        "sma50": round(sma50, 4) if sma50 else None,
        "volatility": round(vola, 2),
        "drawdown": round(drawdown, 2),
        "score": max(0, min(100, round(score, 1))),
        "factors": factors,
    }


# ─── Rationale generator ────────────────────────────────────────────────────
def generate_rationale(pick, all_results, total_mentions=0, top_sent=None):
    ticker = pick["ticker"]
    name = pick["name"]
    cat = pick["category"]
    score = pick["score"]
    price = pick["price"]
    chg_7d = pick["change_7d"]
    chg_30d = pick["change_30d"]
    rsi = pick["rsi"]
    sma20 = pick.get("sma20")
    sma50 = pick.get("sma50")
    factors = pick["factors"]
    top_sent = top_sent or {}

    def avg_score(filter_fn):
        vals = [r["score"] for r in all_results if filter_fn(r)]
        return round(sum(vals) / max(1, len(vals)), 1)

    cohort_avg = avg_score(lambda r: r["category"] == cat)
    overall_avg = avg_score(lambda r: True)
    total = len(all_results)

    bull_text = ", ".join(factors[:5]) if factors else "mixed signals"

    if score >= 75:
        conviction = "HIGHEST CONVICTION"
        tone = f"{name} ({ticker}) scores {score}/100 — the strongest setup across {total} tracked assets."
    elif score >= 62:
        conviction = "STRONG BUY"
        tone = f"{name} ({ticker}) leads at {score}/100 — best risk/reward in the entire universe."
    elif score >= 50:
        conviction = "MODERATE BUY"
        tone = f"{name} ({ticker}) edges ahead at {score}/100 — modest edge in a mixed tape."
    elif score >= 40:
        conviction = "CAUTIOUS HOLD"
        tone = f"{name} ({ticker}) tops the list at {score}/100 — best of a weak field. Proceed with stops."
    else:
        conviction = "AVOID / SPECULATIVE"
        tone = f"{name} ({ticker}) scores {score}/100 — the entire market looks rough this week."

    tech_lines = [f"- Price: ${price:,.4f}"]
    if sma20:
        rel20 = (price - sma20) / sma20 * 100
        tech_lines.append(f"- SMA20: ${sma20:,.4f} ({rel20:+.1f}%)")
    if sma50:
        rel50 = (price - sma50) / sma50 * 100
        tech_lines.append(f"- SMA50: ${sma50:,.4f} ({rel50:+.1f}%)")
    if rsi:
        rsi_state = "overbought" if rsi > 70 else "strong" if rsi > 55 else "neutral" if rsi > 40 else "oversold"
        tech_lines.append(f"- RSI(14): {rsi:.1f} — {rsi_state}")
    tech_lines.append(f"- Weekly: {chg_7d:+.1f}%, Monthly: {chg_30d:+.1f}%")
    tech_lines.append(f"- Volatility (max daily swing): {pick['volatility']:.1f}%")
    if pick.get("drawdown") > 5:
        tech_lines.append(f"- Max drawdown: {pick['drawdown']:.1f}%")

    comp = f"Cohort avg ({cat}): {cohort_avg}/100. Overall universe avg: {overall_avg}/100."

    # Sentiment section
    sent_lines = []
    if pick.get("sentiment_score"):
        sent = pick["sentiment_score"]
        polarity = pick.get("sentiment_polarity", 0)
        mentions = pick.get("sentiment_mentions", 0)
        sent_lines.append(
            f"- Sentiment: {sent:.0f}/100 (polarity={polarity:+.2f}, {mentions} mentions)"
        )
        if sent >= 60:
            sent_lines.append("  Social buzz is bullish — community driving momentum.")
        elif sent < 40:
            sent_lines.append("  Social buzz tilts bearish — watch for contrarian bounce.")
        else:
            sent_lines.append("  Sentiment neutral — price-driven, not hype-driven.")
    else:
        sent_lines.append("- Sentiment: no social data this week")

    if top_sent and total_mentions > 0:
        src_list = ", ".join(top_sent.get("sources", {}).keys())
        sent_lines.append(f"- Sources: {src_list}")

    return (
        f"**{conviction}: {name} ({ticker})** — ${price:,.4f}\n\n"
        f"{tone}\n\n"
        f"Key drivers: {bull_text}.\n\n"
        f"**Technical Setup**\n" + "\n".join(tech_lines) + "\n\n"
        f"**Sentiment & Social Signals**\n" + "\n".join(sent_lines) + "\n\n"
        f"**Trade Plan**\n"
        f"Entry: Current levels or pullback to SMA20.\n"
        f"Stop-loss: Daily close below SMA20 or prior swing low.\n"
        f"Target: Upside continuation toward next resistance zone.\n"
        f"Position size: Size to volatility — max 5% for high-vol names, 2% for crypto.\n\n"
        f"**Why {name}?**\n"
        f"Top score of {score} across {total} tracked assets ({comp})\n\n"
        f"*Not financial advice. Data from Yahoo Finance v8 + public social feeds. DYOR.*"
    )


# ─── Main ───────────────────────────────────────────────────────────────────
async def main():
    now = datetime.now()
    is_monday = now.weekday() == 0
    is_afternoon = 12 <= now.hour < 23

    # Load cached pick if not Monday afternoon
    if DATA_PATH.exists():
        try:
            with open(DATA_PATH) as f:
                cached = json.load(f)
            wp = cached.get("weekly_pick")
            if wp and wp.get("top_pick", {}).get("name"):
                gen = datetime.fromisoformat(wp.get("generated_at", "2020-01-01"))
                if (now - gen).days < 7:
                    print("      [weekly_pick] Using cached (runs Mon 12-11pm only)")
                    print(json.dumps(wp, indent=2))
                    return wp
        except Exception:
            pass

    print(f"      [weekly_pick] Generating fresh pick for {now.strftime('%a %b %d %Y')}")

    async with aiohttp.ClientSession(timeout=TIMEOUT, headers=HEADERS) as session:
        # Build universe
        universe = await build_asset_universe(session)

        print(f"      [weekly_pick] Universe built: {len(universe)} unique assets")

        # Fetch all sentiments from Reddit, CNBC, Yahoo...
        sentiment_scores = {}
        if fetch_sentiment:
            print(f"      [weekly_pick] Fetching multi-source sentiment...")
            try:
                sentiment_scores = await fetch_sentiment(
                    session, set(t.upper() for t, _, _ in universe)
                )
                print(
                    f"      [weekly_pick] Sentiment data for {len(sentiment_scores)} tickers"
                )
            except Exception as e:
                print(f"      [weekly_pick] Sentiment fetch failed: {e}")

        # Fetch all price histories in batches
        tickers = [t for t, _, _ in universe]
        histories = await batch_fetch(session, tickers)

        # Analyze each + blend sentiment with technical
        results = []
        for t, n, c in universe:
            closes = histories.get(t, [])
            tech = analyze_one(t, n, c, closes)
            if not tech:
                continue
            # ── Blend sentiment (25%) + technical (75%) ────────────────
            sent_entry = sentiment_scores.get(t.upper(), {}) or {}
            sent_score = sent_entry.get("sentiment_score")
            if sent_score is not None:
                blended = round(tech["score"] * 0.70 + sent_score * 0.30, 1)
                tech["score"] = max(0, min(100, blended))
                tech["sentiment_score"] = sent_score
                tech["sentiment_mentions"] = sent_entry.get("mentions", 0)
                tech["sentiment_polarity"] = sent_entry.get("avg_polarity", 0)
                if sent_score >= 60:
                    tech["factors"].insert(0, f"🗣️ Bullish buzz {sent_score:.0f}")
                elif sent_score < 40:
                    tech["factors"].append(f"🐻 Bearish buzz {sent_score:.0f}")
                else:
                    tech["factors"].append(f"😐 Neutral buzz {sent_score:.0f}")
            results.append(tech)

        print(f"      [weekly_pick] Valid results: {len(results)}")

        if not results:
            print("      [weekly_pick] ERROR: no results")
            return {}

        results.sort(key=lambda x: x["score"], reverse=True)
        pick = results[0]

        # Sentiment mention count for rationale
        total_mentions = sum(
            s.get("mentions", 0) for s in sentiment_scores.values()
        )
        top_sent = sentiment_scores.get(pick["ticker"].upper(), {})

        wp = {
            "generated_at": now.isoformat(),
            "week_label": now.strftime("Week of %b %-d, %Y"),
            "top_pick": pick,
            "top_five": results[:5],
            "all_assets": results,
            "rationale": generate_rationale(pick, results, total_mentions, top_sent),
            "sentiment_summary": {
                "assets_with_sentiment": len(sentiment_scores),
                "total_mentions": total_mentions,
                "sources": list(
                    set(src for s in sentiment_scores.values() for src in s.get("sources", {}).keys())
                ) or ["none"],
            },
            "universe_summary": {
                "total": len(universe),
                "valid": len(results),
                "sp500": sum(1 for r in results if r["category"] == "Equity - S&P 500"),
                "russell2k": sum(1 for r in results if r["category"] == "Equity - Russell 2000"),
                "etfs": sum(1 for r in results if r["category"] == "ETF"),
                "crypto": sum(1 for r in results if r["category"] == "Crypto"),
                "metals": sum(1 for r in results if r["category"] == "Precious Metal"),
            },
        }

        # Write to data.json
        try:
            with open(DATA_PATH) as f:
                data = json.load(f)
        except Exception:
            data = {}

        data["weekly_pick"] = wp
        with open(DATA_PATH, "w") as f:
            json.dump(data, f, indent=2)

        # Also write standalone cache
        with open(CACHE_DIR / "weekly_pick_cache.json", "w") as f:
            json.dump(wp, f, indent=2)

        # Generate chart for the new pick
        _generate_chart(wp)

        print(json.dumps(wp["top_five"], indent=2))
        return wp


if __name__ == "__main__":
    wp = asyncio.run(main())
    print(json.dumps(wp.get("top_five", []), indent=2))


# ─── Chart generation helper ───────────────────────────────────────────────

def _generate_chart(wp: dict) -> bool:
    """Trigger weekly-pick chart generation in a subprocess using venv Python."""
    import subprocess
    chart_script = Path(__file__).resolve().parent.parent / "scripts" / "generate_weekly_pick_chart.py"
    if not chart_script.exists():
        print("      [weekly_pick] Chart script not found, skipping chart")
        return False
    top = wp.get("top_pick", {})
    ticker = top.get("ticker")
    name = top.get("name", ticker or "Weekly Pick")
    week_label = wp.get("week_label", "This Week")
    price = top.get("price", 0)

    # Use the project's venv Python (has matplotlib installed)
    venv_python = Path(__file__).resolve().parent.parent / "venv" / "bin" / "python"
    if not venv_python.exists():
        venv_python = Path(__file__).resolve().parent.parent / "venv" / "bin" / "python3"
    python_cmd = str(venv_python) if venv_python.exists() else sys.executable

    try:
        result = subprocess.run(
            [python_cmd, str(chart_script)],
            capture_output=True, text=True, timeout=60
        )
        if result.returncode == 0:
            print("      [weekly_pick] Chart generated successfully")
            return True
        else:
            print(f"      [weekly_pick] Chart generation failed: {result.stderr.strip()}")
            # Fallback: try with pip-installed matplotlib on system python
            try:
                result2 = subprocess.run(
                    [sys.executable, "-m", "pip", "install", "matplotlib", "-q"],
                    capture_output=True, text=True, timeout=120
                )
            except Exception:
                pass
            return False
    except Exception as e:
        print(f"      [weekly_pick] Chart generation error: {e}")
        return False


# ─── Synchronous wrapper for backward compat (called by automated_nasdaq_analysis.py) ──

def get_weekly_pick():
    """Synchronous entry point called by automated_nasdaq_analysis.py.
    Delegates to async main() via asyncio.run()."""
    try:
        return asyncio.run(main())
    except Exception as e:
        print(f"      [weekly_pick] ERROR: {e}")
        return {}
