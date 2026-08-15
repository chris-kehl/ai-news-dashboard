#!/usr/bin/env python3
"""
Multi-Source POSITIVE Sentiment Analyzer

Sources: r/wallstreetbets, CNBC, Bloomberg, Yahoo Finance, Benzinga, Google News
Filter: ONLY positive/bullish posts contribute to scores. Bearish items are dropped.
"""
import asyncio
import json
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Set
from scraper_utils import fetch_with_retry, DEFAULT_HEADERS

# ─── Config ──────────────────────────────────────────────────────────────────
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/html",
    "Accept-Language": "en-US,en;q=0.9",
}

# ─── Sentiment keyword dictionaries ──────────────────────────────────────────
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
    "outperform expectations", "record high", "all time high",
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
    "bear market", "inflation", "layoff", "fraud", "probe", "litigation",
    "fine", "penalty",
]

# ─── Ticker mapping ──────────────────────────────────────────────────────────
NAME_TO_TICKER = {
    "APPLE": "AAPL", "TESLA": "TSLA", "NVIDIA": "NVDA", "MICROSOFT": "MSFT",
    "AMAZON": "AMZN", "GOOGLE": "GOOGL", "ALPHABET": "GOOGL",
    "META": "META", "FACEBOOK": "META", "BERKSHIRE HATHAWAY": "BRK-B",
    "JPMORGAN": "JPM", "JOHNSON AND JOHNSON": "JNJ", "VISA": "V",
    "MASTERCARD": "MA", "WALMART": "WMT", "PROCTER AND GAMBLE": "PG",
    "UNITEDHEALTH": "UNH", "HOME DEPOT": "HD", "CHEVRON": "CVX",
    "ELI LILLY": "LLY", "PFIZER": "PFE", "COCA-COLA": "KO",
    "PEPSICO": "PEP", "MCDONALDS": "MCD", "DISNEY": "DIS",
    "WALT DISNEY": "DIS", "NETFLIX": "NFLX", "AMD": "AMD", "INTEL": "INTC",
    "QUALCOMM": "QCOM", "CISCO": "CSCO", "ORACLE": "ORCL", "SALESFORCE": "CRM",
    "ADOBE": "ADBE", "PAYPAL": "PYPL", "UBER": "UBER", "LYFT": "LYFT",
    "AIRBNB": "ABNB", "COINBASE": "COIN", "ROBINHOOD": "HOOD", "SNAP": "SNAP",
    "SQUARE": "SQ", "BLOCK": "SQ", "MERCK": "MRK",
    "BRISTOL-MYERS": "BMY", "GILEAD": "GILD", "MODERNA": "MRNA",
    "VERTEX": "VRTX", "EXXON": "XOM", "EXXONMOBIL": "XOM", "SHELL": "SHEL",
    "GOLDMAN SACHS": "GS", "MORGAN STANLEY": "MS", "BANK OF AMERICA": "BAC",
    "CITIGROUP": "C", "WELLS FARGO": "WFC", "AMERICAN EXPRESS": "AXP",
    "BLACKROCK": "BLK", "BOEING": "BA", "LOCKHEED MARTIN": "LMT",
    "RAYTHEON": "RTX", "CATERPILLAR": "CAT", "FORD": "F", "GENERAL MOTORS": "GM",
    "NIKE": "NKE", "STARBUCKS": "SBUX", "COSTCO": "COST",
    # Crypto
    "BITCOIN": "BTC-USD", "ETHEREUM": "ETH-USD", "SOLANA": "SOL-USD",
    "RIPPLE": "XRP-USD", "DOGECOIN": "DOGE-USD", "CARDANO": "ADA-USD",
    "AVALANCHE": "AVAX-USD", "CHAINLINK": "LINK-USD", "POLKADOT": "DOT-USD",
    "BITTENSOR": "TAO-USD", "LITECOIN": "LTC-USD", "NEAR": "NEAR-USD",
    "UNISWAP": "UNI-USD", "APTOS": "APT-USD", "SHIBA INU": "SHIB-USD",
    "PEPE": "PEPE-USD", "SUI": "SUI-USD",
}

# ─── Text-level sentiment scorer ─────────────────────────────────────────────
def score_text(text: str) -> float:
    """Return polarity: -1.0 (very bearish) to +1.0 (very bullish)."""
    if not text:
        return 0.0
    text_upper = text.upper()
    bull = sum(1 for term in BULLISH_TERMS if term.upper() in text_upper)
    bear = sum(1 for term in BEARISH_TERMS if term.upper() in text_upper)
    total = bull + bear
    if total == 0:
        return 0.0
    return (bull - bear) / total


