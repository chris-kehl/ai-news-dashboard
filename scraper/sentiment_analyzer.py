#!/usr/bin/env python3
"""
Multi-Source Sentiment Analyzer — WSB, Reddit, News.

All free tier — no paid APIs required.
"""
import asyncio
import json
import re
from collections import defaultdict
from datetime import datetime, timezone
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
    "Accept": "application/json, text/html",
    "Accept-Language": "en-US,en;q=0.9",
}
TIMEOUT = aiohttp.ClientTimeout(total=15)

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

# ─── Top company name → ticker mapping ───────────────────────────────────────
NAME_TO_TICKER = {
    "APPLE": "AAPL", "TESLA": "TSLA", "NVIDIA": "NVDA", "MICROSOFT": "MSFT",
    "AMAZON": "AMZN", "GOOGLE": "GOOGL", "GOOG": "GOOGL", "ALPHABET": "GOOGL",
    "META": "META", "FACEBOOK": "META", "BERKSHIRE": "BRK-B",
    "BERKSHIRE HATHAWAY": "BRK-B", "JPMORGAN": "JPM", "JOHNSON": "JNJ",
    "JOHNSON AND JOHNSON": "JNJ", "VISA": "V", "MASTERCARD": "MA",
    "WALMART": "WMT", "PROCTER": "PG", "PROCTER AND GAMBLE": "PG",
    "UNITEDHEALTH": "UNH", "HOME DEPOT": "HD", "CHEVRON": "CVX",
    "LILLY": "LLY", "ELI LILLY": "LLY", "PFIZER": "PFE",
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
    # Crypto
    "BITCOIN": "BTC-USD", "ETHEREUM": "ETH-USD", "SOLANA": "SOL-USD",
    "RIPPLE": "XRP-USD", "DOGECOIN": "DOGE-USD", "CARDANO": "ADA-USD",
    "AVALANCHE": "AVAX-USD", "CHAINLINK": "LINK-USD", "POLKADOT": "DOT-USD",
    "BITTENSOR": "TAO-USD", "LITECOIN": "LTC-USD", "NEAR": "NEAR-USD",
    "UNISWAP": "UNI-USD", "APTOS": "APT-USD", "BINANCE": "BNB-USD",
    "SHIBA INU": "SHIB-USD", "PEPE": "PEPE-USD", "SUI": "SUI-USD",
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


# ═══════════════════════════════════════════════════════════════════════════════
#  FREE PATH #1: Yahoo Finance RSS (always works, no auth needed)
# ═══════════════════════════════════════════════════════════════════════════════
async def fetch_yahoo_finance(session: aiohttp.ClientSession) -> List[dict]:
    """Fetch Yahoo Finance news RSS titles. 100% free."""
    url = "https://finance.yahoo.com/news/rssindex"
    try:
        async with session.get(url, headers=HEADERS, timeout=TIMEOUT) as r:
            text = await r.text()
            titles = re.findall(r"<title>(.+?)</title>", text)
            results = []
            for t in titles[1:]:  # skip channel title
                t_clean = (
                    t.replace("<![CDATA[", "")
                    .replace("]]>", "")
                    .replace("&amp;", "&")
                    .strip()
                )
                if t_clean and len(t_clean) > 15 and "Yahoo Finance" not in t_clean:
                    results.append({"text": t_clean, "weight": 1.0, "source": "yahoo_finance"})
            print(f"      [yahoo] Fetched {len(results)} headlines")
            return results
    except Exception as e:
        print(f"      [yahoo] Error: {e}")
        return []


# ═══════════════════════════════════════════════════════════════════════════════
#  FREE PATH #2: Finviz News (HTML scrape, no auth)
# ═══════════════════════════════════════════════════════════════════════════════
async def fetch_finviz_news(session: aiohttp.ClientSession) -> List[dict]:
    """Scrape latest headlines from Finviz. 100% free."""
    # Use the news feed endpoint which is simpler HTML
    urls = [
        "https://finviz.com/news.ashx",
        "https://finviz.com/news.ashx?v=2",
    ]
    for url in urls:
        try:
            async with session.get(url, headers=HEADERS, timeout=TIMEOUT) as r:
                text = await r.text()
                # Finviz headlines are in simple <a> links in table cells
                # Pattern 1: <a href="...">TEXT</a> in news rows
                headlines = re.findall(
                    r'<a[^>]+href="https?://[^"]+"[^>]*>([^<]{12,200})</a>',
                    text,
                )
                # Pattern 2: broader catch
                if len(headlines) < 5:
                    headlines = re.findall(
                        r'>([^<]{20,200}[A-Z][a-z]+[^<]{5,100})<',
                        text[:40000],
                    )
                seen = set()
                results = []
                for h in headlines:
                    h = h.strip()
                    # Filter out navigation/menu items
                    if (h and h not in seen and 15 < len(h) < 250
                        and h.lower() not in {"news", "home", "screener", "maps",
                                               "groups", "portfolio", "insider",
                                               "futures", "forex", "crypto", "backtests"}
                        and not h.startswith(("http", "www", "finviz"))):
                        seen.add(h)
                        results.append({"text": h, "weight": 1.2, "source": "finviz"})
                if results:
                    print(f"      [finviz] Fetched {len(results)} headlines")
                    return results
        except Exception as e:
            print(f"      [finviz] {url} error: {e}")
    return []


# ═══════════════════════════════════════════════════════════════════════════════
#  FREE PATH #3: 24/7 Wall St (HTML scrape, no auth)
# ═══════════════════════════════════════════════════════════════════════════════
async def fetch_247wallst(session: aiohttp.ClientSession) -> List[dict]:
    """Scrape headlines from 24/7 Wall Street. Free financial news."""
    url = "https://247wallst.com/"
    try:
        async with session.get(url, headers=HEADERS, timeout=TIMEOUT) as r:
            text = await r.text()
            headlines = re.findall(
                r'<h[1-3][^>]*>(.*?)</h[1-3]>',
                text,
                re.DOTALL | re.IGNORECASE,
            )
            seen = set()
            results = []
            for h in headlines:
                h_clean = re.sub(r"<[^>]+>", "", h).strip()
                if h_clean and h_clean not in seen and 20 < len(h_clean) < 250:
                    seen.add(h_clean)
                    results.append({"text": h_clean, "weight": 0.9, "source": "247wallst"})
            print(f"      [247wallst] Fetched {len(results)} headlines")
            return results
    except Exception as e:
        print(f"      [247wallst] Error: {e}")
        return []


# ═══════════════════════════════════════════════════════════════════════════════
#  FREE PATH #4: MarketWatch latest (HTML scrape, no auth)
# ═══════════════════════════════════════════════════════════════════════════════
async def fetch_marketwatch(session: aiohttp.ClientSession) -> List[dict]:
    """Scrape latest headlines from MarketWatch. Free tier."""
    url = "https://www.marketwatch.com/latest-news"
    try:
        async with session.get(url, headers=HEADERS, timeout=TIMEOUT) as r:
            text = await r.text()
            # Try multiple patterns for MarketWatch
            results = []
            seen = set()
            
            # Pattern 1: article headline links
            for pattern in [
                r'<a[^>]+href="https://www\.marketwatch\.com/story/[^"]*"[^>]*>([^<]{20,250})</a>',
                r'<a[^>]+class="link"[^>]*>([^<]{20,250})</a>',
                r'<h3[^>]*class="[^"]*article[^"]*"[^>]*>.*?<a[^>]*>([^<]{20,250})</a>.*?</h3>',
                r'<h3[^>]*>.*?<a[^>]*>([^<]{20,250})</a>.*?</h3>',
                r'"headline":"([^"]{20,300})"',
            ]:
                matches = re.findall(pattern, text[:80000], re.DOTALL | re.IGNORECASE)
                for h in matches:
                    h_clean = re.sub(r"<[^>]+>", "", h).strip()
                    if h_clean and h_clean not in seen and 20 < len(h_clean) < 250:
                        seen.add(h_clean)
                        results.append({"text": h_clean, "weight": 1.0, "source": "marketwatch"})
                if len(results) >= 10:
                    break
            
            print(f"      [marketwatch] Fetched {len(results)} headlines")
            return results
    except Exception as e:
        print(f"      [marketwatch] Error: {e}")
        return []


# ═══════════════════════════════════════════════════════════════════════════════
#  REDDIT via RSS (WSB only — works! Other subs hit 429 rate limit)
# ═══════════════════════════════════════════════════════════════════════════════
async def fetch_wsb_rss(session: aiohttp.ClientSession, limit: int = 50) -> List[dict]:
    """Fetch WSB posts via Reddit RSS feed. No auth needed, works reliably."""
    url = f"https://www.reddit.com/r/wallstreetbets/new/.rss?limit={limit}"
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; NewsBot/1.0)",
        "Accept": "application/rss+xml, application/xml",
    }
    try:
        async with session.get(url, headers=headers, timeout=TIMEOUT) as r:
            if r.status != 200:
                print(f"      [reddit] WSB RSS HTTP {r.status}")
                return []
            text = await r.text()
            entries = text.split("<entry>")[1:]
            posts = []
            for entry in entries:
                title_m = re.search(r"<title>([^<]+)</title>", entry)
                pub_m = re.search(r"<published>([^<]+)</published>", entry)
                content_m = re.search(
                    r'<content type="html">(.+?)</content>', entry, re.DOTALL
                )

                if not (title_m and pub_m):
                    continue

                # Parse timestamp
                dt_str = pub_m.group(1).replace("Z", "+00:00")
                try:
                    dt = datetime.fromisoformat(dt_str)
                    now = datetime.now(timezone.utc)
                    age_hours = max(0.1, (now - dt).total_seconds() / 3600)
                except Exception:
                    age_hours = 12.0

                # Recency weight: newest = 4x boost, decays to 1x at 24h+
                recency_weight = min(4.0, 1.0 + (24 / max(1, age_hours)))

                title = title_m.group(1)

                # Extract body text from escaped HTML content
                body = ""
                if content_m:
                    raw = content_m.group(1)
                    raw = (
                        raw.replace("&lt;", "<")
                        .replace("&gt;", ">")
                        .replace("&amp;", "&")
                        .replace("&quot;", '\"')
                        .replace("&#32;", " ")
                    )
                    body = re.sub(r"<[^>]+>", " ", raw)
                    body = re.sub(r"\s+", " ", body).strip()

                full_text = title
                if body and len(body) > 20:
                    full_text += " " + body[:500]

                posts.append({
                    "text": full_text,
                    "weight": recency_weight,
                    "source": "reddit_wallstreetbets",
                    "age_hours": round(age_hours, 1),
                })

            # Sort newest first
            posts.sort(key=lambda x: x.get("age_hours", 99))
            print(f"      [reddit] WSB RSS: {len(posts)} posts (recency-weighted)")
            return posts
    except Exception as e:
        print(f"      [reddit] WSB RSS error: {e}")
        return []


