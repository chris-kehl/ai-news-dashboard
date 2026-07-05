#!/usr/bin/env python3
"""Defense / geopolitics scraper: Iran, Israel, Ukraine, China, latest conflicts."""

import requests
import xml.etree.ElementTree as ET
from datetime import datetime
import json
import time
from scraper_utils import fetch_with_retry

HEADERS = {
    "User-Agent": "AI-News-Dashboard/1.0 (Headlines only; bot)"
}

DEFENSE_FEEDS = {
    "defense_news": "https://www.defensenews.com/arc/outboundfeeds/rss/",
    "al_jazeera": "https://www.aljazeera.com/xml/rss/all.xml",
    "bbc_world": "http://feeds.bbci.co.uk/news/world/rss.xml",
}

KEYWORDS = [
    "Iran", "Israel", "Ukraine", "China", "Gaza", "Palestin", "Hamas",
    "Hezbollah", "Russia", "NATO", "Taiwan", "South China Sea",
    "missile", "drone", "airstrike", "tank", "military", "defense",
    "war", "conflict", "Pentagon", "confrontation", "attack",
    "invasion", "sanctions", "escalation"
]

def parse_items(url, source, limit=8):
    items = []
    try:
        r = fetch_with_retry(url, headers=HEADERS, timeout=15, max_retries=2, backoff_base=2.0, retry_codes=(429, 403, 502))
        if r is None:
            return items
        root = ET.fromstring(r.content)
        for item in root.findall(".//item")[:limit]:
            ns = {"content": "http://purl.org/rss/1.0/modules/content/"}
            desc = item.findtext("description", "")
            if not desc:
                c = item.find(".//content:encoded", ns)
                if c is not None and c.text:
                    desc = c.text[:350]
            title = item.findtext("title", "").strip()
            link = item.findtext("link", "").strip()
            pub = item.findtext("pubDate", "").strip()
            if title:
                items.append({
                    "title": title[:200],
                    "url": link if link else "#",
                    "source": source,
                    "published": pub[:17] if pub else "",
                    "description": desc.strip()[:300]
                })
    except Exception as e:
        print(f"      Defense feed {source} failed: {e}")
    return items

def get_conflict_focus():
    """Score by keyword relevance for Iran / Israel / Ukraine / China / conflicts."""
    all_items = []
    for source, url in DEFENSE_FEEDS.items():
        all_items.extend(parse_items(url, source.replace("_", " ").title(), limit=8))

    scored = []
    for item in all_items:
        title_lower = item["title"].lower()
        desc_lower = item.get("description", "").lower()
        score = 0
        for kw in KEYWORDS:
            k = kw.lower()
            if k in title_lower:
                score += 3
            if k in desc_lower:
                score += 1
        if score > 0:
            scored.append({**item, "relevance_score": score})

    # DDG fallback if RSS is empty
    if not scored:
        try:
            from ddg_scraper import ddg_defense_news
            print("      Defense RSS empty — falling back to DDG")
            ddg = ddg_defense_news(max_results=10)
            for d in ddg:
                title_lower = d["title"].lower()
                desc_lower = d.get("description", "").lower()
                score = 0
                for kw in KEYWORDS:
                    k = kw.lower()
                    if k in title_lower:
                        score += 3
                    if k in desc_lower:
                        score += 1
                if score > 0:
                    scored.append({**d, "relevance_score": score})
        except Exception as e:
            print(f"      DDG defense fallback failed: {e}")

    # Sort by relevance, top 15
    scored.sort(key=lambda x: x["relevance_score"], reverse=True)
    return scored[:15]

def get_defense_data(file_path=None):
    """Master entry."""
    print("[ ] Fetching defense / geopolitics news...")
    data = {
        "timestamp": datetime.utcnow().isoformat(),
        "conflicts": get_conflict_focus()
    }
    if file_path:
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    return data


if __name__ == "__main__":
    data = get_defense_data()
    print(f"Conflict articles: {len(data['conflicts'])}")