def is_positive(text: str) -> bool:
    """Return True if text has net-positive sentiment."""
    return score_text(text) > 0.05


# ═══════════════════════════════════════════════════════════════════════════════
#  SOURCE #1: r/wallstreetbets via Reddit OAuth API (positive posts only)
# ═══════════════════════════════════════════════════════════════════════════════
def fetch_wsb_positive(limit: int = 50, min_score: int = 5) -> List[dict]:
    """Fetch WSB posts via Reddit OAuth API. Only returns positive posts."""
    try:
        from reddit_api_client import get_subreddit_posts
        posts, status = get_subreddit_posts("wallstreetbets", sort="hot", limit=limit * 2)
        if not isinstance(status, int) or status != 200:
            return []

        results = []
        for p in posts:
            score = p.get("score", 0)
            if score < min_score:
                continue
            title = p.get("title", "")
            if not is_positive(title):
                continue
            weight = min(4.0, 1.0 + score / 200)
            results.append({
                "text": title[:300],
                "weight": weight,
                "source": "reddit_wallstreetbets",
                "score": score,
            })
            if len(results) >= limit:
                break
        print(f"      [wsb] {len(results)} positive posts")
        return results
    except Exception as e:
        print(f"      [wsb] Error: {e}")
        return []


# ═══════════════════════════════════════════════════════════════════════════════
#  SOURCE #2: CNBC RSS
# ═══════════════════════════════════════════════════════════════════════════════
def fetch_cnbc(limit: int = 20) -> List[dict]:
    """Fetch CNBC top news via RSS, keep only positive headlines."""
    url = "https://www.cnbc.com/id/100003114/device/rss/rss.html"
    try:
        r = fetch_with_retry(url, headers=HEADERS, timeout=15, max_retries=2)
        if not r:
            return []
        text = r.text
        titles = re.findall(r"<title>([^<]+)</title>", text)
        results = []
        for t in titles[1:]:  # skip channel title
            t_clean = t.replace("&amp;", "&").strip()
            if not t_clean or len(t_clean) < 20:
                continue
            if not is_positive(t_clean):
                continue
            results.append({"text": t_clean, "weight": 1.0, "source": "cnbc"})
        print(f"      [cnbc] {len(results)} positive headlines")
        return results
    except Exception as e:
        print(f"      [cnbc] Error: {e}")
        return []


# ═══════════════════════════════════════════════════════════════════════════════
#  SOURCE #3: Bloomberg RSS
# ═══════════════════════════════════════════════════════════════════════════════
def fetch_bloomberg(limit: int = 20) -> List[dict]:
    """Fetch Bloomberg news via RSS, keep only positive headlines."""
    urls = [
        "https://feeds.bloomberg.com/business/news.rss",
        "https://feeds.bloomberg.com/technology/news.rss",
    ]
    results = []
    try:
        for url in urls:
            r = fetch_with_retry(url, headers=HEADERS, timeout=15, max_retries=2)
            if not r:
                continue
            text = r.text
            titles = re.findall(r"<title>([^<]+)</title>", text)
            for t in titles[1:]:
                t_clean = t.replace("&amp;", "&").strip()
                if not t_clean or len(t_clean) < 20:
                    continue
                if not is_positive(t_clean):
                    continue
                results.append({"text": t_clean, "weight": 1.0, "source": "bloomberg"})
        print(f"      [bloomberg] {len(results)} positive headlines")
        return results
    except Exception as e:
        print(f"      [bloomberg] Error: {e}")
        return []


# ═══════════════════════════════════════════════════════════════════════════════
#  SOURCE #4: Yahoo Finance RSS
# ═══════════════════════════════════════════════════════════════════════════════
def fetch_yahoo_finance(limit: int = 20) -> List[dict]:
    """Fetch Yahoo Finance news headlines, keep only positive ones."""
    url = "https://finance.yahoo.com/news/rssindex"
    try:
        r = fetch_with_retry(url, headers=HEADERS, timeout=15, max_retries=2)
        if not r:
            return []
        text = r.text
        titles = re.findall(r"<title>([^<]+)</title>", text)
        results = []
        for t in titles[1:]:
            t_clean = (
                t.replace("<![CDATA[", "")
                .replace("]]>", "")
                .replace("&amp;", "&")
                .strip()
            )
            if not t_clean or len(t_clean) < 20 or "Yahoo Finance" in t_clean:
                continue
            if not is_positive(t_clean):
                continue
            results.append({"text": t_clean, "weight": 1.0, "source": "yahoo_finance"})
        print(f"      [yahoo] {len(results)} positive headlines")
        return results
    except Exception as e:
        print(f"      [yahoo] Error: {e}")
        return []


