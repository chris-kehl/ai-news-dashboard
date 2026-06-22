#!/usr/bin/env python3
"""Reddit scraper - uses HackerNews RSS + keyword scoring since Reddit blocks."""

import requests
import xml.etree.ElementTree as ET
from datetime import datetime
import time

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
        r = requests.get("https://news.ycombinator.com/rss", headers=HEADERS, timeout=15)
        r.raise_for_status()
        root = ET.fromstring(r.content)
        for item in root.findall(".//item")[:30]:  # fetch more, filter later
            title = item.findtext("title", "")
            link = item.findtext("link", "")
            dc_date = item.findtext("{http://purl.org/dc/elements/1.1/}date", "")
            # Score by AI relevance
            score = 0
            title_lower = title.lower()
            for kw in AI_KEYWORDS:
                if kw in title_lower:
                    score += 1
            # Boost all, but AI topics rank higher
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
    # Sort by AI relevance score
    posts.sort(key=lambda x: x["score"], reverse=True)
    return posts[:limit]

def get_reddit_posts(subreddits=None, limit=10):
    """Main entry. Reddit is blocked, fallback to HackerNews AI stories."""
    # Reddit RSS is heavily blocked (403). Use HackerNews as proxy.
    return get_hn_posts(limit=limit)

if __name__ == "__main__":
    posts = get_reddit_posts()
    print(f"Fetched {len(posts)} posts")
    for p in posts[:5]:
        print(f"[{p['score']}] {p['title'][:80]}...")
