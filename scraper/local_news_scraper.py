#!/usr/bin/env python3
"""Local news scraper using NewsAPI free tier (100 req/day)."""

import os
import requests
import json
from datetime import datetime

HEADERS = {"User-Agent": "AI-News-Dashboard/1.0"}

def get_local_news(city, state, api_key=None):
    """Fetch local news via NewsAPI. Falls back to generic US news if no key."""
    key = api_key or os.environ.get("NEWSAPI_KEY", "")
    if not key:
        return {"error": "NEWSAPI_KEY not set. Get free key at newsapi.org", "articles": []}
    
    query = f'"{city}" OR "{state}"'
    try:
        url = "https://newsapi.org/v2/everything"
        params = {
            "q": query,
            "sortBy": "publishedAt",
            "language": "en",
            "pageSize": 8,
            "apiKey": key
        }
        r = requests.get(url, params=params, headers=HEADERS, timeout=15)
        r.raise_for_status()
        data = r.json()
        articles = []
        for a in data.get("articles", []):
            articles.append({
                "title": a.get("title", ""),
                "url": a.get("url", ""),
                "source": a.get("source", {}).get("name", ""),
                "published": a.get("publishedAt", "")[:16],
                "description": (a.get("description") or "")[:200]
            })
        return {
            "city": city,
            "state": state,
            "timestamp": datetime.utcnow().isoformat(),
            "articles": articles
        }
    except Exception as e:
        print(f"Local news error: {e}")
        return {"error": str(e), "articles": []}

if __name__ == "__main__":
    import sys
    city = sys.argv[1] if len(sys.argv) > 1 else "New York"
    state = sys.argv[2] if len(sys.argv) > 2 else "NY"
    print(json.dumps(get_local_news(city, state), indent=2))
