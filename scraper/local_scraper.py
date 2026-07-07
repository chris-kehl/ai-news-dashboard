#!/usr/bin/env python3
"""Unified local content scraper:
- X via Nitter+Playwright (data-universe NitterScraper pattern)
- Reddit via old.reddit.com RSS (data-universe RedditRssScraper pattern)

Entry: get_local_content(city, state, max_x=8, max_reddit=8)
"""
import asyncio, random, re, traceback, datetime as dt
from typing import List, Dict, Optional
from urllib.parse import quote
import time, requests, xml.etree.ElementTree as ET, html as html_module

from feed_config import get_subreddits, get_x_queries
from reddit_api_client import get_subreddit_posts

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)
BROWSER_TIMEOUT = 25000
PAGE_WAIT       = 6000
NITTER_BASE     = "https://nitter.tiekoetter.com"

# ---------- helpers ----------
def _run_async(coroutine):
    try:
        return asyncio.get_event_loop().run_until_complete(coroutine)
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(coroutine)

# ---------- X / Nitter ----------
async def _x_search_nitter(keyword: str, limit: int = 10) -> List[Dict]:
    posts: List[Dict] = []
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        print("[WARN] Playwright not installed - cannot scrape X")
        return posts

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(user_agent=USER_AGENT)
        page = await context.new_page()
        try:
            url = f"{NITTER_BASE}/search?f=tweets&q={quote(keyword)}"
            print(f"      [X] Nitter search: {keyword}")
            await page.goto(url, timeout=BROWSER_TIMEOUT)
            await page.wait_for_timeout(PAGE_WAIT)
            remaining = limit
            while remaining > 0:
                items = await page.query_selector_all(".timeline-item")
                if not items: break
                for item in items:
                    tweet = await _parse_item(item)
                    if tweet:
                        posts.append(tweet)
                        remaining -= 1
                        if remaining <= 0: break
                if remaining <= 0: break
                show_more = await page.query_selector(".show-more")
                if show_more:
                    link = await show_more.query_selector("a")
                    if link:
                        href = await link.get_attribute("href")
                        if href:
                            await page.goto(f"{NITTER_BASE}{href}", timeout=BROWSER_TIMEOUT)
                            await page.wait_for_timeout(PAGE_WAIT)
                        else: break
                    else: break
                else: break
        except Exception as e:
            print(f"[WARN] Playwright X search error: {e}")
        finally:
            await page.close(); await context.close(); await browser.close()
    return posts


async def _parse_item(item) -> Optional[Dict]:
    try:
        username_el = await item.query_selector(".username")
        username = (await username_el.get_attribute("title")) or "" if username_el else ""
        if not username.startswith("@"):
            username = "@" + username

        link_el = await item.query_selector("a.tweet-link")
        href = await link_el.get_attribute("href") or "" if link_el else ""
        x_url = ""
        if href:
            parts = href.split("/")
            if len(parts) >= 4:
                x_url = f"https://x.com/{parts[1]}/status/{parts[3].split('#')[0]}"

        text = ""
        content_el = await item.query_selector(".tweet-content.media-body")
        if content_el:
            text = (await content_el.inner_text()).strip()
        else:
            content_el = await item.query_selector(".tweet-content")
            if content_el:
                text = (await content_el.inner_text()).strip()

        date_el = await item.query_selector(".tweet-date a")
        date_str = await date_el.get_attribute("title") or "" if date_el else ""

        if not text:
            return None
        return {"author": username or "@unknown", "text": text[:300],
                "url": x_url or f"https://x.com/{username.lstrip('@')}",
                "date": date_str, "likes": 0}
    except Exception:
        return None


def get_local_x_posts(city: str, state: str, max_results: int = 8) -> List[Dict]:
    if not city:
        return []
    queries = [f'"{city}"', f'"{city}" "{state}"', f'"{state}"']
    queries += get_x_queries(city, state)
    all_posts, seen = [], set()
    for q in queries:
        posts = _run_async(_x_search_nitter(q, limit=max_results))
        print(f"      [X] Query '{q}' -> {len(posts)} posts")
        for p in posts:
            key = p["text"].lower()[:50]
            if key and key not in seen:
                seen.add(key); all_posts.append(p)
        if len(all_posts) >= max_results: break
        time.sleep(random.uniform(2, 4))
    return all_posts[:max_results]


# ---------- Reddit ----------
RSS_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "application/atom+xml,application/rss+xml,*/*",
    "Accept-Language": "en-US,en;q=0.9", "Referer": "https://old.reddit.com/",
}
BASE_RSS_URL = "https://old.reddit.com"


def _subreddit_name(name: str) -> str:
    n = name.lower().strip()
    n = re.sub(r"['.\u2019]", "", n)
    n = re.sub(r"[^a-z0-9]", "", n)
    return n


