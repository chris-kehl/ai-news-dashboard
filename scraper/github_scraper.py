#!/usr/bin/env python3
"""GitHub trending AI repositories scraper."""

import requests
from bs4 import BeautifulSoup
import re

def get_trending_repos(language="python", since="daily"):
    """Fetch trending AI repositories from GitHub."""
    repos = []
    
    # AI-related search queries
    ai_queries = [
        "llm",
        "ai-agent",
        "machine-learning",
        "transformers",
        "bittensor"
    ]
    
    headers = {
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "AI-News-Dashboard/1.0"
    }
    
    # GitHub trending page
    try:
        response = requests.get(
            f"https://github.com/trending/{language}?since={since}",
            headers=headers,
            timeout=15
        )
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            articles = soup.find_all('article', class_='Box-row')
            
            for article in articles[:10]:
                try:
                    link = article.find('h2', class_='h3').find('a')
                    name = link.get_text(strip=True).replace('\n', '').replace(' ', '')
                    url = f"https://github.com{link['href']}"
                    
                    desc_elem = article.find('p', class_='col-9')
                    description = desc_elem.get_text(strip=True) if desc_elem else ""
                    
                    lang_elem = article.find('span', itemprop='programmingLanguage')
                    language = lang_elem.get_text(strip=True) if lang_elem else "Unknown"
                    
                    stars_elem = article.find('a', class_='Link--muted', href=re.compile(r'/stargazers'))
                    stars_text = stars_elem.get_text(strip=True) if stars_elem else "0"
                    stars = int(re.sub(r'[^0-9]', '', stars_text)) if stars_text else 0
                    
                    repos.append({
                        "name": name,
                        "description": description[:120],
                        "stars": stars,
                        "language": language,
                        "url": url
                    })
                except Exception as e:
                    continue
    except Exception as e:
        print(f"GitHub trending error: {e}")
    
    # Also search for AI-specific repos
    try:
        for query in ai_queries[:2]:
            response = requests.get(
                f"https://api.github.com/search/repositories",
                params={
                    "q": f"{query} created:>2024-01-01 sort:stars",
                    "per_page": 5
                },
                headers=headers,
                timeout=10
            )
            if response.status_code == 200:
                data = response.json()
                for item in data.get("items", [])[:5]:
                    repos.append({
                        "name": item["full_name"],
                        "description": item.get("description", "")[:120] or "No description",
                        "stars": item["stargazers_count"],
                        "language": item.get("language", "Unknown") or "Unknown",
                        "url": item["html_url"]
                    })
    except Exception as e:
        print(f"GitHub search error: {e}")
    
    # Remove duplicates and sort
    seen = set()
    unique_repos = []
    for repo in repos:
        if repo["name"] not in seen:
            seen.add(repo["name"])
            unique_repos.append(repo)
    
    unique_repos.sort(key=lambda x: x["stars"], reverse=True)
    return unique_repos[:10]

if __name__ == "__main__":
    repos = get_trending_repos()
    print(f"Fetched {len(repos)} trending repos")
    for r in repos[:5]:
        print(f"[{r['stars']}] {r['name']} ({r['language']})")