# Legacy: Reddit JSON API — currently blocked by 403/429
async def fetch_reddit_sub(session: aiohttp.ClientSession, subreddit: str, limit: int = 25):
    """Reddit JSON API — currently returns 403 without OAuth. Use RSS instead for WSB."""
    url = f"https://www.reddit.com/r/{subreddit}/new.json?limit={limit}"
    try:
        async with session.get(url, headers=HEADERS, timeout=TIMEOUT) as r:
            if r.status in (403, 429):
                print(f"      [reddit] r/{subreddit} blocked ({r.status}) — skipping")
                return []
            if r.status != 200:
                return []
            data = await r.json()
            posts = []
            for child in data.get("data", {}).get("children", []):
                post = child.get("data", {})
                title = post.get("title", "")
                body = post.get("selftext", "")
                if not title:
                    continue
                ups = post.get("ups", 0)
                comments = post.get("num_comments", 0)
                weight = 1.0 + (ups / 400) + (comments / 80)
                posts.append({
                    "text": title + " " + body,
                    "weight": min(weight, 8.0),
                    "source": f"reddit_{subreddit}",
                    "ups": ups,
                    "comments": comments,
                })
            return posts
    except Exception as e:
        print(f"      [reddit] r/{subreddit} error: {e}")
        return []