def _scrape_subreddit_rss(sr_name: str, limit: int = 10) -> List[Dict]:
    url = f"{BASE_RSS_URL}/r/{sr_name}/.rss?limit={limit}&sort=new"
    posts = []
    try:
        print(f"      [Reddit] RSS: r/{sr_name}")
        r = requests.get(url, headers=RSS_HEADERS, timeout=20)
        if r.status_code == 429:
            print(f"      [Reddit] Rate limited r/{sr_name}, waiting 30s...")
            time.sleep(30)
            r = requests.get(url, headers=RSS_HEADERS, timeout=20)
        if r.status_code != 200:
            print(f"      [Reddit] HTTP {r.status_code} for r/{sr_name}")
            return posts

        root = ET.fromstring(r.content)
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        for entry in root.findall("atom:entry", ns):
            try:
                title_el  = entry.find("atom:title", ns)
                link_el   = entry.find("atom:link", ns)
                author_el = entry.find("atom:author", ns)
                updated_el= entry.find("atom:updated", ns)
                content_el= entry.find("atom:content", ns)

                title = title_el.text or "" if title_el is not None else ""
                permalink = link_el.get("href", "") if link_el is not None else ""
                from urllib.parse import urlparse
                permalink = urlparse(permalink).path or permalink
                updated_str = updated_el.text or "" if updated_el is not None else ""

                name_el = author_el.find("atom:name", ns) if author_el is not None else None
                username = name_el.text or "unknown" if name_el is not None else "unknown"

                body = html_module.unescape(content_el.text) if content_el is not None and content_el.text else ""

                created_at = dt.datetime.now(tz=dt.timezone.utc)
                if updated_str:
                    try: created_at = dt.datetime.fromisoformat(updated_str.replace("Z", "+00:00"))
                    except Exception: pass

                url = f"https://www.reddit.com{permalink}" if permalink else ""
                if not url: continue

                score = 0
                if body:
                    m = re.search(r'Score:\s*([\d,]+)', body)
                    if m: score = int(m.group(1).replace(',', ''))

                if title.startswith("[") and "moderator" in title.lower(): continue

                posts.append({
                    "title": title.strip()[:200], "subreddit": sr_name,
                    "score": score or 0, "comments": 0, "url": url,
                    "created": created_at.isoformat(), "body": body[:300]
                })
            except Exception:
                continue
    except Exception as e:
        print(f"[WARN] Reddit RSS error r/{sr_name}: {e}")
    return posts


def get_local_reddit(city: str, state: str, max_posts: int = 8) -> List[Dict]:
    """Fetch local subreddit posts via OAuth API, fall back to old RSS."""
    subs = get_subreddits(city, state)[:3]

    # Try OAuth API first
    try:
        from reddit_api_client import get_subreddit_posts, get_token
        token = get_token()
        all_posts = []
        for i, sub in enumerate(subs):
            posts, status = get_subreddit_posts(sub, sort="hot", limit=10, token=token)
            if isinstance(status, int) and status == 200:
                all_posts.extend(posts)
                print(f"      [Reddit] API: r/{sub} -> {len(posts)} posts")
            else:
                print(f"      [Reddit] API: r/{sub} -> status={status}")
            if i < len(subs) - 1:
                time.sleep(0.75)
        if all_posts:
            all_posts.sort(key=lambda x: x.get("score", 0), reverse=True)
            return all_posts[:max_posts]
    except Exception as e:
        print(f"      [Reddit] API error: {e} — falling back to RSS")

    # RSS fallback
    all_posts = []
    for i, sub in enumerate(subs):
        posts = _scrape_subreddit_rss(sub, limit=10)
        if posts:
            all_posts.extend(posts)
        if i < len(subs) - 1:
            time.sleep(random.uniform(8, 12))
    all_posts.sort(key=lambda x: int(x["score"]) if isinstance(x["score"], int) else 0, reverse=True)
    return all_posts[:max_posts]


# ---------- public entry ----------
def get_local_content(city: str, state: str, max_x: int = 8, max_reddit: int = 8) -> Dict:
    print(f"[ ] get_local_content: city={city}, state={state}")
    x_posts = get_local_x_posts(city, state, max_results=max_x)
    reddit_posts = get_local_reddit(city, state, max_posts=max_reddit)
    print(f"      X posts: {len(x_posts)}, Reddit posts: {len(reddit_posts)}")
    return {"x_posts": x_posts, "reddit_posts": reddit_posts}


if __name__ == "__main__":
    res = get_local_content("Louisville", "Kentucky", max_x=3, max_reddit=3)
    print("X:", res["x_posts"][:2])
    print("Reddit:", res["reddit_posts"][:2])