# ═══════════════════════════════════════════════════════════════════════════════
#  SOURCE #5: Benzinga (via Google News since direct RSS is dead)
# ═══════════════════════════════════════════════════════════════════════════════
def fetch_benzinga(limit: int = 15) -> List[dict]:
    """Fetch Benzinga articles via Google News RSS, keep only positive."""
    # Google News RSS: search for Benzinga-sourced articles
    url = (
        "https://news.google.com/rss/search?q=site:benzinga.com"
        "+stock+OR+market+OR+earnings&hl=en-US&gl=US&ceid=US:en"
    )
    try:
        r = fetch_with_retry(url, headers=HEADERS, timeout=15, max_retries=2)
        if not r:
            return []
        text = r.text
        # Parse title + source
        items = re.findall(
            r"<item>.*?<title>([^<]+)</title>.*?<source[^>]*>([^<]+)</source>.*?</item>",
            text,
            re.DOTALL,
        )
        results = []
        for title, source in items:
            title_clean = (
                re.sub(r"&amp;", "&", title)
                .replace("<![CDATA[", "")
                .replace("]]>", "")
                .strip()
            )
            if not title_clean or len(title_clean) < 20:
                continue
            if not is_positive(title_clean):
                continue
            results.append({"text": title_clean, "weight": 1.1, "source": "benzinga"})
            if len(results) >= limit:
                break
        print(f"      [benzinga] {len(results)} positive headlines")
        return results
    except Exception as e:
        print(f"      [benzinga] Error: {e}")
        return []


# ═══════════════════════════════════════════════════════════════════════════════
#  SOURCE #6: Google News (general market headlines)
# ═══════════════════════════════════════════════════════════════════════════════
def fetch_google_news(limit: int = 20) -> List[dict]:
    """Fetch general stock market news from Google News RSS, keep only positive."""
    url = (
        "https://news.google.com/rss/search?q="
        "stock+market+OR+NASDAQ+OR+SP500+OR+earnings+OR+analyst+upgrade"
        "&hl=en-US&gl=US&ceid=US:en"
    )
    try:
        r = fetch_with_retry(url, headers=HEADERS, timeout=15, max_retries=2)
        if not r:
            return []
        text = r.text
        items = re.findall(
            r"<item>.*?<title>([^<]+)</title>.*?<source[^>]*>([^<]+)</source>.*?</item>",
            text,
            re.DOTALL,
        )
        results = []
        for title, source in items:
            title_clean = (
                re.sub(r"&amp;", "&", title)
                .replace("<![CDATA[", "")
                .replace("]]>", "")
                .strip()
            )
            if not title_clean or len(title_clean) < 20:
                continue
            if not is_positive(title_clean):
                continue
            results.append({"text": title_clean, "weight": 1.0, "source": "google_news"})
            if len(results) >= limit:
                break
        print(f"      [google_news] {len(results)} positive headlines")
        return results
    except Exception as e:
        print(f"      [google_news] Error: {e}")
        return []


