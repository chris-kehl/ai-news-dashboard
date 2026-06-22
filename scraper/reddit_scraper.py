#!/usr/bin/env python3
"""Reddit scraper using RSS feeds (reliable, no auth)."""

import requests
import xml.etree.ElementTree as ET
from datetime import datetime

HEADERS = {
    "User-Agent": "AI-News-Dashboard/1.0"
}

def get_reddit_posts(subreddits=None, limit=10):
    """Fetch hot posts from subreddits via RSS."""
    if subreddits is None:
        subreddits = ["LocalLLaMA", "MachineLearning", "Bittensor"]

    posts = []
    for sub_name in subreddits:
        try:
            url = f"https://www.reddit.com/r/{sub_name}/hot/.rss?limit={limit}"
            response = requests.get(url, headers=HEADERS, timeout=15)
            response.raise_for_status()

            root = ET.fromstring(response.content)
            ns = {"atom": "http://www.w3.org/2005/Atom"}

            for entry in root.findall("atom:entry", ns):
                title = entry.find("atom:title", ns)
                link = entry.find("atom:link", ns)
                updated = entry.find("atom:updated", ns)

                # Reddit includes score in content
                content = entry.find("atom:content", ns)
                score = 0
                comments = 0
                if content is not None and content.text:
                    # Try to extract score from content
                    import re
                    s = re.search(r'Score:\s*(\d+)', content.text)
                    if s:
                        score = int(s.group(1))
                    c = re.search(r'(\d+)\s+comment', content.text)
                    if c:
                        comments = int(c.group(1))

                posts.append({
                    "title": title.text if title is not None else "",
                    "subreddit": sub_name,
                    "score": score,
                    "comments": comments,
                    "url": link.get("href") if link is not None else "",
                    "created": updated.text if updated is not None else ""
                })
        except Exception as e:
            print(f"      Error fetching r/{sub_name}: {e}")
            continue

    # Sort by score and return top posts
    posts.sort(key=lambda x: x["score"], reverse=True)
    return posts[:20]

if __name__ == "__main__":
    posts = get_reddit_posts()
    print(f"Fetched {len(posts)} Reddit posts")
    for p in posts[:5]:
        print(f"[{p['score']}] {p['title'][:80]}...")
