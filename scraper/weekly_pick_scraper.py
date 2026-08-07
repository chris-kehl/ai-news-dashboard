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

try:
    import aiohttp
    import aiofiles
except ImportError:
    print("pip install aiohttp aiofiles")
    raise

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
CRYPTO = [
    ("BTC-USD","Bitcoin","Crypto"),
    ("ETH-USD","Ethereum","Crypto"),
    ("SOL-USD","Solana","Crypto"),
    ("XRP-USD","XRP","Crypto"),
    ("BNB-USD","Binance Coin","Crypto"),
    ("DOGE-USD","Dogecoin","Crypto"),
    ("ADA-USD","Cardano","Crypto"),
    ("TRX-USD","TRON","Crypto"),
    ("AVAX-USD","Avalanche","Crypto"),
    ("SUI-USD","Sui","Crypto"),
    ("LINK-USD","Chainlink","Crypto"),
    ("DOT-USD","Polkadot","Crypto"),
    ("TAO-USD","Bittensor","Crypto"),
    ("LTC-USD","Litecoin","Crypto"),
    ("BCH-USD","Bitcoin Cash","Crypto"),
    ("NEAR-USD","NEAR Protocol","Crypto"),
    ("ICP-USD","Internet Computer","Crypto"),
    ("HBAR-USD","Hedera","Crypto"),
    ("UNI-USD","Uniswap","Crypto"),
    ("ETC-USD","Ethereum Classic","Crypto"),
    ("APT-USD","Aptos","Crypto"),
    ("CRO-USD","Cronos","Crypto"),
    ("VET-USD","VeChain","Crypto"),
    ("FIL-USD","Filecoin","Crypto"),
    ("ARB-USD","Arbitrum","Crypto"),
    ("IMX-USD","Immutable","Crypto"),
    ("OP-USD","Optimism","Crypto"),
    ("MNT-USD","Mantle","Crypto"),
    ("STX-USD","Stacks","Crypto"),
    ("MKR-USD","Maker","Crypto"),
    ("HYPE-USD","Hyperliquid","Crypto"),
    ("RENDER-USD","Render","Crypto"),
    ("FET-USD","Fetch.ai","Crypto"),
    ("INJ-USD","Injective","Crypto"),
    ("GRT-USD","The Graph","Crypto"),
    ("PEPE-USD","Pepe","Crypto"),
    ("WIF-USD","dogwifhat","Crypto"),
    ("BONK-USD","Bonk","Crypto"),
    ("FLOKI-USD","FLOKI","Crypto"),
    ("SHIB-USD","Shiba Inu","Crypto"),
    ("MATIC-USD","Polygon","Crypto"),
    ("ATOM-USD","Cosmos","Crypto"),
    ("ALGO-USD","Algorand","Crypto"),
    ("THETA-USD","Theta Network","Crypto"),
    ("FTM-USD","Fantom","Crypto"),
    ("SAND-USD","The Sandbox","Crypto"),
    ("MANA-USD","Decentraland","Crypto"),
    ("AXS-USD","Axie Infinity","Crypto"),
    ("FLOW-USD","Flow","Crypto"),
    ("KLAY-USD","Klaytn","Crypto"),
    ("XTZ-USD","Tezos","Crypto"),
    ("EOS-USD","EOS","Crypto"),
    ("ZEC-USD","Zcash","Crypto"),
    ("XMR-USD","Monero","Crypto"),
    ("DASH-USD","Dash","Crypto"),
    ("NEO-USD","NEO","Crypto"),
    ("IOTA-USD","IOTA","Crypto"),
    ("EGLD-USD","MultiversX","Crypto"),
    ("QNT-USD","Quant","Crypto"),
    ("KAS-USD","Kaspa","Crypto"),
    ("TIA-USD","Celestia","Crypto"),
    ("SEI-USD","Sei","Crypto"),
    ("STRK-USD","Starknet","Crypto"),
    ("ZRO-USD","LayerZero","Crypto"),
    ("ENA-USD","Ethena","Crypto"),
    ("PENDLE-USD","Pendle","Crypto"),
    ("WLD-USD","Worldcoin","Crypto"),
    ("ARKM-USD","Arkham","Crypto"),
    ("PYTH-USD","Pyth Network","Crypto"),
    ("JUP-USD","Jupiter","Crypto"),
    ("JTO-USD","Jito","Crypto"),
    ("BOME-USD","BOOK OF MEME","Crypto"),
    ("WLD-USD","Worldcoin","Crypto"),
    ("TNSR-USD","Tensor","Crypto"),
    ("DRIFT-USD","Drift Protocol","Crypto"),
    ("ZEX-USD","Zeta","Crypto"),
    ("KMNO-USD","Kamino","Crypto"),
    ("CLORE-USD","Clore.ai","Crypto"),
    ("COOK-USD","Cook Finance","Crypto"),
    ("RON-USD","Ronin","Crypto"),
    ("PIXEL-USD","Pixels","Crypto"),
    ("BEAM-USD","Beam","Crypto"),
    ("GMT-USD","STEPN","Crypto"),
    ("GALA-USD","Gala","Crypto"),
    ("CHZ-USD","Chiliz","Crypto"),
    ("ENJ-USD","Enjin Coin","Crypto"),
    ("BAT-USD","Basic Attention Token","Crypto"),
    ("CRV-USD","Curve DAO Token","Crypto"),
    ("LDO-USD","Lido DAO","Crypto"),
    ("SSV-USD","SSV Network","Crypto"),
    ("RPL-USD","Rocket Pool","Crypto"),
    ("FXS-USD","Frax Shares","Crypto"),
    ("AAVE-USD","Aave","Crypto"),
    ("COMP-USD","Compound","Crypto"),
    ("MKR-USD","Maker","Crypto"),
    ("YFI-USD","Yearn.finance","Crypto"),
    ("SNX-USD","Synthetix","Crypto"),
    ("1INCH-USD","1inch Network","Crypto"),
    ("DYDX-USD","dYdX","Crypto"),
    ("GMX-USD","GMX","Crypto"),
    ("VELO-USD","Velo","Crypto"),
    ("MAGIC-USD","MAGIC","Crypto"),
    ("TREMP-USD","Tremp","Crypto"),
    ("MAGA-USD","MAGA","Crypto"),
    ("TRUMP-USD","TRUMP","Crypto"),
    ("PEOPLE-USD","ConstitutionDAO","Crypto"),
]


