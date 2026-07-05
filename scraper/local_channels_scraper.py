#!/usr/bin/env python3
"""Dynamic local TV station + newspaper scraper for ANY US city.

Uses DuckDuckGo site search to discover local news stations for the given city,
then hits their homepages for headlines. No hardcoded Louisville-only stations.
"""
import requests, re, time, json
from urllib.parse import quote, unquote
from datetime import datetime

BROWSER = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/125.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9',
}

REGEX_HEADLINE = re.compile(r'<a[^>]+href=["\']([^"\']+)["\'][^>]*>([^<]{20,120})</a>', re.IGNORECASE)

KNOWN_TOP_DOMAINS = {
    'nbc', 'abc', 'cbs', 'fox', 'npr', 'cnn', 'ap', 'cable', 'broadcasting',
    'gannett', 'hearst', 'tribune', 'ebr', 'journal', 'courier', 'enquirer',
    'sentinel', 'gazette', 'herald', 'dispatch', 'post', 'times', 'chronicle',
    'news', 'wkyt', 'wlky', 'wave', 'whas', 'wdrb', 'wmur', 'wgal', 'wral',
    'ksdk', 'ktvu', 'kron', 'wbz', 'necn', 'wxyz', 'wdiv', 'kcnc', 'kusa',
    'kdka', 'wpvi', 'wnbc', 'wnyj', 'wcvb', 'wgn', 'kttv', 'ktla', 'kcbs',
}


def _is_article_url(url):
    u = url.lower()
    skip = ['video', 'live', 'weather', 'traffic', 'sports', 'javascript:', '#', 'mailto:', 'login', 'subscribe', 'privacy', 'terms', 'careers', 'about']
    return all(s not in u for s in skip) and len(u) > 20


def _is_good_headline(text):
    t = text.strip()
    bad = ['home', 'menu', 'search', 'login', 'subscribe', 'advertise', 'contact us', 'privacy policy', 'terms of use', 'sign up', 'watch live', 'skip to', 'newsletter']
    return len(t) > 20 and len(t) < 150 and all(b not in t.lower() for b in bad)


def _extract_domain(url):
    m = re.search(r'https?://([^/]+)', url)
    return m.group(1) if m else ''


def ddg_site_search(site, query='news', max_results=8):
    """DuckDuckGo HTML search scoped to a domain."""
    try:
        q = f'site:{site} {query}'
        url = f'https://html.duckduckgo.com/html/?q={quote(q)}'
        r = requests.get(url, headers=BROWSER, timeout=20)
        if r.status_code != 200:
            return []
        html = r.text
        results = []
        for m in re.finditer(r'<a[^>]+class=["\']result__a["\'][^>]+href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', html, re.IGNORECASE | re.DOTALL):
            href = m.group(1)
            title = re.sub(r'<[^>]+>', '', m.group(2)).strip()
            if _is_good_headline(title) and href.startswith('http'):
                results.append({'title': title, 'url': href, 'source': site})
        if not results:
            for m in re.finditer(r'<a[^>]+href="/l/\?[^"]*uddg=([^"&]+)', html):
                decoded = requests.utils.unquote(m.group(1))
                results.append({'title': 'News from ' + site, 'url': decoded, 'source': site})
        return results[:max_results]
    except Exception as e:
        print(f'      DDG search error for {site}: {e}')
        return []


def discover_local_sites(city, state):
    """Use DuckDuckGo to discover local news station URLs for a city."""
    query = f'{city} {state} news TV station newspaper'
    found = set()
    try:
        url = f'https://html.duckduckgo.com/html/?q={quote(query)}'
        r = requests.get(url, headers=BROWSER, timeout=20)
        if r.status_code == 200:
            html = r.text
            for m in re.finditer(r'https?://([a-zA-Z0-9][-a-zA-Z0-9]*\.)+[a-zA-Z]{2,}', html):
                domain = _extract_domain(m.group(0))
                if any(k in domain.lower() for k in KNOWN_TOP_DOMAINS):
                    found.add(domain)
            for m in re.finditer(r'href="https?://([^"]+)"', html):
                domain = _extract_domain('https://' + m.group(1))
                if any(k in domain.lower() for k in KNOWN_TOP_DOMAINS):
                    found.add(domain)
    except Exception as e:
        print(f'[WARN] DDG discovery failed for {city}: {e}')
    return list(found)


def scrape_homepage(domain, label):
    """Grab headlines from a news site homepage."""
    try:
        url = f'https://{domain}'
        r = requests.get(url, headers=BROWSER, timeout=15)
        if r.status_code != 200:
            return []
        html = r.text
        results = []
        seen = set()
        for m in REGEX_HEADLINE.finditer(html):
            href = m.group(1)
            title = re.sub(r'<[^>]+>', '', m.group(2)).strip()
            if not href.startswith('http'):
                if href.startswith('/'):
                    href = f'https://{domain}{href}'
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
        # print(f'      Homepage scrape error {domain}: {e}')
        return []


def get_local_channel_news(city='Louisville', state='Kentucky', max_per_station=6, max_sites=6):
    """Aggregate local news from dynamically discovered TV stations + newspapers."""
    all_results = []
    seen_titles = set()

    sites = discover_local_sites(city, state)
    if not sites:
        sites = ['wlky.com', 'wave3.com', 'whas11.com', 'wdrb.com', 'courier-journal.com']
    sites = sites[:max_sites]

    print(f'      Discovered {len(sites)} local news sites for {city}')
    for domain in sites:
        articles = scrape_homepage(domain, domain.split('.')[0].upper())
        if len(articles) < 3:
            more = ddg_site_search(domain, query=f'{city} OR {state}', max_results=6)
            for a in more:
                key = a['title'].lower()[:40]
                if key not in seen_titles:
                    seen_titles.add(key)
                    articles.append(a)
        for a in articles[:max_per_station]:
            key = a['title'].lower()[:40]
            if key not in seen_titles:
                seen_titles.add(key)
                all_results.append(a)

    return all_results[:15]


if __name__ == '__main__':
    city = 'Louisville'
    state = 'Kentucky'
    if __import__('sys').argv[1:]:
        city = __import__('sys').argv[1]
    if len(__import__('sys').argv) > 2:
        state = __import__('sys').argv[2]
    news = get_local_channel_news(city, state)
    print(f'\nTotal unique local articles: {len(news)}')
    for n in news[:12]:
        print(f'  [{n["source"][:18]:18s}] {n["title"][:70]}...')
