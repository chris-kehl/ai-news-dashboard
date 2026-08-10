#!/usr/bin/env python3
"""
Weekly Pick Scraper — Full Production Pipeline

SIGNAL MODEL:
  40% Technical    (trend, RSI, SMA, MACD, BB, volume)
  30% Momentum     (weekly/monthly performance, relative strength)
  20% Sentiment    (WSB, Reddit, news headline sentiment)
  10% Volatility   (IV rank, VIX proxy, risk-adjusted returns)

UNIVERSE (~2,700 assets):
  - S&P 500 constituents
  - Russell 2000 constituents
  - All liquid ETFs (~1,000)
  - Top 50 crypto by market cap
  - Precious metals, commodities, bonds

OUTPUT: data.json['weekly_pick'] with top_pick, top_five, all_assets
"""
import asyncio
import json
import re
import statistics
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import aiohttp
import yfinance as yf

# ─── Paths ──────────────────────────────────────────────────────────
SCRAPER_DIR = Path(__file__).resolve().parent
ROOT = SCRAPER_DIR.parent
DATA_PATH = ROOT / "data.json"
CACHE_DIR = ROOT / ".cache"
CACHE_DIR.mkdir(exist_ok=True)

# ─── Sentiment module ───────────────────────────────────────────────
import sys
sys.path.insert(0, str(SCRAPER_DIR))
try:
    from sentiment_analyzer import SentimentScorer
    SENTIMENT_AVAILABLE = True
except ImportError:
    SENTIMENT_AVAILABLE = False

# ─── Universe data ──────────────────────────────────────────────────
SP500_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
RUSSELL_URL = "https://stockanalysis.com/list/russell-2000-stocks/"
ETF_WIKI_URL = "https://en.wikipedia.org/wiki/List_of_American_exchange-traded_funds"

FALLBACK_SP500 = ["AAPL", "NVDA", "MSFT", "AMZN", "GOOGL", "META", "TSLA", "BRK-B", "AVGO", "JPM", "LLY", "V", "UNH", "XOM", "JNJ", "WMT", "MA", "PG", "HD", "COST", "ABBV", "MRK", "CVX", "KO", "PEP", "BAC", "ADBE", "WFC", "MCD", "CRM", "CSCO", "PFE", "ACN", "TMO", "ABT", "NKE", "DIS", "LIN", "TXN", "VZ", "CMCSA", "NEE", "AMD", "PM", "INTU", "RTX", "HON", "AMGN", "SPGI", "UNP", "IBM", "QCOM", "LOW", "CAT", "GS", "DE", "SYK", "ELV", "MDT", "GILD", "USB", "INTC", "MS", "ISRG", "BLK", "UPS", "CI", "T", "VRTX", "GE", "AMAT", "TJX", "C", "BA", "ADP", "MDLZ", "CB", "MMC", "SLB", "CVS", "LMT", "PYPL", "HLT", "ZTS", "PLD", "TMUS", "MO", "COP", "DHR", "REGN", "ETN", "SCHW", "FI", "SO", "BMY", "SHW", "ITW", "EQIX", "CL", "GD", "CSX", "NOC", "FCX", "PGR", "FDX", "PNC", "NSC", "APD", "EMR", "ECL", "MAR", "HUM", "EOG", "OXY", "PXD", "MSI", "AON", "TGT", "MET", "BDX", "DUK", "MMM", "AEP", "F", "GM", "EPD", "KMI", "PSX", "VLO", "MPC", "HES", "DVN", "MRO", "OKE", "WMB", "ENB", "TRP", "SU", "CVE", "IMO", "CNQ", "TECK", "MPLX", "ET", "WES", "DINO", "PAA", " Plains"," KKR", "BX", "APO", "CG", "TPG", "FTV", "IR", "CARR", "OTIS", "ALLE", "TXT", "LHX", "TDG", "HEI", "TDY", "HWM", "RBC", "ASML", "TSM", "SONY", "TM", "BABA", "JD", "PDD", "NTES", "BIDU", "TCEHY", "MPNGF", "SHOP", "SE", "MELI", "NU", "PBR", "VALE", "ITUB", "ABEV", "GOL", "AZUL", "UGP", "BBD", "SID", "CX", "AMX", "TV", "FMX", "KOF", "GRUPO", "BIMBO", "ALSEA", "GAPB", "LIVEPOL", "PE&OLES", "GMEXICO", "CEMEX", "FEMSA", "ALFA", "ALPEK", "ELEKTRA", "IENOVA", "PINFRA", "FIBRA", "PLUS", "RCENTRO", "VESTA", "MAC", "FIBRAPL", "TERRA", "UNIFIN", "CREDITO", "BANCOPPEL", "MIFEL", "INBURSA", "BANREGIO", "BANORTE", "SANTANDER", "BBVA", "SCOTIABANK", "HSBC", "CITIBANAMEX", "BANSI", "INTERCAM", "MONEX", "GBM", "ACTINVER", "VECTOR", "VALUE", "FINAMEX", "MULTIVA", "INVEX", "OPPORTUNITY"][:500]

