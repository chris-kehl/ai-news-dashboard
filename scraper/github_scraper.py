#!/usr/bin/env python3
"""GitHub trending AI repositories scraper via REST API only."""

import requests
import time
from datetime import datetime, timedelta
from scraper_utils import fetch_json_with_retry, load_scraper_cache, save_scraper_cache

HEADERS = {
    "Accept": "application/vnd.github.v3+json",
    "User-Agent": "AI-News-Dashboard/1.0"
}

def get_ai_repos():
    """Fetch top AI repos via GitHub Search API (no bs4 needed)."""
    cached = load_scraper_cache("github_ai_repos", max_age_minutes=60)
    if cached:
        print("      Using cached GitHub repos")
        return cached
    repos = []
    queries = [
        "topic:llm created:>2024-01-01 sort:stars",
        "topic:ai-agent created:>2024-01-01 sort:stars",
        "topic:machine-learning created:>2024-01-01 sort:stars",
        "topic:bittensor created:>2024-01-01 sort:stars",
        "llm stars:>500 language:python sort:stars",
        "ai stars:>500 language:rust sort:stars",
    ]

    for q in queries:
        try:
            data = fetch_json_with_retry(
                "https://api.github.com/search/repositories",
                params={"q": q, "per_page": 5},
                headers=HEADERS,
                timeout=15,
                max_retries=2,
                backoff_base=3.0,
                retry_codes=(429, 403, 502, 503)
            )
            if not data:
                continue
            for item in data.get("items", []):
                repos.append({
                    "name": item["full_name"],
                    "description": (item.get("description") or "No description")[:130],
                    "stars": item["stargazers_count"],
                    "language": item.get("language") or "Unknown",
                    "url": item["html_url"],
                    "updated": item.get("updated_at", "")
                })
            time.sleep(2)
        except Exception as e:
            print(f"      GitHub fetch error: {e}")

    # Also get recent trending via /search with pushed: date filter
    try:
        week_ago = (datetime.utcnow() - timedelta(days=7)).strftime("%Y-%m-%d")
        data = fetch_json_with_retry(
            "https://api.github.com/search/repositories",
            params={"q": f"stars:>1000 pushed:>{week_ago}", "sort": "updated", "order": "desc", "per_page": 8},
            headers=HEADERS,
            timeout=15,
            max_retries=2,
            backoff_base=3.0
        )
        if data:
            for item in data.get("items", []):
                repos.append({
                    "name": item["full_name"],
                    "description": (item.get("description") or "No description")[:130],
                    "stars": item["stargazers_count"],
                    "language": item.get("language") or "Unknown",
                    "url": item["html_url"],
                    "updated": item.get("updated_at", "")
                })
    except Exception as e:
        print(f"      GitHub recent trending error: {e}")

    # Deduplicate and sort by stars
    seen = set()
    unique = []
    for r in repos:
        if r["name"] not in seen:
            seen.add(r["name"])
            unique.append(r)

    unique.sort(key=lambda x: x["stars"], reverse=True)
    result = unique[:12]
    if result:
        save_scraper_cache("github_ai_repos", result)
    return result


def get_trending_repos(language="python", since="daily"):
    """Entry point called by main.py."""
    return get_ai_repos()


if __name__ == "__main__":
    repos = get_ai_repos()
    print(f"Fetched {len(repos)} trending repos")
    for r in repos[:8]:
        print(f"[{r['stars']}] {r['name']} ({r['language']})")
