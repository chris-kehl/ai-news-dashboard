#!/usr/bin/env python3
"""Shared utilities for scrapers: retry with backoff + JSON caching."""

import json
import os
import time
from datetime import datetime, timedelta
import requests

_CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".cache")
os.makedirs(_CACHE_DIR, exist_ok=True)

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
}


# ─── Retry wrapper ────────────────────────────────────────────────────────────

def fetch_with_retry(
    url,
    *,
    headers=None,
    params=None,
    timeout=15,
    max_retries=3,
    backoff_base=2.0,
    retry_codes=(429, 403, 502, 503, 504),
    method="get"
):
    """HTTP GET/POST with exponential backoff on 429 / 5xx.

    Returns the response object or None after exhausting retries.
    Prints per-attempt status so logs show what happened.
    """
    hdr = headers or DEFAULT_HEADERS.copy()
    last_err = None
    for attempt in range(1, max_retries + 1):
        try:
            fn = requests.get if method == "get" else requests.post
            kwargs = {"headers": hdr, "timeout": timeout}
            if params is not None:
                kwargs["params"] = params
            r = fn(url, **kwargs)
            if r.status_code in retry_codes:
                wait = backoff_base ** attempt
                print(f"      {r.status_code} on {url[:60]}… retry {attempt}/{max_retries} in {wait:.1f}s")
                time.sleep(wait)
                continue
            return r
        except requests.exceptions.ConnectionError as e:
            last_err = e
            wait = backoff_base ** attempt
            print(f"      Connection error (attempt {attempt}): {e} — waiting {wait:.1f}s")
            time.sleep(wait)
        except requests.exceptions.Timeout as e:
            last_err = e
            wait = backoff_base ** attempt
            print(f"      Timeout (attempt {attempt}): {e} — waiting {wait:.1f}s")
            time.sleep(wait)
        except Exception as e:
            last_err = e
            print(f"      Unexpected error (attempt {attempt}): {e}")
            time.sleep(backoff_base ** attempt)
    if last_err:
        print(f"      Giving up on {url[:60]}… after {max_retries}: {last_err}")
    return None


def fetch_json_with_retry(url, **kw):
    """Convenience: fetch_with_retry + .json() with blank fallback."""
    r = fetch_with_retry(url, **kw)
    if r is None:
        return {}
    try:
        return r.json()
    except Exception as e:
        print(f"      JSON parse error: {e}")
        return {}


# ─── Per-scraper JSON caching ────────────────────────────────────────────────

def _cache_path(name: str) -> str:
    safe = "".join(c if c.isalnum() or c in "_-" else "_" for c in name)
    return os.path.join(_CACHE_DIR, f"{safe}.json")


def load_scraper_cache(name: str, max_age_minutes: int = 30):
    """Return cached data dict or None if stale / missing."""
    path = _cache_path(name)
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


def save_scraper_cache(name: str, data):
    """Persist data dict with timestamp."""
    try:
        with open(_cache_path(name), "w", encoding="utf-8") as f:
            json.dump({"_cached_at": datetime.utcnow().isoformat(), "data": data}, f, ensure_ascii=False)
    except Exception:
        pass
