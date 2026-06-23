#!/usr/bin/env python3
"""GitHub trending AI repositories scraper via REST API."""
import requests, time, os
from datetime import datetime, timedelta

HEADERS = {"Accept": "application/vnd.github.v3+json", "User-Agent": "AI-News-Dashboard/1.0"}

def get_ai_repos():
    repos = []
    month_ago = (datetime.utcnow() - timedelta(days=30)).strftime("%Y-%m-%d")
    week_ago = (datetime.utcnow() - timedelta(days=7)).strftime("%Y-%m-%d")
    queries = [
        f"topic:llm created:>{month_ago} sort:stars",
        f"stars:>500 pushed:>{week_ago} language:python sort:stars",
        f"stars:>300 pushed:>{week_ago} language:rust sort:stars",
    ]
    gh_token = os.getenv("GITHUB_TOKEN", "")
    req_headers = HEADERS.copy()
    if gh_token:
        req_headers["Authorization"] = f"token {gh_token}"
        rate_limit = 30
    else:
        rate_limit = 8
    req_count = 0
    for q in queries:
        if req_count >= rate_limit:
            print("      GitHub rate limit approaching")
            break
        try:
            resp = requests.get("https://api.github.com/search/repositories", params={"q": q, "per_page": 8}, headers=req_headers, timeout=15)
            req_count += 1
            if resp.status_code == 200:
                for item in resp.json().get("items", []):
                    repos.append({"name": item["full_name"], "description": (item.get("description") or "No description")[:130], "stars": item["stargazers_count"], "language": item.get("language") or "Unknown", "url": item["html_url"], "updated": item.get("updated_at", "")})
            elif resp.status_code == 403:
                print("      GitHub rate limited (403)")
                break
            else:
                print(f"      GitHub query returned {resp.status_code}")
            time.sleep(2)
        except Exception as e:
            print(f"      GitHub fetch error: {e}")
    seen = set()
    unique = []
    for r in repos:
        if r["name"] not in seen and r["stars"] > 0:
            seen.add(r["name"])
            unique.append(r)
    unique.sort(key=lambda x: x["stars"], reverse=True)
    return unique[:12]

def get_trending_repos(language="python", since="daily"):
    return get_ai_repos()

if __name__ == "__main__":
    repos = get_ai_repos()
    print(f"Fetched {len(repos)} trending repos")
    for r in repos[:8]:
        print(f"[{r['stars']}] {r['name']} ({r['language']})")