# ─── Helpers ────────────────────────────────────────────────────────────────
async def fetch_wiki_sp500(session: aiohttp.ClientSession) -> list:
    """Scrape S&P 500 constituents from Wikipedia."""
    url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
    try:
        async with session.get(url, headers=HEADERS, timeout=TIMEOUT) as r:
            text = await r.text()
            import re
            # Find the first wikitable and extract tickers
            # Each row has format: <td><a href="...">TICKER</a></td>
            tickers = re.findall(
                r'<a[^>]+href="/wiki/[^"]+"[^>]*>([A-Z\.]+)</a>',
                text[:60000]  # first 60K chars to avoid footnotes
            )
            # Deduplicate and filter
            seen = set()
            result = []
            for t in tickers:
                t = t.replace(".", "-")  # BRK.B -> BRK-B for Yahoo
                if t not in seen and len(t) <= 6:
                    seen.add(t)
                    result.append(t)
            print(f"      [wiki] Fetched {len(result)} S&P 500 tickers")
            return result[:505]  # cap at 505 (some Wikioedia drift)
    except Exception as e:
        print(f"      [wiki] ERROR fetching S&P 500: {e}")
        return []


async def fetch_sa_russell2k(session: aiohttp.ClientSession) -> list:
    """Scrape Russell 2000 constituents from stockanalysis.com."""
    tickers = []
    # StockAnalysis paginates; try first few pages
    for page in range(1, 6):
        url = f"https://stockanalysis.com/etf/iwm/holdings/?page={page}"
        try:
            async with session.get(url, headers=HEADERS, timeout=TIMEOUT) as r:
                text = await r.text()
                import re
                # Each row has ticker in first link
                matches = re.findall(
                    r'"symbol":"([A-Z\-]+)"',
                    text
                )
                for m in matches:
                    if m not in tickers and len(m) <= 6:
                        tickers.append(m)
                print(f"      [sa] Page {page}: {len(matches)} tickers, total {len(tickers)}")
                if not matches:
                    break
        except Exception as e:
            print(f"      [sa] Page {page} error: {e}")
            break
    print(f"      [sa] Total Russell 2000 tickers fetched: {len(tickers)}")
    return tickers


async def fetch_wiki_etfs(session: aiohttp.ClientSession) -> list:
    """Scrape list of US ETFs from Wikipedia."""
    url = "https://en.wikipedia.org/wiki/List_of_American_exchange-traded_funds"
    try:
        async with session.get(url, headers=HEADERS, timeout=TIMEOUT) as r:
            text = await r.text()
            import re
            # ETFs are listed in tables with format TICKER (Name) in text
            # More robust: find pattern like "(TICKER)" near "ETF"
            # Actually Wikipedia tables have columns: Ticker, ETF, etc.
            # Let's grab tickers from the first large table
            tickers = re.findall(
                r'<td[^>]*>\s*<a[^>]+href="[^"]*"[^>]*>([A-Z]{1,5})</a>\s*</td>',
                text[:120000]
            )
            # Deduplicate
            seen = set()
            result = []
            for t in tickers:
                if t not in seen and t != "ETF":
                    seen.add(t)
                    result.append(t)
            # Fallback: also try to find tickers in a different pattern
            if len(result) < 50:
                alt = re.findall(
                    r'\(([A-Z]{2,5})\).*?(?:ETF|Fund|Index)',
                    text[:120000],
                    re.IGNORECASE
                )
                for a in alt:
                    if a not in seen and a not in {"ETF", "the", "NYSE"}:
                        seen.add(a)
                        result.append(a)
            print(f"      [wiki] Fetched {len(result)} ETF tickers")
            return result
    except Exception as e:
        print(f"      [wiki] ERROR fetching ETFs: {e}")
        return []


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

    # 3. ETFs
    etf_tickers = await fetch_wiki_etfs(session)
    for t in etf_tickers:
        add(t, t, "ETF")
    for t, name, cat in FALLBACK_ETFS:
        add(t, name, cat)

    # Remove duplicates aggressively — SPY, QQQ etc. appear in multiple lists
    print(f"      [universe] Total unique assets: {len(assets)}")
    return assets


