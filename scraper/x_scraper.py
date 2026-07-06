#!/usr/bin/env python3
"""X/Twitter scraper with local city search + AI accounts fallback.

Uses Nitter RSS (free, no API key) to search for local city tweets.
Falls back to popular AI accounts if local search is empty.
"""
import requests, re, random, time, json
import xml.etree.ElementTree as ET
from urllib.parse import quote

BROWSER = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9',
}

NITTER_INSTANCES = [
    "https://nitter.net",        # Working for RSS (Jul 2025)
    "https://nitter.cz",
    "https://nitter.space",
    "https://nitter.privacydev.net",
    "https://nitter.it",
]

NEWS_X_ACCOUNTS = ["BBCWorld", "Reuters", "BreakingNews", "AP"]

AI_ACCOUNTS = ["karpathy", "swyx", "ylecun", "DrJimFan", "sama", "gdb"]


def _working_nitter():
    """Find a responding Nitter instance."""
    for base in NITTER_INSTANCES:
        try:
            sess = requests.Session()
            sess.headers.update(BROWSER)
            r = sess.get(f"{base}/karpathy/rss", timeout=10)
            if r.status_code == 200 and b"<item>" in r.content:
                return base
        except Exception:
            continue
    return NITTER_INSTANCES[0]


def _search_nitter(base, query, max_results=10):
    """Search Nitter for tweets matching a query."""
    try:
        sess = requests.Session()
        sess.headers.update(BROWSER)
        url = f"{base}/search?f=tweets&q={quote(query)}&since=&until=&near="
        r = sess.get(url, timeout=20)
        if r.status_code != 200:
            return []
        html = r.text
        posts = []
        seen = set()
        # Extract tweet cards from search results
        for m in re.finditer(r'<div class="tweet-content[^"]*"[^>]*>.*?<div class="tweet-body">.*?<a href="([^"]+)"[^>]*class="tweet-link"[^>]*>.*?<p class="tweet-content">(.*?)</p>', html, re.DOTALL | re.IGNORECASE):
            tweet_url = m.group(1)
            tweet_text = re.sub(r'<[^>]+>', '', m.group(2)).strip()
            if not tweet_text or len(tweet_text) < 10:
                continue
            # Get author from URL
            author_match = re.search(r'/([^/]+)/status/\d+', tweet_url)
            author = author_match.group(1) if author_match else 'unknown'
            key = tweet_text.lower()[:40]
            if key in seen:
                continue
            seen.add(key)
            # Build URL
            status_match = re.search(r'/status/(\d+)', tweet_url)
            if status_match:
                tweet_id = status_match.group(1)
                full_url = f"https://twitter.com/{author}/status/{tweet_id}"
            else:
                full_url = f"https://twitter.com/{author}"
            posts.append({
                "author": f"@{author}",
                "text": tweet_text[:280],
                "url": full_url,
                "date": "",
                "likes": 0,
            })
        return posts[:max_results]
    except Exception as e:
        print(f"[WARN] Nitter search error: {e}")
        return []


def _fetch_user_rss(base, username, limit=5):
    """Fetch RSS feed for a specific user using session."""
    try:
        sess = requests.Session()
        sess.headers.update(BROWSER)
        url = f"{base}/{username}/rss"
        r = sess.get(url, timeout=15)
        if r.status_code != 200:
            return []
        root = ET.fromstring(r.content)
        posts = []
        for item in root.findall(".//item"):
            title = item.findtext("title", "")
            link  = item.findtext("link", "")
            pub   = item.findtext("pubDate", "")
            if title:
                text = re.sub(r'<[^>]+>', '', title).strip()
                posts.append({
                    "author": f"@{username}",
                    "text": text[:280],
                    "url": link or f"https://twitter.com/{username}",
                    "date": pub or "",
                    "likes": 0,
                })
        return posts[:limit]
    except Exception:
        return []


def get_local_x_posts(city, state, max_results=8, fallback_ai=True):
    """Get X/Twitter posts for a local area."""
    base = _working_nitter()
    print(f"      Using Nitter instance: {base}")

    # Strategy 1: Search Nitter for city + state tweets
    queries = [
        f'"{city}"',
        f'"{city}" "{state}"',
    ]
    all_posts = []
    seen = set()

    for q in queries:
        posts = _search_nitter(base, q, max_results=max_results)
        for p in posts:
            key = p["text"].lower()[:40]
            if key not in seen:
                seen.add(key)
                all_posts.append(p)
        time.sleep(1)

    # Strategy 2: Fallback to AI accounts if local search is empty
    if fallback_ai and len(all_posts) < 3:
        print(f"      Local X tweets sparse ({len(all_posts)}), falling back to AI accounts")
        for acct in AI_ACCOUNTS[:4]:
            posts = _fetch_user_rss(base, acct, limit=3)
            for p in posts:
                key = p["text"].lower()[:40]
                if key not in seen:
                    seen.add(key)
                    all_posts.append(p)
            time.sleep(0.8)

    return all_posts[:max_results]


def get_world_x_posts(max_results=5):
    """Fetch world news tweets via Nitter RSS - search endpoint broken, use RSS directly."""
    posts = []
    try:
        base = _working_nitter()
        print(f"      [X World] Using Nitter: {base}")
        for acct in NEWS_X_ACCOUNTS[:3]:
            try:
                more = _fetch_user_rss(base, acct, limit=3)
                for p in more:
                    key = p["text"].lower()[:40]
                    if not any(key == existing["text"].lower()[:40] for existing in posts):
                        posts.append(p)
                if len(posts) >= max_results:
                    break
                time.sleep(0.5)
            except Exception as e:
                print(f"      [WARN] {acct} fetch error: {e}")
                continue
        print(f"      [X World] Got {len(posts)} posts")
    except Exception as e:
        print(f"[WARN] World X scraper error: {e}")
    return posts[:max_results]


if __name__ == "__main__":
    import sys
    city = sys.argv[1] if len(sys.argv) > 1 else "Louisville"
    state = sys.argv[2] if len(sys.argv) > 2 else "Kentucky"
    posts = get_local_x_posts(city, state)
    print(f"Fetched {len(posts)} posts")
    for p in posts[:5]:
        print(f"[{p['author']}] {p['text'][:80]}...")
    wposts = get_world_x_posts()
    print(f"Fetched {len(wposts)} world posts")
    for p in wposts[:5]:
        print(f"[{p['author']}] {p['text'][:80]}...")