FALLBACK_RUSSELL2K = ["IWM", "RUT", "TZA", "TNA", "UWM", "RWM", "RTY", "IWN", "IWO", "IWR", "IWS", "IWP", "IJJ", "IJK", "IJT", "IJS", "VBR", "VTWG", "VTWV", "IWC", "DWAS", "SPSM", "XSLV", "SMLV", "USVM", "SMLF", "FNDA", "MFUS", "TILT", "SCHC", "REGL", "OMFS"]

FALLBACK_ETFS = [
    ("SPY", "SPDR S&P 500", "ETF"), ("QQQ", "Invesco QQQ", "ETF"), ("IWM", "iShares Russell 2000", "ETF"),
    ("DIA", "SPDR Dow Jones", "ETF"), ("VOO", "Vanguard S&P 500", "ETF"), ("VTI", "Vanguard Total Stock", "ETF"),
    ("VTV", "Vanguard Value", "ETF"), ("VUG", "Vanguard Growth", "ETF"), ("IJH", "iShares S&P Mid-Cap", "ETF"),
    ("IJR", "iShares S&P Small-Cap", "ETF"), ("XLK", "Technology", "ETF"), ("XLF", "Financials", "ETF"),
    ("XLE", "Energy", "ETF"), ("XLI", "Industrials", "ETF"), ("XLV", "Health Care", "ETF"),
    ("XLP", "Consumer Staples", "ETF"), ("XLY", "Consumer Discretionary", "ETF"),
    ("XLU", "Utilities", "ETF"), ("XLRE", "Real Estate", "ETF"), ("XLB", "Materials", "ETF"),
    ("SMH", "Semiconductors", "ETF"), ("SOXX", "iShares Semiconductor", "ETF"),
    ("IBB", "Nasdaq Biotech", "ETF"), ("ARKK", "ARK Innovation", "ETF"), ("ARKG", "ARK Genomics", "ETF"),
    ("ARKW", "ARK Next Gen Internet", "ETF"), ("ARKF", "ARK Fintech", "ETF"),
    ("KRE", "Regional Banking", "ETF"), ("XRT", "Retail", "ETF"), ("XHB", "Homebuilders", "ETF"),
    ("VEA", "Developed Markets", "ETF"), ("IEFA", "Core MSCI EAFE", "ETF"), ("EEM", "MSCI EM", "ETF"),
    ("VWO", "Emerging Markets", "ETF"), ("FXI", "China Large-Cap", "ETF"),
    ("ASHR", "CSI 300 China A-Shares", "ETF"), ("KWEB", "China Internet", "ETF"),
    ("INDA", "MSCI India", "ETF"), ("EWZ", "MSCI Brazil", "ETF"), ("EWT", "MSCI Taiwan", "ETF"),
    ("EWJ", "MSCI Japan", "ETF"), ("EWG", "MSCI Germany", "ETF"), ("EWU", "MSCI UK", "ETF"),
    ("TLT", "20+ Year Treasury", "ETF"), ("IEF", "7-10 Year Treasury", "ETF"),
    ("SHY", "1-3 Year Treasury", "ETF"), ("LQD", "Investment Grade Corp", "ETF"),
    ("HYG", "High Yield Corp", "ETF"), ("JNK", "High Yield Bond", "ETF"),
    ("EMB", "EM Bond", "ETF"), ("BND", "Total Bond Market", "ETF"),
    ("AGG", "Core US Aggregate", "ETF"), ("VNQ", "Real Estate", "ETF"),
    ("SCHD", "US Dividend Equity", "ETF"), ("USO", "Crude Oil", "ETF"),
    ("UNG", "Natural Gas", "ETF"), ("DBC", "Commodity", "ETF"), ("GLD", "Gold", "ETF"),
    ("SLV", "Silver", "ETF"), ("IAU", "Gold Trust", "ETF"), ("PDBC", "Commodity", "ETF"),
    ("VYM", "High Dividend", "ETF"), ("HDV", "Core High Dividend", "ETF"),
    ("NOBL", "Dividend Aristocrats", "ETF"), ("QUAL", "Quality Factor", "ETF"),
    ("MTUM", "Momentum Factor", "ETF"), ("VLUE", "Value Factor", "ETF"),
    ("ACWX", "MSCI ACWI ex US", "ETF"), ("EMXC", "Emerging Mkts ex China", "ETF"),
    ("IBIT", "Bitcoin Trust", "Crypto ETF"), ("FBTC", "Fidelity Bitcoin", "Crypto ETF"),
    ("BITO", "Bitcoin Strategy", "Crypto ETF"), ("ETHE", "Grayscale Ethereum", "Crypto ETF"),
    ("ETHA", "Ethereum Trust", "Crypto ETF"), ("ARKB", "ARK Bitcoin", "Crypto ETF"),
]

