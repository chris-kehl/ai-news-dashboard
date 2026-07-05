#!/usr/bin/env python3
"""Multi-source local news aggregator.

Tries NewsAPI first, then Bing News RSS, then regional RSS feeds.
Merges and deduplicates results. No single point of failure.
"""

import os
import requests
import xml.etree.ElementTree as ET
import re
import time
from datetime import datetime
from urllib.parse import urlparse

HEADERS = {
    "User-Agent": "AI-News-Dashboard/1.0 (Headlines only; bot)",
    "Accept": "application/rss+xml, application/atom+xml, text/xml, */*",
}

BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
}


def _normalize_url(url):
    """Strip tracking params for deduplication."""
    u = url.strip().lower()
    u = re.sub(r'\?utm_.*', '', u)
    u = re.sub(r'\?fbclid=.*', '', u)
    return u


def _dedup_insert(articles, new_articles, seen_urls, max_articles=20):
    """Add articles skipping duplicates by URL or near-identical title."""
    for a in new_articles:
        norm_url = _normalize_url(a.get("url", ""))
        title_key = a.get("title", "").lower().strip()[:40]
        key = norm_url or title_key
        if key in seen_urls:
            continue
        seen_urls.add(key)
        articles.append(a)
        if len(articles) >= max_articles:
            break


def _parse_rss(xml_bytes, source_label=""):
    """Parse RSS/Atom XML into article dicts."""
    articles = []
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return articles

    # Try Atom namespace first
    ns = {"atom": "http://www.w3.org/2005/Atom"}
    for entry in root.findall("atom:entry", ns):
        title_el = entry.find("atom:title", ns)
        link_el = entry.find("atom:link", ns)
        updated_el = entry.find("atom:updated", ns)

        title = title_el.text if title_el is not None else ""
        link = link_el.get("href") if link_el is not None else ""
        pub = updated_el.text if updated_el is not None else ""

        if title and link:
            articles.append({
                "title": title.strip()[:200],
                "url": link.strip(),
                "source": source_label,
                "published": pub[:16] if pub else "",
                "description": ""
            })

    # Try plain RSS items
    for item in root.findall(".//item"):
        title = item.findtext("title", "").strip()
        link = item.findtext("link", "").strip() or item.findtext("guid", "").strip()
        pub = item.findtext("pubDate", "")
        desc = item.findtext("description", "")[:200]

        # Skip non-news (ads, sports scores, etc) — crude filter
        if not title or len(title) < 10:
            continue
        if link:
            articles.append({
                "title": title[:200],
                "url": link,
                "source": source_label,
                "published": pub[:17] if pub else "",
                "description": desc.strip()
            })

    return articles


def newsapi(city, state, api_key):
    """Tier 1: NewsAPI.org."""
    try:
        url = "https://newsapi.org/v2/everything"
        params = {
            "q": f'"{city}" OR "{state}"',
            "sortBy": "publishedAt",
            "language": "en",
            "pageSize": 10,
            "apiKey": api_key
        }
        r = requests.get(url, params=params, headers=HEADERS, timeout=15)
        data = r.json()
        if data.get("status") == "error":
            print(f"      NewsAPI error: {data.get('message','')}")
            return []
        articles = []
        for a in data.get("articles", [])[:10]:
            articles.append({
                "title": a.get("title", ""),
                "url": a.get("url", ""),
                "source": a.get("source", {}).get("name", "NewsAPI"),
                "published": (a.get("publishedAt") or "")[:16],
                "description": (a.get("description") or "")[:200]
            })
        return articles
    except Exception as e:
        print(f"      NewsAPI exception: {e}")
        return []


def bing_news_rss(city, state):
    """Tier 2: Bing News RSS (no key needed)."""
    try:
        query = f"{city} {state} news"
        url = f"https://www.bing.com/news/search?q={requests.utils.quote(query)}&format=rss"
        r = requests.get(url, headers=BROWSER_HEADERS, timeout=15)
        if r.status_code != 200:
            return []
        return _parse_rss(r.content, source_label="Bing News")
    except Exception as e:
        print(f"      Bing News exception: {e}")
        return []