# ─── Orchestrator ────────────────────────────────────────────────────────────
class SentimentScorer:
    """Fetch multi-source sentiment and score all tracked assets."""

    def __init__(self, known_tickers: Set[str]):
        self.tickers = {t.upper().replace(".", "-") for t in known_tickers}
        self.mentions: Dict[str, List[dict]] = defaultdict(list)

    # ── Extraction ───────────────────────────────────────────────────────────
    def extract_tickers(self, text: str) -> Set[str]:
        """Extract ticker mentions from a text block."""
        found = set()
        if not text:
            return found

        text_upper = text.upper()

        # 1. $TICKER format
        for match in re.finditer(r"\$([A-Za-z]{1,6})\b", text):
            t = match.group(1).upper()
            if t in self.tickers:
                found.add(t)

        # 2. Bare 3-5 letter uppercase words
        for match in re.finditer(r"\b([A-Z]{3,5})\b", text_upper):
            t = match.group(1)
            if t in self.tickers and t not in {"CEO", "CFO", "CTO", "USD", "EPS", "GDP", "IPO", "ATH", "ATHS", "THE", "FOR", "AND", "NEW", "OLD", "ALL", "CEO", "CFO", "CTO", "USD", "EPS", "GDP", "IPO", "ATH", "THE", "AND", "FOR", "ARE", "BUT", "NOT", "NEW", "OLD", "ALL", "HAS", "HAD", "WAS", "WERE", "ITS", "THEIR", "THEY", "SAID", "SAYS", "WILL"}:
                found.add(t)

        # 3. Company name → ticker
        for name, ticker in NAME_TO_TICKER.items():
            if name.upper() in text_upper:
                t = ticker.upper()
                if t in self.tickers:
                    found.add(t)

        # 4. Crypto by symbol
        for match in re.finditer(
            r"\b(BTC|ETH|SOL|XRP|DOGE|ADA|AVAX|LINK|DOT|TAO|LTC|SUI|NEAR|ICP|HBAR|UNI|APT|ARB|IMX|OP|STX|MKR|HYPE|RENDER|FET|INJ|GRT|PEPE|WIF|BONK|FLOKI|SHIB)\b",
            text_upper,
        ):
            t = match.group(1)
            mapped = f"{t}-USD"
            if mapped in self.tickers:
                found.add(mapped)

        return found

    def process_item(self, item: dict):
        """Process a single content item."""
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
            })

    # ── Fetch orchestrator (all working free sources) ─────────────────────────
    async def fetch_all(self, session: aiohttp.ClientSession):
        """Fetch from all working free sources."""
        sources = [
            ("yahoo_finance", fetch_yahoo_finance),
            ("finviz", fetch_finviz_news),
            ("247wallst", fetch_247wallst),
            ("marketwatch", fetch_marketwatch),
        ]

        total_items = 0
        for name, fn in sources:
            try:
                items = await fn(session)
                for item in items:
                    self.process_item(item)
                total_items += len(items)
                print(f"      [sentiment] {name}: processed {len(items)} items")
            except Exception as e:
                print(f"      [sentiment] {name} failed: {e}")

        # ── WSB via RSS (works!) ──────────────────────────────────────────────
        try:
            wsb_posts = await fetch_wsb_rss(session, limit=50)
            for post in wsb_posts:
                self.process_item(post)
            total_items += len(wsb_posts)
            print(f"      [sentiment] Reddit WSB: processed {len(wsb_posts)} posts")
        except Exception as e:
            print(f"      [sentiment] WSB RSS failed: {e}")

        # Fallback: attempt other Reddit subs via JSON (rarely works)
        for sub in ["stocks", "investing", "cryptocurrency"]:
            try:
                posts = await fetch_reddit_sub(session, sub, limit=25)
                for post in posts:
                    self.process_item(post)
                total_items += len(posts)
                if posts:
                    print(f"      [sentiment] Reddit r/{sub}: processed {len(posts)} posts")
            except Exception:
                pass

        print(f"      [sentiment] Total items processed: {total_items}")

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
