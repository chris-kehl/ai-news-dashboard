#!/usr/bin/env python3
"""Reddit API client using OAuth password grant (username+password).

Requires env vars:
    REDDIT_CLIENT_ID     – from reddit.com/prefs/apps (personal use script)
    REDDIT_CLIENT_SECRET – from the same app
    REDDIT_USERNAME      – your Reddit username
    REDDIT_PASSWORD      – your Reddit password
"""

import os, requests, time
from datetime import datetime, timezone

TOKEN_URL = "https://www.reddit.com/api/v1/access_token"
API_BASE = "https://oauth.reddit.com"


def _env(var):
    return os.environ.get(var, "").strip()


def _missing():
    return [v for v in ("REDDIT_CLIENT_ID","REDDIT_CLIENT_SECRET",
                        "REDDIT_USERNAME","REDDIT_PASSWORD") if not _env(v)]


def get_token():
    """Obtain OAuth access token via password grant."""
    miss = _missing()
    if miss:
        raise RuntimeError(f"Missing env vars for Reddit API: {', '.join(miss)}")

    r = requests.post(
        TOKEN_URL,
        auth=(_env("REDDIT_CLIENT_ID"), _env("REDDIT_CLIENT_SECRET")),
        headers={"User-Agent": "AI-News-Dashboard/1.0 by " + _env("REDDIT_USERNAME")},
        data={"grant_type": "password",
              "username": _env("REDDIT_USERNAME"),
              "password": _env("REDDIT_PASSWORD")},
        timeout=15
    )
    r.raise_for_status()
    j = r.json()
    if "access_token" not in j:
        raise RuntimeError(f"Reddit auth failed: {j.get('error','unknown')}")
    return j["access_token"]


def auth_headers(token=None):
    """Return headers with Bearer token."""
    if token is None:
        token = get_token()
    return {
        "Authorization": f"Bearer {token}",
        "User-Agent": "AI-News-Dashboard/1.0 by " + _env("REDDIT_USERNAME"),
    }


def _format_post(child):
    """Normalize a Reddit listing child into our dict format."""
    d = child.get("data", {})
    created = datetime.fromtimestamp(d.get("created_utc", 0), tz=timezone.utc).isoformat()
    permalink = d.get("permalink", "")
    domain = d.get("domain", "")
    # Prefer external URL unless it's a self-post
    url = d.get("url_overridden_by_dest") or d.get("url", "")
    if permalink and not url.startswith("http"):
        url = f"https://www.reddit.com{permalink}"
    return {
        "title": (d.get("title") or "")[:200],
        "subreddit": d.get("subreddit", ""),
        "score": d.get("score", 0),
        "comments": d.get("num_comments", 0),
        "url": url,
        "created": created,
        "author": d.get("author", ""),
        "domain": domain,
    }


def get_subreddit_posts(subreddit, sort="hot", limit=15, period="day", token=None):
    """Fetch posts via OAuth JSON API.

    sort ∈ {"hot","new","top","rising"}
    period ∈ {"hour","day","week","month","year","all"} (only for top)
    """
    sub = subreddit.strip("/r").strip("/")
    url = f"{API_BASE}/r/{sub}/{sort}.json?limit={limit}"
    if sort == "top":
        url += f"&t={period}"
    try:
        r = requests.get(url, headers=auth_headers(token), timeout=20)
        if r.status_code == 429:
            time.sleep(2)
            r = requests.get(url, headers=auth_headers(), timeout=20)
        if r.status_code != 200:
            return [], r.status_code
        j = r.json()
        posts = [_format_post(c) for c in j.get("data", {}).get("children", [])]
        return posts, 200
    except Exception as e:
        return [], str(e)


def get_multiple(subs, limit_per=10, sort="hot", period="day", token=None):
    """Fetch from multiple subreddits; return combined + sorted-by-score list."""
    all_posts = []
    for sub in subs:
        posts, status = get_subreddit_posts(sub, sort=sort, limit=limit_per, period=period, token=token)
        if isinstance(status, int) and status == 200:
            all_posts.extend(posts)
            if len(subs) > 1:
                time.sleep(0.75)  # 750ms between requests to stay polite
    all_posts.sort(key=lambda x: x.get("score", 0), reverse=True)
    return all_posts


def get_worldnews_posts(limit=15, period="day", token=None):
    """Convenience wrapper for r/worldnews top."""
    posts, status = get_subreddit_posts("worldnews", sort="top", limit=limit, period=period, token=token)
    return posts if isinstance(status, int) and status == 200 else []


def get_hot_ai_posts(subreddits=None, limit=15, token=None):
    """Get AI-relevant posts from tech subreddits."""
    if subreddits is None:
        subreddits = ["machinelearning", "artificial", "LocalLLaMA", "OpenAI"]
    posts = get_multiple(subreddits, limit_per=limit, sort="hot", token=token)
    # Extra scoring boost for AI keywords in title
    ai_kw = ["llm", "model", "ai", "agent", "inference", "gpu", "nvidia",
             "openai", "anthropic", "claude", "gpt", "transformer", "neural",
             "machine learning", "autonomous", "benchmark", "quantize",
             "fine-tun", "training"]
    for p in posts:
        t = p.get("title", "").lower()
        bonus = sum(1 for kw in ai_kw if kw in t)
        if bonus:
            p["score"] = p.get("score", 0) + bonus * 50
    posts.sort(key=lambda x: x.get("score", 0), reverse=True)
    return posts
