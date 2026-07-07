#!/usr/bin/env python3
"""Reddit scraper — now uses OAuth password grant API client.

Requires env vars:
    REDDIT_CLIENT_ID
    REDDIT_CLIENT_SECRET
    REDDIT_USERNAME
    REDDIT_PASSWORD
"""

import time
import requests
import xml.etree.ElementTree as ET
from datetime import datetime
import re
from scraper_utils import fetch_with_retry, DEFAULT_HEADERS
from reddit_api_client import (
    get_hot_ai_posts,
    get_worldnews_posts,
    get_subreddit_posts,
    get_token,
)

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
        r = fetch_with_retry(
            "https://news.ycombinator.com/rss",
            headers=HEADERS,
            timeout=15,
            max_retries=2,
            backoff_base=2.0
        )
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
    """Main entry: fetch AI-relevant Reddit posts via OAuth API.

    Falls back to HackerNews + DDG on auth failure.
    """
    try:
        posts = get_hot_ai_posts(subreddits=subreddits, limit=limit)
        if posts:
            print(f"      Reddit API: {len(posts)} AI posts")
            return posts
    except Exception as e:
        print(f"      Reddit API error: {e}")

    # Fallback chain
    posts = get_hn_posts(limit=limit)
    if posts:
        print(f"      HN fallback: {len(posts)} posts")
        return posts

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
        print(f"      DDG fallback failed: {e}")
    return posts


def get_world_reddit_posts(limit=5):
    """Fetch top posts from r/worldnews via OAuth API."""
    try:
        posts = get_worldnews_posts(limit=limit, period="day")
        if posts:
            print(f"      r/worldnews API: {len(posts)} posts")
            return [{
                "title": p["title"],
                "url": p["url"],
                "source": "r/worldnews",
                "category": "world",
                "description": ""
            } for p in posts]
    except Exception as e:
        print(f"      r/worldnews API error: {e}")

    # HTML fallback only if API fails
    posts = []
    try:
        sess = requests.Session()
        sess.headers.update(DEFAULT_HEADERS)
        sess.get("https://old.reddit.com", timeout=20)
        r = sess.get(
            "https://old.reddit.com/r/worldnews/top/?t=day&limit=15",
            timeout=20
        )
        if r.status_code != 200:
            return []
        for m in re.finditer(
            r'<a[^>]*class="title[^"]*"[^>]*href="([^"]+)"[^>]*>([^<]*)</a>',
            r.text,
            re.IGNORECASE
        ):
            href = m.group(1).strip()
            title = m.group(2).strip()
            if not title:
                continue
            link = href if href.startswith("http") else f"https://old.reddit.com{href}"
            posts.append({
                "title": title[:200],
                "url": link,
                "source": "r/worldnews",
                "category": "world",
                "description": ""
            })
    except Exception as e:
        print(f"      Reddit worldnews HTML fallback error: {e}")
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
