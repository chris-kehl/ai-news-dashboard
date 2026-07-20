"""Sticky tab scrapers — CNBC, Yahoo Finance, Bloomberg, WallStreetBets.
Lightweight: RSS/JSON endpoints first, HTML fallback if blocked.
"""
import json, re, xml.etree.ElementTree as ET
from datetime import datetime
from scraper_utils import fetch_with_retry, DEFAULT_HEADERS

HEADERS = {"User-Agent": "Mozilla/5.0 (AI-News-Dashboard/1.0)"}

def _fmt_date(s):
    if not s: return ""
    try:
        if "GMT" in s or "+" in s[-6:]:
            return datetime.strptime(s[:25].strip(), "%a, %d %b %Y %H:%M:%S").isoformat()
    except: pass
    try:
        return datetime.fromisoformat(s.replace("Z","+00:00")).isoformat()
    except: pass
    return s

def _extract_rss_items(url, limit=8, source=""):
    """Generic RSS parser returning normalized items."""
    items = []
    try:
        r = fetch_with_retry(url, headers={**DEFAULT_HEADERS, **HEADERS}, timeout=15, max_retries=2)
        if not r: return items
        root = ET.fromstring(r.content)
        ns = {"dc": "http://purl.org/dc/elements/1.1/", "content": "http://purl.org/rss/1.0/modules/content/"}
        for item in root.findall(".//item")[:limit*2]:
            title = item.findtext("title", "").strip()
            link = item.findtext("link", "").strip()
            desc = item.findtext("description", "").strip()
            pub = item.findtext("pubDate", "") or item.findtext("{http://purl.org/dc/elements/1.1/}date", "")
            if title and link:
                items.append({
                    "title": title[:200], "url": link,
                    "source": source, "published": _fmt_date(pub),
                    "description": re.sub(r"<[^>]+>", "", desc)[:300]
                })
    except Exception as e:
        print(f"      RSS error {source}: {e}")
    return items[:limit]

# ===== CNBC =====
def get_cnbc(limit=8):
    """CNBC top news via RSS."""
    return _extract_rss_items("https://www.cnbc.com/id/100003114/device/rss/rss.html", limit, "CNBC")

# ===== Yahoo Finance =====
def get_yahoo_finance(limit=8):
    """Yahoo Finance latest news via RSS."""
    return _extract_rss_items("https://finance.yahoo.com/news/rssindex", limit, "Yahoo Finance")

# ===== Bloomberg =====
import os, time

def get_bloomberg(limit=8):
    """Bloomberg RSS (markets + tech sections). Falls back to Bing news search if RSS fails."""
    urls = [
        "https://feeds.bloomberg.com/business/news.rss",
        "https://feeds.bloomberg.com/technology/news.rss",
    ]
    all_items = []
    for url in urls:
        all_items.extend(_extract_rss_items(url, limit, "Bloomberg"))
    # Deduplicate by URL
    seen = set()
    deduped = []
    for it in sorted(all_items, key=lambda x: x.get("published",""), reverse=True):
        if it["url"] not in seen:
            seen.add(it["url"]); deduped.append(it)
    # If RSS is empty, fallback to Bing/DDG search for Bloomberg headlines
    if not deduped:
        try:
            from ddg_scraper import ddg_news
            results = ddg_news("Bloomberg markets OR finance", max_results=limit, cache_key="bloomberg_ddg")
            for r in results:
                deduped.append({
                    "title": r.get("title", "")[:200],
                    "url": r.get("url", "").strip() or "#",
                    "source": "Bloomberg",
                    "published": r.get("published", "")[:20],
                    "description": r.get("description", "")[:300],
                })
        except Exception as e:
            print(f"      Bloomberg fallback error: {e}")
    return deduped[:limit]

# ===== WALL STREET BETS =====
def get_wsb_posts(limit=10):
    """r/wallstreetbets hot posts via Reddit OAuth API.
    Falls back to public JSON API or DDG if OAuth is not configured."""
    try:
        from reddit_api_client import get_subreddit_posts
        posts = get_subreddit_posts("wallstreetbets", limit=limit*2, period="day")
        result = []
        for p in posts:
            score = p.get("score", 0)
            if score < 10: continue
            result.append({
                "title": p["title"][:200], "url": p["url"],
                "source": "r/wallstreetbets", "published": p.get("created", ""),
                "score": score, "comments": p.get("comments", 0),
                "description": ""
            })
            if len(result) >= limit: break
        return result
    except Exception as e:
        print(f"      WSB OAuth failed: {e}, trying public JSON API")

    # Public JSON API fallback (no auth required)
    try:
        import requests
        r = requests.get(
            "https://www.reddit.com/r/wallstreetbets/hot.json?limit=25",
            headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"},
            timeout=15
        )
        if r.status_code == 200:
            data = r.json()
            result = []
            for child in data.get("data", {}).get("children", []):
                p = child.get("data", {})
                score = p.get("score", 0)
                if score < 10: continue
                result.append({
                    "title": p.get("title", "")[:200],
                    "url": "https://reddit.com" + p.get("permalink", ""),
                    "source": "r/wallstreetbets",
                    "published": "",
                    "score": score,
                    "comments": p.get("num_comments", 0),
                    "description": ""
                })
                if len(result) >= limit: break
            if result:
                return result
    except Exception as e:
        print(f"      WSB JSON fallback error: {e}")

    # DDG news search fallback
    try:
        from ddg_scraper import ddg_news
        results = ddg_news("wallstreetbets OR WSB stock picks", max_results=limit, cache_key="wsb_ddg")
        if results:
            return [{
                "title": r.get("title", "")[:200],
                "url": r.get("url", "").strip() or "#",
                "source": "r/wallstreetbets",
                "published": r.get("published", "")[:20],
                "score": "—",
                "comments": 0,
                "description": ""
            } for r in results]
    except Exception as e:
        print(f"      WSB DDG fallback error: {e}")

    # Final fallback: Google News RSS for wallstreetbets mentions
    print("      Trying Google News RSS fallback...")
    return _extract_rss_items(
        "https://news.google.com/rss/search?q=wallstreetbets&hl=en-US&gl=US&ceid=US:en",
        limit, "r/wallstreetbets"
    )
    return []

# ===== COMBINED STICKY TAB DATA =====
def get_sticky_tab_data():
    """Fetch all sticky-tab sources. Called from main.py."""
    print("\n[Sticky Tab] CNBC...")
    cnbc = get_cnbc(8)
    print(f"       {len(cnbc)} items")

    print("[Sticky Tab] Yahoo Finance...")
    yahoo = get_yahoo_finance(8)
    print(f"       {len(yahoo)} items")

    print("[Sticky Tab] Bloomberg...")
    bloomberg = get_bloomberg(8)
    print(f"       {len(bloomberg)} items")

    print("[Sticky Tab] WallStreetBets...")
    wsb = get_wsb_posts(10)
    print(f"       {len(wsb)} items")

    return {
        "cnbc": cnbc,
        "yahoo_finance": yahoo,
        "bloomberg": bloomberg,
        "wallstreetbets": wsb,
    }

if __name__ == "__main__":
    data = get_sticky_tab_data()
    for src, items in data.items():
        print(f"\n{src.upper()}: {len(items)} items")
        for it in items[:3]:
            print(f"  - {it['title'][:70]}...")