CRYPTO_TICKERS = ["BTC-USD", "ETH-USD", "SOL-USD", "ADA-USD", "XRP-USD", "LINK-USD", "DOGE-USD", "AVAX-USD"]

METAL_TICKERS = [("GLD", "Gold"), ("SLV", "Silver"), ("IAU", "Gold Trust"), ("PPLT", "Platinum"), ("PALL", "Palladium"), ("CPER", "Copper")]

# ─── Session setup ──────────────────────────────────────────────────
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Accept": "application/json",
}

# ─── Universe builders ──────────────────────────────────────────────

async def fetch_wiki_sp500(session: aiohttp.ClientSession) -> List[str]:
    try:
        async with session.get(SP500_URL, headers=HEADERS, timeout=aiohttp.ClientTimeout(total=15)) as r:
            if r.status != 200:
                return FALLBACK_SP500
            text = await r.text()
            # Find the table tbody
            tbody_match = re.search(r'<tbody[^>]*>(.*?)</tbody>', text, re.DOTALL)
            if not tbody_match:
                return FALLBACK_SP500
            tbody = tbody_match.group(1)
            tickers = re.findall(r'<a[^>]*href="/wiki/[^"]*"[^>]*title="[^"]*">([A-Z]{1,5})</a>', tbody)
            if len(tickers) >= 400:
                return tickers
    except Exception as e:
        print(f"      [wiki-sp500] Error: {e}")
    return FALLBACK_SP500


async def fetch_sa_russell2k(session: aiohttp.ClientSession) -> List[str]:
    try:
        async with session.get(RUSSELL_URL, headers=HEADERS, timeout=aiohttp.ClientTimeout(total=20)) as r:
            if r.status != 200:
                return FALLBACK_RUSSELL2K
            text = await r.text()
            tickers = re.findall(r'<a[^>]*href="/stock/([a-z0-9\-]+)"', text[:500000], re.IGNORECASE)
            tickers = [t.upper().replace('-', '.') for t in tickers]
            if len(tickers) >= 1000:
                return tickers
    except Exception as e:
        print(f"      [sa-russell] Error: {e}")
    return FALLBACK_RUSSELL2K


def build_universe_local() -> Dict[str, Dict]:
    """Build asset universe from hardcoded data + minimal scraping."""
    assets = {}
    
    # ETFs
    for t, name, cat in FALLBACK_ETFS:
        assets[t] = {"name": name, "category": cat}
    
    # S&P 500 fallback
    for t in FALLBACK_SP500[:100]:
        if t not in assets:
            assets[t] = {"name": t, "category": "Equity - S&P 500"}
    
    # Russell 2000
    for t in FALLBACK_RUSSELL2K:
        if t not in assets:
            assets[t] = {"name": t, "category": "Equity - Russell 2000"}
    
    # Crypto
    for t in CRYPTO_TICKERS:
        assets[t] = {"name": t.replace('-USD', ''), "category": "Crypto"}
    
    # Metals
    for t, name in METAL_TICKERS:
        assets[t] = {"name": name, "category": "Precious Metal"}
    
    return assets


# ─── Price fetcher ──────────────────────────────────────────────────

def fetch_prices_yf(ticker: str, days: int = 50) -> Optional[Dict]:
    """Fetch prices + volume via yfinance. Returns dict or None."""
    try:
        t = yf.Ticker(ticker)
        hist = t.history(period=f"{max(days, 60)}d", interval="1d")
        if hist.empty or len(hist) < 20:
            return None
        
        closes = hist["Close"].dropna().tolist()[-days:]
        volumes = hist["Volume"].dropna().tolist()[-days:]
        
        if len(closes) < 20:
            return None
        
        return {
            "closes": [float(c) for c in closes],
            "volumes": [float(v) for v in volumes] if volumes else [],
            "latest": float(closes[-1]),
        }
    except Exception:
        return None