def feed(url, label, retries=2):
    """Fetch and parse an RSS/Atom feed with retries."""
    last_err = None
    for attempt in range(retries):
        try:
            r = requests.get(url, headers=BROWSER_HEADERS, timeout=12)
            if r.status_code == 200:
                return _parse_rss(r.content, source_label=label)
            if r.status_code in (429, 403):
                time.sleep(2)
                continue
            if r.status_code == 404:
                return []
        except Exception as e:
            last_err = e
            time.sleep(1)
    if last_err:
        print(f"      Feed failed ({label}): {last_err}")
    return []


# Kentucky/Louisville-specific feeds (state-weighted)
# Add your own feeds here for other regions.
KY_FEEDS = [
    ("WFPL NPR Louisville", "https://wfpl.org/feed/"),
    ("Kentucky Sports Radio", "https://kentuckysportsradio.com/feed/"),
    ("Forward Kentucky", "https://forwardky.com/feed/"),
    ("The Lane Report", "https://www.lanereport.com/feed/"),
    ("UK Kentucky Kernel", "https://www.kykernel.com/feed/"),
]

# Generic state-level feeds that exist for most states
STATE_FEED_TEMPLATES = {
    "npr": "https://www.npr.org/sections/{state}/rss.xml",
    # Add more templates as discovered
}


def get_local_news(city, state, api_key=None):
    """Fetch local news from all available sources."""
    key = api_key or os.environ.get("NEWSAPI_KEY", "")
    articles = []
    seen = set()

    # Tier 1: NewsAPI (best quality)
    if key:
        print(f"      Fetching NewsAPI for {city}, {state}...")
        news = newsapi(city, state, key)
        _dedup_insert(articles, news, seen)
        print(f"      NewsAPI: {len(news)} articles")

    # Tier 2: Bing News RSS (no key)
    print(f"      Fetching Bing News RSS...")
    bing = bing_news_rss(city, state)
    _dedup_insert(articles, bing, seen)
    print(f"      Bing News: {len(bing)} articles")

    # Tier 3: Regional RSS feeds
    state_lower = state.lower().replace(" ", "")
    city_lower = city.lower().replace(" ", "")

    for label, url in KY_FEEDS:
        print(f"      Fetching {label}...")
        f = feed(url, label)
        _dedup_insert(articles, f, seen)
        print(f"      {label}: {len(f)} articles")

    # Tier 4: DDG fallback if everything above is empty
    if len(articles) < 3:
        try:
            from ddg_scraper import ddg_local_news
            print(f"      RSS/API sparse — falling back to DDG local news")
            ddg = ddg_local_news(city, state, max_results=10)
            for d in ddg:
                norm_url = _normalize_url(d.get("url", ""))
                title_key = d.get("title", "").lower().strip()[:40]
                key = norm_url or title_key
                if key in seen:
                    continue
                seen.add(key)
                articles.append({
                    "title": d["title"][:200],
                    "url": d["url"],
                    "source": d.get("source", "DDG"),
                    "published": d.get("published", "")[:16],
                    "description": d.get("description", "")[:200]
                })
                if len(articles) >= 20:
                    break
        except Exception as e:
            print(f"      DDG local fallback failed: {e}")

    # Relabel by freshness (most recent first)
    articles = articles[:15]

    return {
        "city": city,
        "state": state,
        "timestamp": datetime.utcnow().isoformat(),
        "articles": articles
    }


if __name__ == "__main__":
    import sys
    city = sys.argv[1] if len(sys.argv) > 1 else "Louisville"
    state = sys.argv[2] if len(sys.argv) > 2 else "Kentucky"
    result = get_local_news(city, state)
    print(f"\nTotal unique articles: {len(result['articles'])}")
    for a in result["articles"][:8]:
        print(f"  [{a['source'][:12]:12s}] {a['title'][:65]}...")
