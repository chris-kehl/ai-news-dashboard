#!/usr/bin/env python3
"""
Multi-Source Sentiment Analyzer — WSB, Reddit, CNBC, Yahoo Finance.

Feeds sentiment signals into the weekly pick scorer.
Free tier only — no paid APIs required.
"""
import asyncio
import json
import re
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set

import aiohttp

# ─── Config ──────────────────────────────────────────────────────────────────
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
}
TIMEOUT = aiohttp.ClientTimeout(total=18)

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
    "partnership", "contract win", "fda approval", "breakthrough",
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
]

# ─── Top company name → ticker mapping (news headlines often use names) ──────
NAME_TO_TICKER = {
    "APPLE": "AAPL", "TESLA": "TSLA", "NVIDIA": "NVDA", "MICROSOFT": "MSFT",
    "AMAZON": "AMZN", "GOOGLE": "GOOGL", "ALPHABET": "GOOGL", "META": "META",
    "FACEBOOK": "META", "BERKSHIRE": "BRK-B", "BERKSHIRE HATHAWAY": "BRK-B",
    "JPMORGAN": "JPM", "JOHNSON": "JNJ", "JOHNSON & JOHNSON": "JNJ",
    "VISA": "V", "MASTERCARD": "MA", "WALMART": "WMT", "PROCTER": "PG",
    "PROCTER & GAMBLE": "PG", "UNITEDHEALTH": "UNH", "HOME DEPOT": "HD",
    "CHEVRON": "CVX", "LILLY": "LLY", "ELI LILLY": "LLY", "PFIZER": "PFE",
    "COCA-COLA": "KO", "COCACOLA": "KO", "PEPSI": "PEP", "PEPSICO": "PEP",
    "MCDONALD": "MCD", "MCDONALDS": "MCD", "DISNEY": "DIS",
    "WALT DISNEY": "DIS", "NETFLIX": "NFLX", "AMD": "AMD", "INTEL": "INTC",
    "QUALCOMM": "QCOM", "CISCO": "CSCO", "ORACLE": "ORCL", "SALESFORCE": "CRM",
    "ADOBE": "ADBE", "PAYPAL": "PYPL", "UBER": "UBER", "LYFT": "LYFT",
    "AIRBNB": "ABNB", "COINBASE": "COIN", "ROBINHOOD": "HOOD", "SNAP": "SNAP",
    "SQUARE": "SQ", "BLOCK": "SQ", "BOSTON SCIENTIFIC": "BSX",
    "STRYKER": "SYK", "THERMO FISHER": "TMO", "ABBOTT": "ABT",
    "DANAHER": "DHR", "MERCK": "MRK", "BRISTOL": "BMY",
    "BRISTOL-MYERS": "BMY", "GILEAD": "GILD", "REGENERON": "REGN",
    "MODERNA": "MRNA", "VERTEX": "VRTX", "BIOGEN": "BIIB",
    "EXXON": "XOM", "EXXONMOBIL": "XOM", "SHELL": "SHEL", "BP": "BP",
    "CONOCOPHILLIPS": "COP", "SCHLUMBERGER": "SLB", "PHILLIPS": "PSX",
    "GOLDMAN": "GS", "GOLDMAN SACHS": "GS", "MORGAN": "MS",
    "MORGAN STANLEY": "MS", "BANK OF AMERICA": "BAC", "CITIGROUP": "C",
    "CITI": "C", "WELLS": "WFC", "WELLS FARGO": "WFC",
    "AMERICAN EXPRESS": "AXP", "BLACKROCK": "BLK", "BLACKSTONE": "BX",
    "KKR": "KKR", "CARLYLE": "CG", "APOLLO": "APO", "BOEING": "BA",
    "LOCKHEED": "LMT", "LOCKHEED MARTIN": "LMT", "NORTHROP": "NOC",
    "RAYTHEON": "RTX", "GENERAL DYNAMICS": "GD", "CAT": "CAT",
    "CATERPILLAR": "CAT", "DEERE": "DE", "JOHN DEERE": "DE",
    "FORD": "F", "GENERAL MOTORS": "GM", "GM": "GM", "TOYOTA": "TM",
    "HONDA": "HMC", "NIKE": "NKE", "STARBUCKS": "SBUX", "COSTCO": "COST",
    "TARGET": "TGT", "LOWE": "LOW", "LOWES": "LOW", "BEST BUY": "BBY",
    "HOME DEPOT": "HD",
    # Crypto by name
    "BITCOIN": "BTC-USD", "ETHEREUM": "ETH-USD", "SOLANA": "SOL-USD",
    "RIPPLE": "XRP-USD", "DOGECOIN": "DOGE-USD", "CARDANO": "ADA-USD",
    "AVALANCHE": "AVAX-USD", "CHAINLINK": "LINK-USD", "POLKADOT": "DOT-USD",
    "BITTENSOR": "TAO-USD", "LITECOIN": "LTC-USD", "NEAR": "NEAR-USD",
    "UNISWAP": "UNI-USD", "APTOS": "APT-USD",
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
        return 0.0  # neutral
    return (bull - bear) / total


# ─── Async fetchers ──────────────────────────────────────────────────────────
async def fetch_reddit_sub(session: aiohttp.ClientSession, subreddit: str, limit: int = 50):
    """Fetch posts from a subreddit via public JSON API."""
    url = f"https://www.reddit.com/r/{subreddit}/new.json?limit={limit}"
    posts = []
    for attempt in range(3):
        try:
            async with session.get(url, headers=HEADERS, timeout=TIMEOUT) as r:
                if r.status == 429:
                    await asyncio.sleep(2 ** attempt)
                    continue
                if r.status != 200:
                    print(f"      [reddit] r/{subreddit} HTTP {r.status}")
                    return posts
                data = await r.json()
                for child in data.get("data", {}).get("children", []):
                    post = child.get("data", {})
                    title = post.get("title", "")
                    body = post.get("selftext", "")
                    if not title:
                        continue
                    ups = post.get("ups", 0)
                    comments = post.get("num_comments", 0)
                    # Engagement weight: popular posts get more say
                    weight = 1.0 + (ups / 400) + (comments / 80)
                    posts.append({
                        "text": title + " " + body,
                        "weight": min(weight, 8.0),  # cap weight
                        "source": f"reddit_{subreddit}",
                        "ups": ups,
                        "comments": comments,
                    })
                return posts
        except Exception as e:
            print(f"      [reddit] r/{subreddit} attempt {attempt+1} error: {e}")
            await asyncio.sleep(1)
    return posts


async def fetch_cnbc(session: aiohttp.ClientSession):
    """Scrape CNBC latest headlines."""
    url = "https://www.cnbc.com/world/?market=americas"
    try:
        async with session.get(url, headers=HEADERS, timeout=TIMEOUT) as r:
            text = await r.text()
            # Extract headlines from various CNBC article links
            headlines = re.findall(
                r'(?:headline|title|Card-title)[^>]*>([^<]{20,300})',
                text,
                re.IGNORECASE,
            )
            # Also try simple anchor extraction for article titles
            alt = re.findall(
                r'<a[^>]+href="/202[0-9]/[0-9]{2}/[0-9]{2}/[^"]*"[^>]*>([^<]{20,300})</a>',
                text,
            )
            headlines.extend(alt)
            seen = set()
            results = []
            for h in headlines:
                h = re.sub(r"<[^>]+>", "", h).strip()
                if h and h not in seen and len(h) > 20:
                    seen.add(h)
                    results.append({"text": h, "weight": 1.0, "source": "cnbc"})
            print(f"      [cnbc] Fetched {len(results)} headlines")
            return results
    except Exception as e:
        print(f"      [cnbc] Error: {e}")
        return []


async def fetch_yahoo_finance(session: aiohttp.ClientSession):
    """Fetch Yahoo Finance news RSS titles."""
    url = "https://finance.yahoo.com/news/rssindex"
    try:
        async with session.get(url, headers=HEADERS, timeout=TIMEOUT) as r:
            text = await r.text()
            titles = re.findall(r"<title>(.+?)</title>", text)
            results = []
            for t in titles[1:]:  # skip channel title
                t_clean = t.replace("<![CDATA[", "").replace("]]>", "").strip()
                if t_clean and len(t_clean) > 15:
                    results.append({"text": t_clean, "weight": 0.8, "source": "yahoo_finance"})
            print(f"      [yahoo] Fetched {len(results)} headlines")
            return results
    except Exception as e:
        print(f"      [yahoo] Error: {e}")
        return []


# ─── Orchestrator ────────────────────────────────────────────────────────────
class SentimentScorer:
    """Fetch multi-source sentiment and score all tracked assets."""

    def __init__(self, known_tickers: Set[str]):
        # Normalize tickers
        self.tickers = {t.upper().replace(".", "-") for t in known_tickers}
        self.mentions: Dict[str, List[dict]] = defaultdict(list)

    # ── Extraction ───────────────────────────────────────────────────────────
    def extract_tickers(self, text: str) -> Set[str]:
        """Extract ticker mentions from a text block."""
        found = set()
        if not text:
            return found

        text_upper = text.upper()

        # 1. $TICKER format (Reddit / WSB)
        for match in re.finditer(r"\$([A-Za-z\-]{1,6})\b", text):
            t = match.group(1).upper()
            if t in self.tickers:
                found.add(t)

        # 2. Bare 3-5 letter uppercase words (most tickers)
        for match in re.finditer(r"\b([A-Z]{3,5})\b", text_upper):
            t = match.group(1)
            if t in self.tickers:
                found.add(t)

        # 3. Company name → ticker mapping (news headlines)
        for name, ticker in NAME_TO_TICKER.items():
            if name.upper() in text_upper:
                t = ticker.upper()
                if t in self.tickers:
                    found.add(t)

        # 4. Explicit crypto symbols (any case, looser match)
        for match in re.finditer(
            r"\b(BTC|ETH|SOL|XRP|DOGE|ADA|AVAX|LINK|DOT|TAO|LTC|SUI|NEAR|ICP|HBAR|UNI|APT|ARB|IMX|OP|STX|MKR|HYPE|RENDER|FET|INJ|GRT|PEPE|WIF|BONK|FLOKI|SHIB|MATIC|ATOM|ALGO|THETA|FTM|SAND|MANA|AXS|FLOW|KLAY|XTZ|EOS|ZEC|XMR|DASH|NEO|IOTA|EGLD|QNT|KAS|TIA|SEI|STRK|ZRO|ENA|PENDLE|WLD|ARKM|PYTH|JUP|JTO|BOME|TNSR|DRIFT|ZEX|KMNO|CLORE|COOK|RON|PIXEL|BEAM|GMT|GALA|CHZ|ENJ|BAT|CRV|LDO|SSV|RPL|FXS|AAVE|COMP|YFI|SNX|1INCH|DYDX|GMX|VELO|MAGIC|TREMP|MAGA|TRUMP|PEOPLE)\b",
            text_upper,
        ):
            t = match.group(1)
            mapped = f"{t}-USD"
            if mapped in self.tickers:
                found.add(mapped)
            elif t in self.tickers:
                found.add(t)

        return found

    def process_item(self, item: dict):
        """Process a single content item (headline/post)."""
        text = item.get("text", "")
        weight = item.get("weight", 1.0)
        source = item.get("source", "unknown")
        polarity = score_text(text)
        tickers = self.extract_tickers(text)

        for t in tickers:
            self.mentions[t].append({
                "text": text[:250],
                "polarity": polarity,
                "weight": weight,
                "source": source,
                "ups": item.get("ups", 0),
                "comments": item.get("comments", 0),
            })

    # ── Fetch orchestrator ───────────────────────────────────────────────────
    async def fetch_all(self, session: aiohttp.ClientSession):
        """Fetch all sources and populate mentions."""
        # Reddit subs
        reddit_subs = [
            "wallstreetbets", "stocks", "investing",
            "SecurityAnalysis", "cryptocurrency", "pennystocks",
        ]
        reddit_tasks = [fetch_reddit_sub(session, s, limit=50) for s in reddit_subs]
        reddit_results = await asyncio.gather(*reddit_tasks, return_exceptions=True)
        reddit_count = 0
        for posts in reddit_results:
            if isinstance(posts, list):
                for post in posts:
                    self.process_item(post)
                reddit_count += len(posts)
            else:
                print(f"      [sentiment] Reddit batch error: {posts}")
        print(f"      [sentiment] Reddit total posts processed: {reddit_count}")

        # CNBC
        cnbc_items = await fetch_cnbc(session)
        for item in cnbc_items:
            self.process_item(item)

        # Yahoo Finance
        yahoo_items = await fetch_yahoo_finance(session)
        for item in yahoo_items:
            self.process_item(item)

    # ── Scoring ──────────────────────────────────────────────────────────────
    def get_scores(self) -> Dict[str, dict]:
        """Compute final sentiment scores for all tickers with mentions."""
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

            # Sentiment score base: 50 neutral, polarity shifts ±30, popularity adds up to 8
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


# ─── Convenience wrapper ─────────────────────────────────────────────────────
async def fetch_sentiment(session: aiohttp.ClientSession, tickers: Set[str]) -> Dict[str, dict]:
    """One-shot fetch sentiment for a set of tickers."""
    scorer = SentimentScorer(tickers)
    await scorer.fetch_all(session)
    return scorer.get_scores()