# ─── Orchestrator ────────────────────────────────────────────────────────────
class SentimentScorer:
    """Multi-source sentiment — only positive posts feed into scores."""

    def __init__(self, known_tickers: Set[str]):
        self.tickers = {t.upper().replace(".", "-") for t in known_tickers}
        self.mentions: Dict[str, List[dict]] = defaultdict(list)

    # ── Extraction ───────────────────────────────────────────────────────────
    def extract_tickers(self, text: str) -> Set[str]:
        """Extract ticker mentions from text."""
        found = set()
        if not text:
            return found
        text_upper = text.upper()

        # $TICKER format
        for match in re.finditer(r"\$([A-Za-z]{1,6})\b", text):
            t = match.group(1).upper()
            if t in self.tickers:
                found.add(t)

        # Bare 3-5 letter uppercase words
        STOPWORDS = {
            "CEO", "CFO", "CTO", "USD", "EPS", "GDP", "IPO", "ATH", "THE",
            "FOR", "AND", "NEW", "OLD", "ALL", "HAS", "HAD", "WAS", "WERE",
            "SAID", "SAYS", "WILL", "ARE", "BUT", "NOT", "THEIR", "THEY",
        }
        for match in re.finditer(r"\b([A-Z]{3,5})\b", text_upper):
            t = match.group(1)
            if t in self.tickers and t not in STOPWORDS:
                found.add(t)

        # Company name → ticker
        for name, ticker in NAME_TO_TICKER.items():
            if name.upper() in text_upper:
                t = ticker.upper()
                if t in self.tickers:
                    found.add(t)

        # Crypto by bare symbol
        for match in re.finditer(
            r"\b(BTC|ETH|SOL|XRP|DOGE|ADA|AVAX|LINK|DOT|TAO|LTC|SUI|NEAR|ICP|HBAR|UNI|APT|ARB|IMX|OP|STX|MKR|RENDER|FET|INJ|GRT|PEPE|WIF|BONK|FLOKI|SHIB)\b",
            text_upper,
        ):
            t = match.group(1)
            mapped = f"{t}-USD"
            if mapped in self.tickers:
                found.add(mapped)

        return found

    def process_item(self, item: dict):
        """Process a single content item — already confirmed positive upstream."""
        text = item.get("text", "")
        weight = item.get("weight", 1.0)
        source = item.get("source", "unknown")
        polarity = score_text(text)

        # Second safety check — silently drop anything that somehow got negative
        if polarity <= 0:
            return

        tickers = self.extract_tickers(text)
        for t in tickers:
            self.mentions[t].append({
                "text": text[:250],
                "polarity": polarity,
                "weight": weight,
                "source": source,
            })

    # ── Fetch orchestrator ───────────────────────────────────────────────────
    def fetch_all(self):
        """Fetch from all sources, filter for positive sentiment, score tickers."""
        sources = [
            ("cnbc", fetch_cnbc),
            ("bloomberg", fetch_bloomberg),
            ("yahoo_finance", fetch_yahoo_finance),
            ("benzinga", fetch_benzinga),
            ("google_news", fetch_google_news),
        ]

        total_items = 0
        for name, fn in sources:
            try:
                items = fn()
                for item in items:
                    self.process_item(item)
                total_items += len(items)
                print(f"      [sentiment] {name}: {len(items)} processed")
            except Exception as e:
                print(f"      [sentiment] {name} failed: {e}")

        # ── WSB via Reddit OAuth (sync call, kept last as it may be slower) ───
        try:
            wsb_posts = fetch_wsb_positive(limit=40)
            for post in wsb_posts:
                self.process_item(post)
            total_items += len(wsb_posts)
            print(f"      [sentiment] wsb: {len(wsb_posts)} processed")
        except Exception as e:
            print(f"      [sentiment] wsb failed: {e}")

        print(f"      [sentiment] TOTAL positive items processed: {total_items}")

    # ── Scoring ──────────────────────────────────────────────────────────────
    def get_scores(self) -> Dict[str, dict]:
        """Compute final sentiment scores for tickers with positive mentions."""
        scores = {}
        for ticker, mentions in self.mentions.items():
            if not mentions:
                continue

            total_weight = sum(m["weight"] for m in mentions)
            if total_weight <= 0:
                continue

            avg_polarity = sum(m["polarity"] * m["weight"] for m in mentions) / total_weight
            mention_count = len(mentions)

            # Source breakdown
            sources = defaultdict(int)
            for m in mentions:
                sources[m["source"]] += 1

            # Popularity boost: log-scale mention volume → 0-8 pts
            pop_boost = min(8, (mention_count ** 0.5) * 1.5)

            # Score base: 50 neutral, polarity shifts ±30, popularity adds up to 8
            raw = 50 + (avg_polarity * 30) + pop_boost
            sentiment_score = max(0, min(100, raw))

            scores[ticker] = {
                "sentiment_score": round(sentiment_score, 1),
                "avg_polarity": round(avg_polarity, 3),
                "mentions": mention_count,
                "weighted_mentions": round(total_weight, 1),
                "sources": dict(sources),
                "sample": mentions[0]["text"][:120] if mentions else "",
            }

        return scores


# ─── Convenience wrapper (sync version for full_pipeline.py) ─────────────────
def fetch_sentiment(tickers: Set[str]) -> Dict[str, dict]:
    """One-shot sync sentiment for a set of tickers."""
    scorer = SentimentScorer(tickers)
    scorer.fetch_all()
    return scorer.get_scores()


# ─── Legacy async wrapper (if anything still calls it) ───────────────────────
import aiohttp

async def fetch_sentiment_async(session: aiohttp.ClientSession, tickers: Set[str]) -> Dict[str, dict]:
    """Async wrapper that ignores the session arg (all sources are sync now)."""
    return fetch_sentiment(tickers)
