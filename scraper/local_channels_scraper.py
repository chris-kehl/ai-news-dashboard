#!/usr/bin/env python3
"""Direct local TV station + newspaper scraper for Louisville/KY.

Hits real local station homepages + DuckDuckGo site search to pull
headlines from WLKY, WAVE, WHAS, WDRB, Courier-Journal.
Runs scraper-side (no CORS issues).
"""
import requests
import re
import time
from urllib.parse import quote
from datetime import datetime

BROWSER = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/125.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9',
}

LOUISVILLE_STATIONS = [
    ('WLKY 32 (CBS)', 'wlky.com'),
    ('WAVE 3 (NBC)', 'wave3.com'),
    ('WHAS 11 (ABC)', 'whas11.com'),
    ('WDRB 41 (FOX)', 'wdrb.com'),
    ('Courier-Journal', 'courier-journal.com'),
    ('Kentucky Today', 'kentuckytoday.com'),
]

REGEX_HEADLINE = re.compile(r'<a[^>]+href=["\']([^"\']+)["\'][^>]*>([^<]{20,120})</a>', re.IGNORECASE)
REGEX_TITLE_FROM_META = re.compile(r'<title>([^<]{10,200})</title>', re.IGNORECASE)

def _is_article_url(url):
    u = url.lower()
    skip = ['video', 'live', 'weather', 'traffic', 'sports', 'javascript:', '#', 'mailto:', 'login', 'subscribe', 'privacy', 'terms']
    return all(s not in u for s in skip) and len(u) > 20

def _is_good_headline(text):
    t = text.strip()
    bad = ['home', 'menu', 'search', 'login', 'subscribe', 'advertise', 'contact us', 'privacy policy', 'terms of use', 'sign up', 'watch live']
    return len(t) > 20 and len(t) < 150 and all(b not in t.lower() for b in bad)

def duckduckgo_site_search(site, query='news', max_results=8):
    """Use DuckDuckGo HTML search for a specific site."""
    try:
        q = f'site:{site} {query}'
        url = f'https://html.duckduckgo.com/html/?q={quote(q)}'
        r = requests.get(url, headers=BROWSER, timeout=20)
        if r.status_code != 200:
            return []
        html = r.text
        results = []
        # DDG results snippets
        for m in re.finditer(r'<a[^>]+class=["\']result__a["\'][^>]+href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', html, re.IGNORECASE | re.DOTALL):
            href = m.group(1)
            title = re.sub(r'<[^>]+>', '', m.group(2)).strip()
            if _is_good_headline(title) and href.startswith('http'):
                results.append({'title': title, 'url': href, 'source': site})
        # Also grab redirect URLs (DDG wraps links)
        if not results:
            for m in re.finditer(r'<a[^>]+href="/l/\?[^"]*uddg=([^"&]+)', html):
                decoded = requests.utils.unquote(m.group(1))
                # Need titles from nearby text
                results.append({'title': 'News from ' + site, 'url': decoded, 'source': site})
        return results[:max_results]
    except Exception as e:
        print(f'      DDG search error for {site}: {e}')
        return []

def scrape_station_homepage(site, label):
    """Try to grab headlines from the site's homepage directly."""
    try:
        url = f'https://{site}' if not site.startswith('http') else site
        r = requests.get(url, headers=BROWSER, timeout=15)
        if r.status_code != 200:
            return []
        html = r.text
        results = []
        # Find all links with decent text
        seen = set()
        for m in REGEX_HEADLINE.finditer(html):
            href = m.group(1)
            title = re.sub(r'<[^>]+>', '', m.group(2)).strip()
            if not href.startswith('http'):
                if href.startswith('/'):
                    href = f'https://{site}{href}'
                elif href.startswith('//'):
                    href = f'https:{href}'
                else:
                    continue
            if not _is_article_url(href) or not _is_good_headline(title):
                continue
            key = title.lower()[:40]
            if key in seen:
                continue
            seen.add(key)
            results.append({'title': title, 'url': href, 'source': label})
        return results[:10]
    except Exception as e:
        print(f'      Homepage scrape error {site}: {e}')
        return []

def get_local_channel_news(city='Louisville', state='Kentucky', max_per_station=6):
    """Aggregate from all local TV stations + newspapers."""
    all_results = []
    seen_titles = set()
    
    print(f'      Hitting local stations for {city}...')
    for label, site in LOUISVILLE_STATIONS:
        print(f'        -> {label} ({site})')
        # Strategy 1: Try homepage scrape
        articles = scrape_station_homepage(site, label)
        time.sleep(0.5)
        
        # Strategy 2: Supplement with DDG site search if homepage light
        if len(articles) < 3:
            more = duckduckgo_site_search(site, query=f'{city} OR {state}', max_results=6)
            for a in more:
                key = a['title'].lower()[:40]
                if key not in seen_titles:
                    seen_titles.add(key)
                    articles.append(a)
            time.sleep(0.8)
        
        for a in articles[:max_per_station]:
            key = a['title'].lower()[:40]
            if key not in seen_titles:
                seen_titles.add(key)
                all_results.append(a)
    
    return all_results

if __name__ == '__main__':
    news = get_local_channel_news()
    print(f'\nTotal unique local articles: {len(news)}')
    for n in news[:12]:
        print(f'  [{n["source"][:18]:18s}] {n["title"][:70]}...')
