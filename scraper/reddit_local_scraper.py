#!/usr/bin/env python3
"""Local Reddit scraper: fetches city/state subreddits based on weather zip.

Uses old.reddit.com RSS which works with realistic browser headers.
3-4 second delays between requests to avoid rate limits.
"""

import requests
import xml.etree.ElementTree as ET
import re
import time
import os
from datetime import datetime
from scraper_utils import fetch_with_retry

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Accept": "application/atom+xml,application/rss+xml,*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://old.reddit.com/",
}


def subreddit_name(name):
    """Normalize a city/state name for a subreddit."""
    # Lowercase, remove apostrophes, replace spaces with nothing
    n = name.lower().strip()
    n = re.sub(r"['.]", "", n)     # Louisville's -> louisvilles, St. -> St
    n = re.sub(r"[^a-z0-9]", "", n) # Remove all non-alphanumeric
    return n


def fetch_subreddit_posts(name, limit=5):
    """Fetch hot posts from a single subreddit via old.reddit.com RSS."""
    url = f"https://old.reddit.com/r/{name}/.rss?limit={limit}"
    posts = []
    try:
        r = fetch_with_retry(url, headers=HEADERS, timeout=15, max_retries=2, backoff_base=3.0, retry_codes=(429, 403, 502))
        if r is None:
            return posts, 429
        if r.status_code != 200:
            return posts, r.status_code

        root = ET.fromstring(r.content)
        ns = {"atom": "http://www.w3.org/2005/Atom",
              "media": "http://search.yahoo.com/mrss/"}

        for entry in root.findall("atom:entry", ns):
            title_el = entry.find("atom:title", ns)
            link_el = entry.find("atom:link", ns)
            updated_el = entry.find("atom:updated", ns)
            content_el = entry.find("atom:content", ns)

            title = title_el.text if title_el is not None else ""
            link = link_el.get("href") if link_el is not None else ""
            updated = updated_el.text if updated_el is not None else ""

            # Extract score from uri/id if available (format: t3_postid)
            score, comments = 0, 0
            id_el = entry.find("atom:id", ns)
            if id_el is not None and id_el.text:
                # Try to get comment count from comments link in content
                pass

            # Try score/comments from content text
            if content_el is not None and content_el.text:
                s = re.search(r'Score:\s*([\d,]+)', content_el.text)
                if s:
                    score = int(s.group(1).replace(',', ''))
                c = re.search(r'([\d,]+)\s+comment', content_el.text)
                if c:
                    comments = int(c.group(1).replace(',', ''))

            # Fallback: try thumbnail/media for engagement hints (no scores in modern RSS)
            # Reddit hides scores in unauthenticated RSS now — that's expected
            if score == 0:
                score = "—"
            if comments == 0:
                comments = "—"

            # Skip moderator stickies
            if title.startswith("[") and "moderator" in title.lower():
                continue

            posts.append({
                "title": title.strip()[:200],
                "subreddit": name,
                "score": score,
                "comments": comments,
                "url": link.strip(),
                "created": updated
            })

        return posts, 200
    except ET.ParseError:
        # Got HTML error page instead of XML
        return posts, 403
    except Exception as e:
        return posts, str(e)


def get_local_reddit(city, state, max_posts=8):
    """Fetch hot posts from city and state subreddits.

    Args:
        city:  City name (e.g. "Louisville")
        state: State name (e.g. "Kentucky")
        max_posts: max total posts to return
    """
    subs = []

    # Derive subreddit names
    city_sub = subreddit_name(city)
    state_sub = subreddit_name(state)

    if city_sub:
        subs.append(city_sub)
    if state_sub and state_sub != city_sub:
        subs.append(state_sub)

    all_posts = []
    for sub in subs:
        posts, status = fetch_subreddit_posts(sub, limit=5)
        if posts:
            all_posts.extend(posts)
        # Politeness: 6-9 seconds between requests (ran once/15 min via cron)
        import random
        time.sleep(random.uniform(6, 9))

    # Sort by score, take top N
    all_posts.sort(key=lambda x: x["score"], reverse=True)
    return all_posts[:max_posts]


def get_local_reddit_from_weather(weather_data, max_posts=8):
    """Convenience: pass weather dict from weather_scraper."""
    city = weather_data.get("city", "")
    state = weather_data.get("state", "")
    if not city:
        return []
    return get_local_reddit(city, state, max_posts)


if __name__ == "__main__":
    # Test
    posts = get_local_reddit("Louisville", "Kentucky", max_posts=8)
    print(f"Fetched {len(posts)} local reddit posts")
    for p in posts[:5]:
        print(f"  [{p['score']}] r/{p['subreddit']}: {p['title'][:70]}...")
