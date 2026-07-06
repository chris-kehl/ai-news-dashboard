#!/usr/bin/env python3
"""Business section scraper.

Primary: Google News Business RSS (fast, reliable, no API key).
Secondary: r/business via Reddit RSS (rate-limited, blocked sometimes).
Fallback: DDG news search.
"""

import requests
import xml.etree.ElementTree as ET
import time
from datetime import datetime
from scraper_utils import fetch_with_retry

BROWSER = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9',
}

# Google News Business topic RSS (stable, no auth needed)
GOOGLE_NEWS_BUSINESS = "https://news.google.com/rss/topics/CAAqJggKIiBDQkFTRWdvSUwyMHZNRGx6TVdZU0FtVnVHZ0pWVXlnQVAB?hl=en-US&gl=US&ceid=US:en"

# Reddit RSS feeds for business/tech subreddits
REDDIT_FEEDS = [
    ("https://www.reddit.com/r/business/top/.rss?t=day&limit=15", "r/business"),
    ("https://www.reddit.com/r/investing/top/.rss?t=day&limit=15", "r/investing"),
]


def _parse_google_news_rss(url, limit=12):
    """Parse Google News RSS. Titles come as 'Headline - Source'."""
    items = []
    try:
        r = fetch_with_retry(url, headers=BROWSER, timeout=20, max_retries=2, backoff_base=2.0)
        if r is None:
            return items
        root = ET.fromstring(r.content)
        for item in root.findall(".//item")[:limit]:
            title = item.findtext("title", "")
            link = item.findtext("link", "")
            pub = item.findtext("pubDate", "")
            source_el = item.find("source")
            source = source_el.text if source_el is not None else ""
            if not title:
                continue
            # Strip source suffix from title if present ("Title - Source")
            clean_title = title.strip()[:200]
            if source and clean_title.endswith(f" - {source}"):
                clean_title = clean_title[:-(len(source) + 3)].strip()
            items.append({
                "title": clean_title,
                "url": link.strip() if link else "#",
                "source": source or "Google News",
                "category": "business",
                "published": pub.strip()[:17] if pub else "",
                "description": "",
                "score": 0,
                "author": "",
            })
    except Exception as e:
        print(f"      Google News business error: {e}")
    return items


def _parse_reddit_rss(feed_url, source_name, limit=6):
    """Parse a Reddit public RSS feed."""
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


def _get_ddg_business(limit=6):
    """DDG news search fallback."""
    try:
        from ddg_scraper import ddg_news
        results = ddg_news("business news economy markets", max_results=limit, cache_key="business_ddg")
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
    except Exception as e:
        print(f"      DDG business error: {e}")
        return []


def get_business_data(limit_per_source=8):
    """Aggregate business headlines from Google News + Reddit + DDG."""
    print("\n[BUSINESS] Fetching business section...")

    # 1. Google News (primary — most reliable)
    gn_items = _parse_google_news_rss(GOOGLE_NEWS_BUSINESS, limit=limit_per_source)
    print(f"       Google News business: {len(gn_items)}")

    # 2. Reddit (secondary)
    reddit_items = []
    for url, name in REDDIT_FEEDS:
        reddit_items.extend(_parse_reddit_rss(url, name, limit=limit_per_source))
        time.sleep(0.5)
    print(f"       Reddit business: {len(reddit_items)}")

    # 3. DDG fallback (only if primary sources are weak)
    ddg_items = []
    if len(gn_items) < 3:
        ddg_items = _get_ddg_business(limit=limit_per_source)
        print(f"       DDG business fallback: {len(ddg_items)}")

    # Merge with dedup — Google News first (highest quality), then Reddit, then DDG
    seen = set()
    merged = []
    for it in gn_items + reddit_items + ddg_items:
        key = it["title"].lower()[:60]
        if key not in seen:
            seen.add(key)
            merged.append(it)

    return merged[:limit_per_source * 2]


if __name__ == "__main__":
    biz = get_business_data()
    print(f"Total business items: {len(biz)}")
    for b in biz[:8]:
        print(f"[{b['source']}] {b['title'][:90]}...")
