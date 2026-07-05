#!/usr/bin/env python3
"""Reddit scraper - uses HackerNews RSS + keyword scoring since Reddit blocks."""

import requests
import xml.etree.ElementTree as ET
from datetime import datetime
import time
from scraper_utils import fetch_with_retry

HEADERS = {
    "User-Agent": "AI-News-Dashboard/1.0"
}

AI_KEYWORDS = [
    "llm", "model", "ai ", "agent", "inference", "gpu", "nvidia", "openai",
    "anthropic", "claude", "gpt", "transformer", "neural", "machine learning",
    "autonomous", "benchmark", "quantiz", "fine-tun", "training"
]

def get_hn_posts(limit=15):
    """Fetch HackerNews top stories via RSS."""
    posts = []
    try:
        r = fetch_with_retry("https://news.ycombinator.com/rss", headers=HEADERS, timeout=15, max_retries=2, backoff_base=2.0)
        if r is None:
            return []
        root = ET.fromstring(r.content)
        for item in root.findall(".//item")[:30]:
            title = item.findtext("title", "")
            link = item.findtext("link", "")
            dc_date = item.findtext("{http://purl.org/dc/elements/1.1/}date", "")
            score = 0
            title_lower = title.lower()
            for kw in AI_KEYWORDS:
                if kw in title_lower:
                    score += 1
            posts.append({
                "title": title.strip()[:200],
                "subreddit": "HackerNews",
                "score": score * 100 + 1,
                "comments": 0,
                "url": link.strip() if link else "#",
                "created": dc_date
            })
    except Exception as e:
        print(f"      HN fetch error: {e}")
    posts.sort(key=lambda x: x["score"], reverse=True)
    return posts[:limit]

def get_reddit_posts(subreddits=None, limit=10):
    """Main entry. Reddit is blocked, fallback to HackerNews + DDG."""
    posts = get_hn_posts(limit=limit)
    # If HN is empty (rare), try DDG AI news as last resort
    if not posts:
        try:
            from ddg_scraper import ddg_ai_reddit
            print("      HN empty — falling back to DDG AI news")
            ddg = ddg_ai_reddit(max_results=limit)
            posts = [{
                "title": d["title"],
                "subreddit": "DDG",
                "score": 100,
                "comments": 0,
                "url": d["url"],
                "created": d.get("published", "")
            } for d in ddg[:limit]]
        except Exception as e:
            print(f"      DDG AI fallback failed: {e}")
    return posts

def get_world_reddit_posts(limit=5):
    """Fetch top posts from r/worldnews via public RSS."""
    posts = []
    try:
        r = fetch_with_retry(
            "https://www.reddit.com/r/worldnews/top/.rss?t=day&limit=15",
            timeout=15, max_retries=2, backoff_base=2.0
        )
        if r is None:
            return []
        root = ET.fromstring(r.content)
        for item in root.findall(".//item")[:limit * 2]:
            title = item.findtext("title", "")
            link = item.findtext("link", "")
            pub = item.findtext("pubDate", "")
            author = item.findtext("{http://purl.org/dc/elements/1.1/}creator", "")
            if not title:
                continue
            posts.append({
                "title": title.strip()[:200],
                "url": link.strip() if link else "#",
                "source": "r/worldnews",
                "category": "world",
                "published": pub.strip()[:17] if pub else "",
                "description": f"u/{author}" if author else ""
            })
    except Exception as e:
        print(f"      Reddit worldnews error: {e}")
    return posts[:limit]


if __name__ == "__main__":
    posts = get_reddit_posts()
    print(f"Fetched {len(posts)} posts")
    for p in posts[:5]:
        print(f"[{p['score']}] {p['title'][:80]}...")
    wposts = get_world_reddit_posts()
    print(f"Fetched {len(wposts)} world posts")
    for p in wposts[:5]:
        print(f"[r/worldnews] {p['title'][:80]}...")
