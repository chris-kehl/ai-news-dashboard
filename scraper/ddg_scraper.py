#!/usr/bin/env python3
"""DuckDuckGo-based fallback scraper. No API key required.

Provides news search + text search fallbacks when RSS feeds or APIs
return 429/403/empty.  Cached to disk per-scraper to survive outages.
"""

import json
import os
import time
from datetime import datetime, timedelta

try:
    from duckduckgo_search import DDGS
except ImportError:
    DDGS = None

_CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".cache")
os.makedirs(_CACHE_DIR, exist_ok=True)

_BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


def _cache_path(key: str) -> str:
    return os.path.join(_CACHE_DIR, f"ddg_{key}.json")


def _load_cache(key: str, max_age_minutes: int = 30):
    path = _cache_path(key)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            cached = json.load(f)
        ts = cached.get("_cached_at", "")
        if ts and datetime.utcnow() - datetime.fromisoformat(ts) <= timedelta(minutes=max_age_minutes):
            return cached.get("data")
    except Exception:
        pass
    return None


def _save_cache(key: str, data):
    try:
        with open(_cache_path(key), "w", encoding="utf-8") as f:
            json.dump({"_cached_at": datetime.utcnow().isoformat(), "data": data}, f, ensure_ascii=False)
    except Exception:
        pass


def ddg_news(query: str, max_results: int = 10, region: str = "us-en", cache_key: str = ""):
    """Search DuckDuckGo news. Returns list[dict] or empty list on failure.

    Args:
        query: search string
        max_results: number of results to return
        region: DDG region code (us-en, uk-en, etc)
        cache_key: if provided, cache result under this key for 30 min
    """
    if DDGS is None:
        print("      DDG library not installed")
        return []

    if cache_key:
        cached = _load_cache(cache_key)
        if cached is not None:
            return cached

    results = []
    attempt = 0
    while attempt < 3:
        try:
            with DDGS(headers=_BROWSER_HEADERS, timeout=15) as ddgs:
                for r in ddgs.news(keywords=query, region=region, safesearch="off", max_results=max_results):
                    results.append({
                        "title": (r.get("title") or "")[:200],
                        "url": (r.get("url") or "").strip(),
                        "source": (r.get("source") or "DDG News")[:40],
                        "published": (r.get("date") or "")[:20],
                        "description": (r.get("body") or "")[:300]
                    })
            break
        except Exception as e:
            attempt += 1
            print(f"      DDG news error (attempt {attempt}): {e}")
            time.sleep(2 ** attempt)

    if cache_key:
        _save_cache(cache_key, results)
    return results


def ddg_text(query: str, max_results: int = 10, cache_key: str = ""):
    """Generic DuckDuckGo text search fallback."""
    if DDGS is None:
        return []

    if cache_key:
        cached = _load_cache(cache_key)
        if cached is not None:
            return cached

    results = []
    attempt = 0
    while attempt < 3:
        try:
            with DDGS(headers=_BROWSER_HEADERS, timeout=15) as ddgs:
                for r in ddgs.text(keywords=query, safesearch="off", max_results=max_results):
                    results.append({
                        "title": (r.get("title") or "")[:200],
                        "url": (r.get("href") or "").strip(),
                        "source": "DDG",
                        "published": "",
                        "description": (r.get("body") or "")[:300]
                    })
            break
        except Exception as e:
            attempt += 1
            print(f"      DDG text error (attempt {attempt}): {e}")
            time.sleep(2 ** attempt)

    if cache_key:
        _save_cache(cache_key, results)
    return results


def ddg_crypto_news(max_results: int = 10):
    """Pre-canned crypto news query."""
    return ddg_news(
        "cryptocurrency bitcoin ethereum market news today",
        max_results=max_results,
        cache_key="crypto_news"
    )


def ddg_world_news(max_results: int = 10):
    """Pre-canned world headlines query."""
    return ddg_news(
        "world news today geopolitics",
        max_results=max_results,
        cache_key="world_news"
    )


def ddg_defense_news(max_results: int = 10):
    """Pre-canned defense / conflict news query."""
    return ddg_news(
        "defense military Iran Israel Ukraine conflict news",
        max_results=max_results,
        cache_key="defense_news"
    )


def ddg_local_news(city: str, state: str, max_results: int = 8):
    """Local news fallback."""
    return ddg_news(
        f"{city} {state} local news today",
        max_results=max_results,
        cache_key=f"local_{city}_{state}"
    )


def ddg_ai_reddit(max_results: int = 10):
    """AI-focused HackerNews / tech discussion fallback."""
    return ddg_news(
        "AI LLM machine learning openai anthropic news",
        max_results=max_results,
        cache_key="ai_news"
    )


if __name__ == "__main__":
    print("Crypto:", len(ddg_crypto_news(5)))
    print("World: ", len(ddg_world_news(5)))
    print("Defense:", len(ddg_defense_news(5)))
