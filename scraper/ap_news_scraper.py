#!/usr/bin/env python3
"""AP News + general news aggregator via direct RSS feeds."""

import requests
import xml.etree.ElementTree as ET
from datetime import datetime
import json

HEADERS = {
    "User-Agent": "AI-News-Dashboard/1.0 (Headlines only; bot)"
}

# Direct RSS feeds (avoid RSSHub which blocks us)
NEWS_FEEDS = {
    "bbc_news":      "http://feeds.bbci.co.uk/news/rss.xml",
    "bbc_world":     "http://feeds.bbci.co.uk/news/world/rss.xml",
    "abc_news":      "https://abcnews.go.com/abcnews/topstories",
    "npr":           "https://feeds.npr.org/1001/rss.xml",
    "al_jazeera":    "https://www.aljazeera.com/xml/rss/all.xml",
    "google_news":   "https://news.google.com/rss?hl=en-US&gl=US&ceid=US:en",
}

def parse_rss_items(url, source_name, category_tag="world", limit=6):
    """Fetch and parse a single RSS feed."""
    items = []
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        r.raise_for_status()
        root = ET.fromstring(r.content)
        for item in root.findall(".//item")[:limit]:
            ns = {"content": "http://purl.org/rss/1.0/modules/content/"}
            desc = item.findtext("description", "")
            if not desc:
                c = item.find(".//content:encoded", ns)
                if c is not None:
                    desc = c.text[:350] if c.text else ""
            title = item.findtext("title", "")
            link  = item.findtext("link", "")
            pub   = item.findtext("pubDate", "")
            if title:
                items.append({
                    "title": title.strip()[:200],
                    "url": link.strip() if link else "#",
                    "source": source_name,
                    "category": category_tag,
                    "published": pub.strip()[:17] if pub else "",
                    "description": (desc.strip() if desc else "")[:300]
                })
    except Exception as e:
        print(f"      Feed {source_name} failed: {e}")
    return items

def get_ap_data(file_path=None):
    """Master entry: aggregate all news feeds."""
    print("[ ] Fetching world headlines...")
    all_news = []
    for tag, url in NEWS_FEEDS.items():
        all_news.extend(parse_rss_items(url, tag.replace("_", " ").title(), tag, limit=6))
        # Be polite between requests
        import time
        time.sleep(0.5)

    # Deduplicate by title
    seen = set()
    uniq = []
    for n in all_news:
        if n["title"] not in seen:
            seen.add(n["title"])
            uniq.append(n)

    data = {
        "timestamp": datetime.utcnow().isoformat(),
        "all_news": uniq[:18]
    }
    if file_path:
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    return data


if __name__ == "__main__":
    data = get_ap_data()
    print(f"Total news items: {len(data.get('all_news', []))}")
