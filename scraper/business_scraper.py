#!/usr/bin/env python3
"""Business section scraper — pulls top business/tech/economy stories from
Reddit (r/business, r/investing, r/stocks), DDG news (business queries),
and Nitter/X (business news search).  No API keys required.
"""

import requests
import xml.etree.ElementTree as ET
import time
import random
import re
from urllib.parse import quote

from scraper_utils import fetch_with_retry
from ddg_scraper import ddg_news

try:
    from x_scraper import _working_nitter, _search_nitter
except ImportError:
    _working_nitter = None
    _search_nitter = None

BROWSER = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9',
}

# Business subreddits with public RSS
def _parse_reddit_rss(feed_url, source_name, limit=6):
    """Parse a Reddit RSS feed into unified items."""
    items = []
    try:
        r = fetch_with_retry(feed_url, timeout=15, max_retries=2, backoff_base=2.0)
        if r is None:
            return items
        root = ET.fromstring(r.content)
        for item in root.findall(".//item")[:limit * 2]:
            title = item.findtext("title", "")
            link = item.findtext("link", "")
            pub = item.findtext("pubDate", "")
            if not title:
                continue
            items.append({
                "title": title.strip()[:200],
                "url": link.strip() if link else "#",
                "source": source_name,
                "category": "business",
                "published": pub.strip()[:17] if pub else "",
                "description": "",
                "score": 0,
                "author": "",
            })
    except Exception as e:
        print(f"      Reddit {source_name} error: {e}")
    return items[:limit]


def _get_business_reddit(limit=6):
    """Pull top posts from business subreddits via RSS."""
    feeds = [
        ("https://www.reddit.com/r/business/top/.rss?t=day&limit=15", "r/business"),
        ("https://www.reddit.com/r/investing/top/.rss?t=day&limit=15", "r/investing"),
        ("https://www.reddit.com/r/stocks/top/.rss?t=day&limit=15", "r/stocks"),
    ]
    all_items = []
    seen = set()
    for url, name in feeds:
        for it in _parse_reddit_rss(url, name, limit=limit):
            key = it["title"].lower()[:60]
            if key not in seen:
                seen.add(key)
                it["score"] = 100  # distinguish Reddit items
                all_items.append(it)
        time.sleep(0.5)
    return all_items[:limit]


def _get_business_ddg(limit=6):
    """DDG news search for top business headlines."""
    results = ddg_news("top business news today economy", max_results=limit, cache_key="business_ddg")
    items = []
    for r in results:
        items.append({
            "title": r.get("title", "")[:200],
            "url": r.get("url", "").strip() or "#",
            "source": r.get("source", "DDG")[:40],
            "category": "business",
            "published": r.get("published", "")[:20],
            "description": r.get("description", "")[:300],
            "score": 0,
            "author": "",
        })
    return items


def _get_business_x(limit=6):
    """Search Nitter for business-related tweets."""
    if _working_nitter is None or _search_nitter is None:
        return []
    try:
        base = _working_nitter()
        queries = ["business news", "economy today", "markets news"]
        all_posts = []
        seen = set()
        for q in queries:
            posts = _search_nitter(base, q, max_results=limit)
            for p in posts:
                key = p["text"].lower()[:50]
                if key not in seen:
                    seen.add(key)
                    all_posts.append({
                        "title": p["text"][:200],
                        "url": p.get("url", f"https://twitter.com/{p['author'].lstrip('@')}"),
                        "source": p.get("author", "X"),
                        "category": "business",
                        "published": p.get("date", ""),
                        "description": p["text"][:300],
                        "score": 0,
                        "author": p.get("author", ""),
                    })
            time.sleep(1)
        return all_posts[:limit]
    except Exception as e:
        print(f"      Business X search error: {e}")
        return []


def get_business_data(limit_per_source=6):
    """Aggregate business news from Reddit, DDG news, and X."""
    print("\n[BUSINESS] Fetching business section...")
    reddit_items = _get_business_reddit(limit=limit_per_source)
    print(f"       Reddit business: {len(reddit_items)}")

    ddg_items = _get_business_ddg(limit=limit_per_source)
    print(f"       DDG business: {len(ddg_items)}")

    x_items = _get_business_x(limit=limit_per_source)
    print(f"       X business: {len(x_items)}")

    # Merge with Reddit posts first (most reliable), then DDG, then X
    seen = set()
    merged = []
    for it in reddit_items + ddg_items + x_items:
        key = it["title"].lower()[:60]
        if key not in seen:
            seen.add(key)
            merged.append(it)

    return merged[:limit_per_source * 2]


if __name__ == "__main__":
    biz = get_business_data()
    print(f"Total business items: {len(biz)}")
    for b in biz[:6]:
        print(f"[{b['source']}] {b['title'][:90]}...")
