#!/usr/bin/env python3
"""X/Twitter scraper using Nitter RSS feeds with fallback instances."""

import requests
import xml.etree.ElementTree as ET
import random
import time
import re

def get_working_instances():
    """Test Nitter RSS instances and return working ones."""
    candidates = [
        "https://nitter.privacydev.net",
        "https://nitter.cz",
        "https://nitter.net",
        "https://nitter.space",
        "https://nitter.it",
    ]
    headers = {"User-Agent": "AI-News-Dashboard/1.0"}
    working = []
    for base in candidates:
        try:
            r = requests.get(f"{base}/karpathy/rss", headers=headers, timeout=10)
            if r.status_code == 200 and b"<entry" in r.content:
                working.append(base)
                print(f"      OK: {base}")
            else:
                print(f"      Down: {base} (status {r.status_code})")
        except Exception as e:
            print(f"      Down: {base} ({e})")
    if not working:
        print("      Warning: No Nitter instances responding. Will retry with defaults.")
        return candidates[:2]
    return working

AI_ACCOUNTS = [
    "karpathy",
    "swyx",
    "binduredy",
    "ylecun",
    "DrJimFan",
    "AndrewYNg",
    "sama",
    "gdb",
]

def fetch_rss(base_url, username):
    """Fetch Nitter RSS for a user."""
    rss_url = f"{base_url}/{username}/rss"
    headers = {"User-Agent": "AI-News-Dashboard/1.0"}
    try:
        r = requests.get(rss_url, headers=headers, timeout=15)
        return r.content if r.status_code == 200 else None
    except Exception:
        return None

def parse_nitter_rss(xml_bytes, username):
    """Parse Nitter RSS XML into post dicts."""
    posts = []
    if not xml_bytes:
        return posts
    try:
        root = ET.fromstring(xml_bytes)
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        for entry in root.findall("atom:entry", ns):
            title = entry.find("atom:title", ns)
            link = entry.find("atom:link", ns)
            updated = entry.find("atom:updated", ns)
            text = ""
            if title is not None and title.text:
                text = title.text
            posts.append({
                "author": f"@{username}",
                "text": re.sub(r'<[^>]+>', '', text)[:280],
                "likes": 0,
                "date": updated.text if updated is not None else "",
                "url": link.get("href") if link is not None else f"https://twitter.com/{username}"
            })
    except Exception:
        pass
    return posts

def get_x_posts(accounts=None, limit_per_account=3):
    """Fetch recent posts from AI Twitter accounts via Nitter RSS."""
    if accounts is None:
        accounts = AI_ACCOUNTS

    print("      Finding working Nitter instances...")
    instances = get_working_instances()
    all_posts = []

    for account in accounts[:5]:
        got_posts = False
        for instance in instances:
            xml = fetch_rss(instance, account)
            if xml:
                posts = parse_nitter_rss(xml, account)
                if posts:
                    all_posts.extend(posts[:limit_per_account])
                    got_posts = True
                    break
            time.sleep(0.5)
        if not got_posts:
            print(f"      Could not fetch @{account} from any instance")
        time.sleep(1)

    return all_posts[:12]

if __name__ == "__main__":
    posts = get_x_posts()
    print(f"Fetched {len(posts)} X posts")
    for p in posts[:5]:
        print(f"[{p['author']}] {p['text'][:80]}...")
