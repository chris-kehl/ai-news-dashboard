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
def get_bloomberg(limit=8):
    """Bloomberg RSS (markets + tech sections)."""
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
    return deduped[:limit]

# ===== WALL STREET BETS =====
def get_wsb_posts(limit=10):
    """r/wallstreetbets hot posts via Reddit OAuth API.
    Falls back to HTML scrape if OAuth is not configured."""
    try:
        from reddit_api_client import get_subreddit_posts
        posts = get_subreddit_posts("wallstreetbets", limit=limit*2, period="day")
        result = []
        for p in posts:
            # Filter noise: require some engagement or flair
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
        print(f"      WSB OAuth failed: {e}, trying HTML fallback")

    # HTML fallback via old.reddit
    items = []
    try:
        import requests
        sess = requests.Session()
        sess.headers.update({**DEFAULT_HEADERS, **HEADERS})
        sess.get("https://old.reddit.com", timeout=15)
        r = sess.get("https://old.reddit.com/r/wallstreetbets/hot/?limit=25", timeout=15)
        for m in re.finditer(
            r'<a[^>]*class="title[^"]*"[^>]*href="([^"]+)"[^>]*>([^<]*)</a>.*?data-ups="(\d+)"',
            r.text, re.IGNORECASE | re.DOTALL
        ):
            href, title, score = m.group(1).strip(), m.group(2).strip(), int(m.group(3))
            if not title or score < 10: continue
            link = href if href.startswith("http") else f"https://old.reddit.com{href}"
            items.append({
                "title": title[:200], "url": link, "source": "r/wallstreetbets",
                "published": "", "score": score, "comments": 0, "description": ""
            })
            if len(items) >= limit: break
    except Exception as e:
        print(f"      WSB HTML fallback error: {e}")
    return items

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