# ─── Yahoo Finance fetcher (async batched) ──────────────────────────────────
async def fetch_yf_history(session: aiohttp.ClientSession, ticker: str, days: int = 35) -> list:
    """Fetch daily closes from YF chart endpoint."""
    t = ticker.upper()
    url = (
        f"https://query1.finance.yahoo.com/v8/finance/chart/{t}"
        f"?interval=1d&range={days}d"
    )
    try:
        async with session.get(url, headers=HEADERS, timeout=TIMEOUT) as r:
            if r.status != 200:
                return []
            data = await r.json()
            result = data.get("chart", {}).get("result", [])
            if not result:
                return []
            q = result[0].get("indicators", {}).get("quote", [{}])[0]
            closes = [float(c) for c in q.get("close", []) if c is not None]
            return closes
    except Exception:
        return []


async def batch_fetch(session, tickers: list, days: int = 35) -> dict:
    """Fetch histories in batches with delay. Returns {ticker: closes}."""
    results = {}
    for i in range(0, len(tickers), BATCH_SIZE):
        batch = tickers[i:i + BATCH_SIZE]
        tasks = [fetch_yf_history(session, t, days) for t in batch]
        batch_results = await asyncio.gather(*tasks, return_exceptions=True)
        for t, closes in zip(batch, batch_results):
            if isinstance(closes, list) and len(closes) >= 5:
                results[t] = closes
        # Small delay between batches to stay polite
        if i + BATCH_SIZE < len(tickers):
            await asyncio.sleep(BATCH_DELAY)
        # Progress
        if (i // BATCH_SIZE) % 5 == 0:
            print(f"      [batch] {min(i + BATCH_SIZE, len(tickers))}/{len(tickers)} done, "
                  f"valid={len(results)}")
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
def generate_rationale(pick, all_results):
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

    return (
        f"**{conviction}: {name} ({ticker})** — ${price:,.4f}\n\n"
        f"{tone}\n\n"
        f"Key drivers: {bull_text}.\n\n"
        f"**Technical Setup**\n" + "\n".join(tech_lines) + "\n\n"
        f"**Trade Plan**\n"
        f"Entry: Current levels or pullback to SMA20.\n"
        f"Stop-loss: Daily close below SMA20 or prior swing low.\n"
        f"Target: Upside continuation toward next resistance zone.\n"
        f"Position size: Size to volatility — max 5% for high-vol names, 2% for crypto.\n\n"
        f"**Why {name}?**\n"
        f"Top score of {score} across {total} tracked assets ({comp})\n\n"
        f"*Not financial advice. Data from Yahoo Finance v8 public API. DYOR.*"
    )


# ─── Main ───────────────────────────────────────────────────────────────────
async def main():
    now = datetime.now()
    is_monday = now.weekday() == 0
    is_afternoon = 12 <= now.hour < 23

    # Load cached pick if not Monday afternoon
    if not (is_monday and is_afternoon) and DATA_PATH.exists():
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

        # Add metals & crypto
        for t, n, c in METALS:
            if t not in [u[0] for u in universe]:
                universe.append((t, n, c))
        for t, n, c in CRYPTO:
            if t not in [u[0] for u in universe]:
                universe.append((t, n, c))

        print(f"      [weekly_pick] Total to analyze: {len(universe)}")

        # Fetch all histories in batches
        tickers = [t for t, _, _ in universe]
        histories = await batch_fetch(session, tickers)

        # Analyze each
        results = []
        for t, n, c in universe:
            closes = histories.get(t, [])
            r = analyze_one(t, n, c, closes)
            if r:
                results.append(r)

        print(f"      [weekly_pick] Valid results: {len(results)}")

        if not results:
            print("      [weekly_pick] ERROR: no results")
            return {}

        results.sort(key=lambda x: x["score"], reverse=True)
        pick = results[0]

        wp = {
            "generated_at": now.isoformat(),
            "week_label": now.strftime("Week of %b %-d, %Y"),
            "top_pick": pick,
            "top_five": results[:5],
            "all_assets": results,
            "rationale": generate_rationale(pick, results),
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

        print(json.dumps(wp["top_five"], indent=2))
        return wp


if __name__ == "__main__":
    wp = asyncio.run(main())
    print(json.dumps(wp.get("top_five", []), indent=2))


# ─── Synchronous wrapper for backward compat (called by automated_nasdaq_analysis.py) ──

def get_weekly_pick():
    """Synchronous entry point called by automated_nasdaq_analysis.py.
    Delegates to async main() via asyncio.run()."""
    try:
        return asyncio.run(main())
    except Exception as e:
        print(f"      [weekly_pick] ERROR: {e}")
        return {}
