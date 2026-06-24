#!/usr/bin/env python3
"""Main orchestrator - runs all scrapers and generates data.json."""

import json
import sys
import os
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from reddit_scraper import get_reddit_posts
from crypto_scraper import get_crypto_data as get_crypto
from ap_news_scraper import get_ap_data
from stocks_scraper import get_stocks_data, generate_ticker_json
from defense_scraper import get_defense_data
from weather_scraper import get_weather
from local_news_scraper import get_local_news
from local_channels_scraper import get_local_channel_news
from reddit_local_scraper import get_local_reddit_from_weather
from bittensor_scraper import get_bittensor_intelligence
from github_scraper import get_trending_repos
from summarizer import create_daily_summary

# Load weather zip from env
WEATHER_ZIP = os.environ.get("WEATHER_ZIP", "10001")
NEWSAPI_KEY = os.environ.get("NEWSAPI_KEY", "")

def build_dashboard_data():
    """Run all scrapers and build the data.json payload."""
    print("=" * 50)
    print(f"AI News Dashboard - Update Started")
    print(f"Time: {datetime.now().isoformat()}")
    print("=" * 50)
    
    # Fetch all data
    print("\n[1/10] Fetching Reddit posts...")
    reddit_posts = get_reddit_posts()
    print(f"      Found {len(reddit_posts)} posts")
    
    print("\n[2/10] Fetching Crypto prices & news...")
    crypto_data = get_crypto()
    print(f"      Found {len(crypto_data.get('prices',[]))} coins, {len(crypto_data.get('news',[]))} news items")
    
    print("\n[3/10] Fetching AP News & world headlines...")
    news_data = get_ap_data()
    print(f"      Found {len(news_data.get('all_news',[]))} news items")
    
    print("\n[4/10] Fetching hottest stocks...")
    stocks_data = get_stocks_data()
    print(f"      Trending: {len(stocks_data.get('trending',[]))}, Meme: {len(stocks_data.get('meme_momentum',[]))}")

    print("\n[4.5/10] Generating market ticker...")
    ticker_data = generate_ticker_json()
    print(f"      Ticker items: {len(ticker_data.get('items',[]))}")
    
    print("\n[5/10] Fetching Defense / Geopolitics...")
    defense_data = get_defense_data()
    print(f"      Found {len(defense_data.get('conflicts',[]))} conflict articles")
    
    print(f"\n[6/10] Fetching weather for {WEATHER_ZIP}...")
    weather_data = get_weather(WEATHER_ZIP)
    city = weather_data.get('city', '')
    temp = weather_data.get('current', {}).get('temperature', 'N/A')
    print(f"      {city}: {temp}F")
    print(f"\n[7/10] Fetching local news (multi-source)...")
    state = weather_data.get('state', '')
    local_news = get_local_news(city, state, NEWSAPI_KEY)
    print(f"      Found {len(local_news.get('articles',[]))} local articles")
    
    
    print(f"\n[7.5/10] Fetching local TV stations + newspapers...")
    local_channels = get_local_channel_news(city, state)
    print(f"      Found {len(local_channels)} articles from local channels")
    print(f"\n[7.5/10] Fetching local Reddit (r/{city.lower()}, r/{state.lower()})...")
    local_reddit = get_local_reddit_from_weather(weather_data, max_posts=6)
    print(f"      Found {len(local_reddit)} local reddit posts")
    
    print("\n[8/10] Fetching GitHub trending repos...")
    github_repos = get_trending_repos()
    print(f"      Found {len(github_repos)} repos")
    
    print("\n[9/10] Fetching Bittensor intelligence...")
    bittensor_data = get_bittensor_intelligence()
    print(f"      TAO: ${bittensor_data.get('price', 0):.2f}")
    
    print("\n[10/10] Generating summary...")
    summary_data = create_daily_summary(reddit_posts, [], github_repos, bittensor_data)
    print(f"      Summary length: {len(summary_data['summary'])} chars")
    
    # Build data.json
    data = {
        "timestamp": datetime.now().isoformat(),
        "zip": WEATHER_ZIP,
        "summary": summary_data["summary"],
        "signals": summary_data["signals"],
        "reddit": reddit_posts,
        "local_reddit": local_reddit,
        "crypto": crypto_data,
        "news": news_data.get("all_news", []),
        "stocks": stocks_data,
        "ticker": ticker_data,
        "defense": defense_data.get("conflicts", []),
        "weather": weather_data,
        "local_news": local_news.get("articles", []),
        "local_channels": local_channels,
        "github": github_repos,
        "bittensor": {
            "price": bittensor_data.get("price", 0),
            "price_change_24h": bittensor_data.get("price_change_24h", 0),
            "active_subnets": bittensor_data.get("active_subnets", 0),
            "total_miners": bittensor_data.get("total_miners", 0),
            "top_subnets": bittensor_data.get("top_subnets", [])
        }
    }
    
    output_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data.json")
    with open(output_path, 'w') as f:
        json.dump(data, f, indent=2)
    
    print(f"\n[OK] Data written to {output_path}")
    print(f"     Reddit: {len(reddit_posts)} | LocalReddit: {len(local_reddit)} | Crypto: {len(crypto_data.get('news',[]))} | News: {len(news_data.get('all_news',[]))} | Stocks: {len(stocks_data.get('trending',[]))} | Defense: {len(defense_data.get('conflicts',[]))} | Weather: {city} {temp}F | GitHub: {len(github_repos)} | Subnets: {len(bittensor_data.get('top_subnets', []))}")
    print("=" * 50)
    
    return data

if __name__ == "__main__":
    build_dashboard_data()