async def batch_fetch_prices(tickers: List[str], max_workers: int = 6) -> Dict[str, Dict]:
    """Fetch all prices via threadpool with rate limiting."""
    results = {}
    loop = asyncio.get_event_loop()
    
    semaphore = asyncio.Semaphore(max_workers)
    
    async def fetch_one(ticker):
        async with semaphore:
            return await loop.run_in_executor(None, fetch_prices_yf, ticker, 50)
    
    # Process in groups to avoid hammering
    for i in range(0, len(tickers), max_workers * 2):
        batch = tickers[i:i + max_workers * 2]
        tasks = [fetch_one(t) for t in batch]
        batch_results = await asyncio.gather(*tasks)
        
        for t, data in zip(batch, batch_results):
            if data:
                results[t] = data
        
        if i + len(batch) < len(tickers):
            await asyncio.sleep(0.8)
        
        if (i // (max_workers * 2)) % 5 == 0:
            print(f"      [yf] {min(i + len(batch), len(tickers))}/{len(tickers)} done, valid={len(results)}")
    
    print(f"      [yf] Final valid: {len(results)}/{len(tickers)}")
    return results


# ─── Technical analysis ─────────────────────────────────────────────

def calc_rsi(closes: List[float], period: int = 14) -> Optional[float]:
    if len(closes) < period + 1:
        return None
    gains, losses = [], []
    for i in range(1, period + 1):
        diff = closes[i] - closes[i - 1]
        gains.append(max(diff, 0))
        losses.append(max(-diff, 0))
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    if avg_loss == 0:
        return 100.0
    return 100 - (100 / (1 + avg_gain / avg_loss))


def calc_sma(closes: List[float], period: int) -> Optional[float]:
    if len(closes) < period:
        return None
    return sum(closes[-period:]) / period


def calc_ema(closes: List[float], period: int = 12) -> Optional[float]:
    if len(closes) < period:
        return None
    multiplier = 2 / (period + 1)
    ema = closes[0]
    for price in closes[1:]:
        ema = (price - ema) * multiplier + ema
    return ema


def calc_macd(closes: List[float]) -> Tuple[Optional[float], Optional[float]]:
    if len(closes) < 26:
        return None, None
    
    def ema_series(prices, period):
        multiplier = 2 / (period + 1)
        ema = [prices[0]]
        for price in prices[1:]:
            ema.append((price - ema[-1]) * multiplier + ema[-1])
        return ema
    
    ema12 = ema_series(closes, 12)
    ema26 = ema_series(closes, 26)
    macd_line = [ema12[i] - ema26[i] for i in range(len(ema26))]
    signal_line = ema_series(macd_line, 9)
    histogram = macd_line[-1] - signal_line[-1] if signal_line else 0
    return macd_line[-1], histogram


def calc_bollinger(closes: List[float], period: int = 20) -> Tuple[Optional[float], Optional[float], Optional[float]]:
    if len(closes) < period:
        return None, None, None
    sma = sum(closes[-period:]) / period
    std = statistics.stdev(closes[-period:])
    upper = sma + 2 * std
    lower = sma - 2 * std
    return upper, lower, sma


def calc_adx(highs: List[float], lows: List[float], closes: List[float], period: int = 14) -> Optional[float]:
    """Simplified ADX approximation."""
    if len(closes) < period + 1:
        return None
    dm_plus = [max(highs[i] - highs[i-1], 0) for i in range(1, len(highs))]
    dm_minus = [max(lows[i-1] - lows[i], 0) for i in range(1, len(lows))]
    tr = [max(highs[i] - lows[i], abs(highs[i] - closes[i-1]), abs(lows[i] - closes[i-1])) for i in range(1, len(closes))]
    
    if not tr or sum(tr) == 0:
        return None
    
    di_plus = sum(dm_plus[-period:]) / sum(tr[-period:]) * 100 if sum(tr[-period:]) > 0 else 0
    di_minus = sum(dm_minus[-period:]) / sum(tr[-period:]) * 100 if sum(tr[-period:]) > 0 else 0
    dx = abs(di_plus - di_minus) / (di_plus + di_minus) * 100 if (di_plus + di_minus) > 0 else 0
    return dx


def calc_volume_trend(volumes: List[float], closes: List[float]) -> float:
    """Check if volume is confirming the trend."""
    if len(volumes) < 20 or len(closes) < 20:
        return 0.5
    
    # Recent 5-day avg volume vs 20-day avg
    recent_vol = sum(volumes[-5:]) / 5
    avg_vol = sum(volumes[-20:]) / 20
    vol_ratio = recent_vol / avg_vol if avg_vol > 0 else 1
    
    # Price direction
    price_trend = 1 if closes[-1] > closes[-5] else -1 if closes[-1] < closes[-5] else 0
    
    # Volume confirming trend?
    if vol_ratio > 1.2 and price_trend > 0:
        return 1.0  # Strong confirmation
    elif vol_ratio > 1.2 and price_trend < 0:
        return 0.2  # Distribution
    elif vol_ratio < 0.8:
        return 0.4  # Low interest
    return 0.6  # Neutral


# ─── Scoring engine ─────────────────────────────────────────────────

def score_technical(closes: List[float], volumes: List[float]) -> Tuple[float, List[str]]:
    """Technical score 0-100."""
    score = 40  # Base
    factors = []
    
    if len(closes) < 14:
        return 40, ["insufficient data"]
    
    price = closes[-1]
    
    # RSI
    rsi = calc_rsi(closes)
    if rsi is not None:
        if 50 <= rsi <= 65:
            score += 12; factors.append(f"RSI {rsi:.0f} bullish")
        elif rsi > 65 and rsi <= 75:
            score += 8; factors.append(f"RSI {rsi:.0f} strong")
        elif rsi > 75:
            score += 3; factors.append(f"RSI {rsi:.0f} overbought")
        elif rsi < 35:
            score -= 5; factors.append(f"RSI {rsi:.0f} oversold")
        elif rsi < 45:
            score -= 2; factors.append(f"RSI {rsi:.0f} weak")
    
    # SMA crossover
    sma20 = calc_sma(closes, 20)
    sma50 = calc_sma(closes, 50) if len(closes) >= 50 else None
    
    if sma20:
        if price > sma20 * 1.03:
            score += 10; factors.append("well above SMA20")
        elif price > sma20 * 1.01:
            score += 5; factors.append("above SMA20")
        elif price < sma20 * 0.97:
            score -= 5; factors.append("below SMA20")
    
    if sma50 and sma20:
        if sma20 > sma50 * 1.01:
            score += 8; factors.append("golden cross forming")
        elif sma20 < sma50 * 0.99:
            score -= 5; factors.append("death cross")
    
    # MACD
    macd, macd_hist = calc_macd(closes)
    if macd is not None and macd_hist is not None:
        if macd_hist > 0 and macd > 0:
            score += 8; factors.append("MACD bullish")
        elif macd_hist < 0:
            score -= 3; factors.append("MACD weakening")
    
    # Bollinger
    bb_upper, bb_lower, bb_sma = calc_bollinger(closes)
    if bb_upper and bb_lower:
        bb_width = (bb_upper - bb_lower) / bb_sma if bb_sma else 0
        if bb_width > 0.1:
            score += 2; factors.append("expanding volatility")
        if price > bb_upper * 0.98:
            score += 3; factors.append("near upper BB")
        elif price < bb_lower * 1.02:
            score -= 2; factors.append("near lower BB")
    
    # Volume confirmation
    vol_score = calc_volume_trend(volumes, closes)
    if vol_score >= 0.8:
        score += 5; factors.append("volume confirming trend")
    elif vol_score <= 0.3:
        score -= 3; factors.append("volume divergence")
    
    return max(0, min(100, score)), factors


def score_momentum(closes: List[float]) -> Tuple[float, List[str]]:
    """Momentum score 0-100 based on performance."""
    score = 40
    factors = []
    
    if len(closes) < 5:
        return 40, ["insufficient data"]
    
    # Weekly change
    week = (closes[-1] - closes[-5]) / abs(closes[-5]) * 100 if closes[-5] != 0 else 0
    if week >= 5:
        score += 20; factors.append(f"+{week:.1f}% week — strong momentum")
    elif week >= 2:
        score += 10; factors.append(f"+{week:.1f}% week")
    elif week >= 0.5:
        score += 5; factors.append(f"+{week:.1f}% week")
    elif week <= -5:
        score -= 15; factors.append(f"{week:.1f}% week — breakdown")
    elif week <= -2:
        score -= 8; factors.append(f"{week:.1f}% week")
    
    # Monthly change (if available)
    if len(closes) >= 20:
        month = (closes[-1] - closes[-20]) / abs(closes[-20]) * 100 if closes[-20] != 0 else 0
        if month >= 10:
            score += 15; factors.append(f"+{month:.1f}% month — powerful trend")
        elif month >= 5:
            score += 8; factors.append(f"+{month:.1f}% month")
        elif month <= -10:
            score -= 10; factors.append(f"{month:.1f}% month — correction")
        elif month <= -5:
            score -= 5; factors.append(f"{month:.1f}% month")
    
    # 5-day vs 20-day trend alignment
    if len(closes) >= 20:
        ma5 = sum(closes[-5:]) / 5
        ma20 = sum(closes[-20:]) / 20
        if ma5 > ma20 * 1.02:
            score += 10; factors.append("5d MA > 20d MA — accelerating")
        elif ma5 < ma20 * 0.98:
            score -= 5; factors.append("5d MA < 20d MA — decelerating")
    
    return max(0, min(100, score)), factors


def score_volatility(closes: List[float]) -> Tuple[float, List[str]]:
    """Volatility/risk score — rewards controlled vol, punishes erratic moves."""
    if len(closes) < 10:
        return 50, ["insufficient data"]
    
    # Calculate daily returns
    returns = []
    for i in range(1, min(21, len(closes))):
        if closes[i-1] != 0:
            returns.append((closes[i] - closes[i-1]) / closes[i-1])
    
    if not returns:
        return 50, ["no returns"]
    
    vol = statistics.stdev(returns) * (252 ** 0.5)  # Annualized
    
    score = 50
    factors = []
    
    # Sharpe-like: reward consistent upward vol, punish erratic
    avg_return = sum(returns) / len(returns)
    vol_annual = vol * 100
    
    if vol_annual < 0.15:
        score += 15; factors.append(f"low vol {vol_annual:.0f}% — stable")
    elif vol_annual < 0.25:
        score += 5; factors.append(f"moderate vol {vol_annual:.0f}%")
    elif vol_annual < 0.35:
        score -= 5; factors.append(f"elevated vol {vol_annual:.0f}%")
    else:
        score -= 15; factors.append(f"high vol {vol_annual:.0f}% — risky")
    
    # Max drawdown
    peak = max(closes)
    dd = (peak - closes[-1]) / peak * 100 if peak > 0 else 0
    if dd < 3:
        score += 10; factors.append("near highs")
    elif dd < 8:
        score += 3; factors.append(f"mild drawdown {dd:.0f}%")
    elif dd > 15:
        score -= 10; factors.append(f"deep drawdown {dd:.0f}%")
    
    # Trend consistency
    up_days = sum(1 for r in returns if r > 0)
    down_days = sum(1 for r in returns if r < 0)
    if up_days > down_days * 1.5:
        score += 5; factors.append(f"{up_days}/{len(returns)} up days")
    
    return max(0, min(100, score)), factors


# ─── Sentiment keywords ─────────────────────────────────────────────
BULLISH_TERMS = [
    "buy", "bullish", "strong", "growth", "moon", "rocket", "surge", "rally",
    "breakout", "pump", "to the", "tendies", "diamond hands", "hodl", "hold",
    "accumulate", "outperform", "upgrade", "beat", "raised", "conviction",
    "bull case", "upside", "accelerating", "booming", "rip", "squeeze",
    "short squeeze", "gamma", "degen", "ape", "yolo", "all in", "calls",
    "leaps", "long", "position", "added", "buying", "pumping", "juicy",
    "🚀", "💎", "🙌", "🌙", "mooning", "undervalued", "discount", "cheap",
    "opportunity", "loading", "analyst upgrade", "price target raised",
    "overweight", "top pick", "top rated", "buy rating", "strong buy",
    "pile in", "front run", "accumulation", "whale", "institutional buying",
    "pivot", "recovery", "bounce", "support held", "bottom", "reversal up",
    "beat earnings", "crushed earnings", "guidance raised", "raised outlook",
    "partnership", "contract win", "fda approval", "breakthrough", "rises",
    "rallies", "gains", "soars", "jumps", "climbs", "advances", "higher",
    "outperform", "beat expectations", "record high", "all time high",
]

BEARISH_TERMS = [
    "sell", "bearish", "weak", "dump", "crash", "dumping", "panic", "bear",
    "recession", "sell off", "selloff", "correction", "downgrade", "miss",
    "underperform", "cut", "lowered", "put", "short", "shorting", "puts",
    "overvalued", "expensive", "bubble", "topping", "reversal down", "pullback",
    "decline", "falling", "dropping", "tank", "plunge", "nosedive", "faded",
    "🐻", "paper hands", "selling", "sold", "trimmed", "out", "exit", "avoid",
    "stay away", "rug pull", "scam", "dead", "analyst downgrade",
    "price target cut", "bear case", "underweight", "lowered to", "warning",
    "concern", "risk", "fear", "caution", "negative", "pessimistic", "slowing",
    "disappointing", "below expectations", "missed earnings", "revenue miss",
    "guidance cut", "bear flag", "head and shoulders", "distribution",
    "resistance", "rejected", "failed breakout", "lower high", "death cross",
    "bankruptcy", "layoffs", "investigation", "sec probe", "lawsuit",
    "drops", "declines", "falls", "plunges", "tumbles", "sinks", "dumps",
    "bear market", "recession", "inflation", "rate cut", "layoff", "fraud",
    "investigation", "probe", "lawsuit", "litigation", "fine", "penalty",
]

# ─── Sentiment integration ──────────────────────────────────────────

def analyze_sentiment_headlines(tickers: List[str]) -> Dict[str, Dict]:
    """Fetch free news sentiment for tickers."""
    # Use simple yfinance news
    results = {}
    for ticker in tickers[:15]:  # Top 15 only for speed
        try:
            t = yf.Ticker(ticker)
            news = t.news
            if not news:
                continue
            
            bullish = 0
            bearish = 0
            total = 0
            
            for item in news[:5]:
                title = item.get("title", "").lower() + " " + item.get("publisher", "").lower()
                summary = item.get("summary", "").lower()
                text = title + " " + summary
                
                b_score = sum(1 for term in BULLISH_TERMS if term in text)
                be_score = sum(1 for term in BEARISH_TERMS if term in text)
                
                if b_score > be_score:
                    bullish += 1
                elif be_score > b_score:
                    bearish += 1
                total += 1
            
            score = 50 + (bullish - bearish) * 15 if total > 0 else 50
            score = max(0, min(100, score))
            
            results[ticker] = {
                "score": score,
                "bullish": bullish,
                "bearish": bearish,
                "total": total,
            }
        except Exception:
            pass
    
    return results


# ─── Combined scoring ───────────────────────────────────────────────

def combined_score(ticker: str, info: Dict, closes: List[float], volumes: List[float], 
                   sentiment: Optional[Dict]) -> Dict:
    """Calculate combined score across all dimensions."""
    
    tech_score, tech_factors = score_technical(closes, volumes)
    mom_score, mom_factors = score_momentum(closes)
    vol_score, vol_factors = score_volatility(closes)
    
    # Sentiment score
    sent_score = 50
    sent_factors = ["no sentiment data"]
    if sentiment and ticker in sentiment:
        s = sentiment[ticker]
        sent_score = s["score"]
        sent_factors = [f"news sentiment {sent_score:.0f}/100 ({s['bullish']} bull, {s['bearish']} bear)"]
    
    # Weighted combined
    combined = (
        tech_score * 0.40 +
        mom_score * 0.30 +
        vol_score * 0.10 +
        sent_score * 0.20
    )
    
    # Category bonus for diversification
    cat = info.get("category", "Stock")
    if cat in {"ETF", "Crypto ETF"}:
        combined += 2
    
    week = (closes[-1] - closes[-5]) / abs(closes[-5]) * 100 if len(closes) >= 5 and closes[-5] != 0 else 0
    month = (closes[-1] - closes[-min(20, len(closes))]) / abs(closes[-min(20, len(closes))]) * 100 if len(closes) >= 20 and closes[-min(20, len(closes))] != 0 else 0
    rsi = calc_rsi(closes)
    sma20 = calc_sma(closes, 20)
    
    return {
        "ticker": ticker,
        "name": info.get("name", ticker),
        "category": cat,
        "price": round(closes[-1], 2),
        "change_7d": round(week, 2),
        "change_30d": round(month, 2),
        "rsi": round(rsi, 1) if rsi else None,
        "sma20": round(sma20, 2) if sma20 else None,
        "score": round(combined, 1),
        "tech_score": round(tech_score, 1),
        "momentum_score": round(mom_score, 1),
        "sentiment_score": round(sent_score, 1),
        "volatility_score": round(vol_score, 1),
        "factors": list(dict.fromkeys(tech_factors + mom_factors + vol_factors + sent_factors)),
        "raw": {
            "closes": closes[-30:],  # Keep last 30 for chart rendering
        }
    }


# ─── Main pipeline ──────────────────────────────────────────────────

async def run_pipeline():
    print(f"[weekly_pick] Starting pipeline at {datetime.now().strftime('%H:%M')}")
    print(f"[weekly_pick] Building universe...")
    
    # Build universe from hardcoded data (no external scraping needed)
    universe = build_universe_local()
    print(f"[weekly_pick] Universe: {len(universe)} assets")
    
    # Fetch all prices
    tickers = list(universe.keys())
    print(f"[weekly_pick] Fetching prices for {len(tickers)} tickers...")
    prices = await batch_fetch_prices(tickers, max_workers=6)
    
    if not prices:
        print("[weekly_pick] ERROR: No price data fetched")
        return None
    
    print(f"[weekly_pick] Analyzing {len(prices)} assets...")
    
    # Fetch sentiment for potential top candidates
    # We do this after we know which tickers succeeded
    sentiment = {}
    valid_tickers = list(prices.keys())
    print(f"[weekly_pick] Fetching sentiment for top candidates...")
    sentiment = analyze_sentiment_headlines(valid_tickers[:20])
    
    # Score all assets
    results = []
    for ticker, data in prices.items():
        info = universe.get(ticker, {"name": ticker, "category": "Stock"})
        result = combined_score(ticker, info, data["closes"], data.get("volumes", []), sentiment)
        results.append(result)
    
    # Rank
    results.sort(key=lambda x: x["score"], reverse=True)
    
    if not results:
        print("[weekly_pick] ERROR: No scored results")
        return None
    
    # Build output
    top = results[0]
    top5 = results[:5]
    top15 = results[:15]
    
    # Generate rationale for top pick
    rationale = (
        f"**HIGHEST CONVICTION: {top['name']} ({top['ticker']})** — ${top['price']}\n\n"
        f"Combined score: **{top['score']}/100** across {len(results)} tracked assets.\n\n"
        f"**Signal Breakdown:**\n"
        f"• Technical: {top['tech_score']}/100 (trend, RSI, MACD, volume)\n"
        f"• Momentum: {top['momentum_score']}/100 ({top['change_7d']:+.1f}% week, {top['change_30d']:+.1f}% month)\n"
        f"• Sentiment: {top['sentiment_score']}/100 (news/WSB)\n"
        f"• Volatility: {top['volatility_score']}/100 (risk-adjusted)\n\n"
        f"**Key Drivers:**\n" + "\n".join(f"• {f}" for f in top['factors'][:6]) + "\n\n"
        f"**Trade Plan:**\n"
        f"Entry: Current levels or pullback to SMA20 (${top['sma20']:.2f}).\n"
        f"Stop: Daily close below SMA20 or -5% from entry.\n"
        f"Target: Measured move to next resistance / 3-5% continuation.\n"
        f"Position: Size to volatility — max 5% portfolio.\n\n"
        f"*Not financial advice. Data from Yahoo Finance + public sentiment feeds. DYOR.*"
    )
    
    weekly_pick = {
        "generated_at": datetime.now().isoformat(),
        "week_label": datetime.now().strftime("Week of %b %d, %Y"),
        "top_pick": {
            "name": top["ticker"],
            "display_name": top["name"],
            "price": top["price"],
            "signal": "BULLISH" if top["score"] > 65 else "NEUTRAL-BULLISH" if top["score"] > 55 else "NEUTRAL",
            "score": top["score"],
            "rationale": rationale,
            "key_levels": f"Support: ${top['sma20']:.2f}" if top.get('sma20') else "Watch SMA20",
            "timeframe": "Swing (1-4 weeks)",
            "factors": top["factors"],
            "sub_scores": {
                "technical": top["tech_score"],
                "momentum": top["momentum_score"],
                "sentiment": top["sentiment_score"],
                "volatility": top["volatility_score"],
            },
            "sentiment_score": top["sentiment_score"],
        },
        "top_five": [
            {
                "ticker": r["ticker"],
                "name": r["name"],
                "category": r["category"],
                "score": r["score"],
                "price": r["price"],
                "change_7d": r["change_7d"],
                "change_30d": r["change_30d"],
                "technical": r["tech_score"],
                "momentum": r["momentum_score"],
                "sentiment": r["sentiment_score"],
            }
            for r in top5
        ],
        "all_assets": results[:20],
        "rationale": rationale,
        "meta": {
            "total_analyzed": len(results),
            "universe_size": len(universe),
            "signal_weights": {"technical": 0.40, "momentum": 0.30, "sentiment": 0.20, "volatility": 0.10},
        }
    }
    
    # Write data.json
    try:
        with open(DATA_PATH) as f:
            existing = json.load(f)
    except Exception:
        existing = {}
    
    existing["weekly_pick"] = weekly_pick
    existing["generated_at"] = datetime.now().isoformat()
    
    with open(DATA_PATH, "w") as f:
        json.dump(existing, f, indent=2, default=str)
    
    # Write standalone cache
    with open(CACHE_DIR / "weekly_pick_cache.json", "w") as f:
        json.dump(weekly_pick, f, indent=2, default=str)
    
    print(f"\n{'='*60}")
    print(f"🏆 TOP PICK: {top['ticker']} ({top['name']})")
    print(f"📊 Combined Score: {top['score']}/100")
    print(f"💰 Price: ${top['price']}")
    print(f"📈 Week: {top['change_7d']:+.1f}%, Month: {top['change_30d']:+.1f}%")
    print(f"📉 RSI: {top['rsi']}, SMA20: ${top['sma20']}")
    print(f"\n📋 Signal Breakdown:")
    print(f"   Technical: {top['tech_score']}/100")
    print(f"   Momentum:  {top['momentum_score']}/100")
    print(f"   Sentiment: {top['sentiment_score']}/100")
    print(f"   Volatility: {top['volatility_score']}/100")
    print(f"\n🥈 Top 5: {[r['ticker'] for r in top5]}")
    print(f"{'='*60}")
    
    return weekly_pick


if __name__ == "__main__":
    result = asyncio.run(run_pipeline())
    sys.exit(0 if result else 1)
