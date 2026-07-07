#!/usr/bin/env python3
"""Alpha Vantage News & Sentiment scraper.

Endpoint: NEWS_SENTIMENT — returns news articles with ticker-level sentiment.
Free tier: 5 calls/min, 500/day. Cache 15 min to stay well under limits.

Each article has ticker_sentiment array:
  [{"ticker": "AAPL", "ticker_sentiment_score": 0.234, ...}, ...]

We extract the tickers and scores, aggregate by ticker, and emit items
that can be fed into the scrolling ticker + signals cards.
"""

import os
import json
import time
from datetime import datetime
from scraper_utils import fetch_json_with_retry, load_scraper_cache, save_scraper_cache

ALPHA_VANTAGE_API_KEY = os.environ.get("ALPHA_VANTAGE_API_KEY", "")
AV_NEWS_URL = "https://www.alphavantage.co/query"

# Topics to rotate through on successive calls (prevents stale results)
TOPICS = ["technology", "financial_markets", "economy_monetary", "mergers_and_acquisitions"]


def fetch_av_sentiment(topic: str = "technology", limit: int = 50):
    """Fetch Alpha Vantage NEWS_SENTIMENT for a topic. Returns raw feed payload."""
    if not ALPHA_VANTAGE_API_KEY:
        print("[AV] No ALPHA_VANTAGE_API_KEY — skipping")
        return {}

    cache_name = f"av_sentiment_{topic}"
    cached = load_scraper_cache(cache_name, max_age_minutes=15)
    if cached:
        return cached

    params = {
        "function": "NEWS_SENTIMENT",
        "topics": topic,
        "sort": "LATEST",
        "limit": str(limit),
        "apikey": ALPHA_VANTAGE_API_KEY,
    }

    data = fetch_json_with_retry(
        AV_NEWS_URL,
        params=params,
        timeout=20,
        max_retries=2,
        backoff_base=3.0,
    )
    if data and "feed" in data:
        save_scraper_cache(cache_name, data)
    return data or {}


def extract_ticker_sentiment(feed_data: dict, max_items: int = 20):
    """Aggregate ticker sentiment from AV feed into ticker-level items.

    Returns list of dicts:
      {symbol, price: None, change: avg_score, sentiment_label, headline}
    """
    feed = feed_data.get("feed", [])
    if not feed:
        return []

    # Collect all (ticker, score, label) tuples per article
    ticker_scores = {}
    headlines = {}
    for article in feed:
        ts_list = article.get("ticker_sentiment", [])
        title = article.get("title", "")[:120]
        for ts in ts_list:
            sym = ts.get("ticker", "").upper()
            score_str = ts.get("ticker_sentiment_score", "0")
            label = ts.get("ticker_sentiment_label", "Neutral")
            if not sym:
                continue
            try:
                score = float(score_str)
            except (ValueError, TypeError):
                continue
            if sym not in ticker_scores:
                ticker_scores[sym] = []
                headlines[sym] = title
            ticker_scores[sym].append((score, label))

    # Aggregate: average score, most frequent label
    items = []
    for sym, scores in ticker_scores.items():
        avg = sum(s[0] for s in scores) / len(scores)
        labels = {}
        for _, lab in scores:
            labels[lab] = labels.get(lab, 0) + 1
        dominant_label = max(labels.items(), key=lambda kv: kv[1])[0]
        items.append({
            "symbol": sym,
            "price": 0,  # no price from AV; ticker renderer can skip
            "change": round(avg * 100, 2),  # scale to pct-like for ticker
            "sentiment_label": dominant_label,
            "headline": headlines.get(sym, ""),
            "article_count": len(scores),
            "category": "av_sentiment",
        })

    # Sort by absolute sentiment strength, strongest first
    items.sort(key=lambda x: abs(x["change"]), reverse=True)
    return items[:max_items]


def get_av_ticker_sentiment_items(max_items: int = 20):
    """Master function: fetch AV news sentiment and return ticker items.
    """
    # Rotate topic based on minute to spread calls across topics
    topic = TOPICS[datetime.utcnow().minute % len(TOPICS)]
    raw = fetch_av_sentiment(topic=topic, limit=50)
    return extract_ticker_sentiment(raw, max_items=max_items)


def add_av_to_ticker(ticker_items: list, max_sentiment: int = 12):
    """Interleave AV sentiment items into existing ticker items.

    Returns augmented list. Sentiment items get a prefix so the renderer
    can display them differently.
    """
    av_items = get_av_ticker_sentiment_items(max_items=max_sentiment)
    if not av_items:
        return ticker_items

    # Map to ticker-compatible dict with sentinel for renderer
    enriched = []
    for it in ticker_items:
        enriched.append(dict(it, av_news=False))
    for it in av_items:
        enriched.append(dict(it, av_news=True))

    # Re-sort: keep indices/futures/crypto first, then AV sentiment, then stocks
    # Use category ordering
    order = {
        "av_sentiment": 0,
        "index": 1,
        "futures": 2,
        "crypto": 3,
        "stock": 4,
    }
    # Tag existing items with category if missing
    for e in enriched:
        if "category" not in e:
            sym = e.get("symbol", "")
            if sym in ("SPX", "DJI", "IXIC", "VIX", "RUT"):
                e["category"] = "index"
            elif sym.endswith("=F"):
                e["category"] = "futures"
            elif sym in ("BTC", "ETH", "SOL", "DOGE", "AVAX", "LINK", "TAO"):
                e["category"] = "crypto"
            else:
                e["category"] = "stock"

    enriched.sort(key=lambda x: order.get(x.get("category", "stock"), 99))
    return enriched


if __name__ == "__main__":
    if not ALPHA_VANTAGE_API_KEY:
        print("Set ALPHA_VANTAGE_API_KEY env var to test")
    else:
        items = get_av_ticker_sentiment_items()
        print(f"AV Sentiment items: {len(items)}")
        for it in items[:12]:
            label = it["sentiment_label"]
            score = it["change"]
            print(f"  {it['symbol']:8} score={score:>+7.2f}  {label:10}  {it['headline'][:60]}...")
