#!/usr/bin/env python3
"""Main orchestrator - runs all scrapers and generates data.json.

Reads zip code from scraper/zip.txt (overrides env var).
"""
import json, sys, os
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from reddit_scraper import get_reddit_posts
from crypto_scraper import get_crypto_data as get_crypto
from ap_news_scraper import get_ap_data
from stocks_scraper import get_stocks_data, generate_ticker_json
from defense_scraper import get_defense_data
from weather_scraper import get_weather
from local_news_scraper import get_local_news
from reddit_local_scraper import get_local_reddit_from_weather
from local_channels_scraper import get_local_channel_news
from x_scraper import get_local_x_posts
from taostats import get_bittensor_data
from github_scraper import get_trending_repos
from summarizer import create_daily_summary

# Zip priority: 1) scraper/zip.txt, 2) WEATHER_ZIP env var, 3) 40272
SCRAPER_DIR = os.path.dirname(os.path.abspath(__file__))
ZIP_FILE = os.path.join(SCRAPER_DIR, "zip.txt")
WEATHER_ZIP = os.environ.get("WEATHER_ZIP", "40272")
if os.path.exists(ZIP_FILE):
    try:
        with open(ZIP_FILE) as f:
            WEATHER_ZIP = f.read().strip()
    except Exception:
        pass

NEWSAPI_KEY = os.environ.get("NEWSAPI_KEY", "")


def build_dashboard_data():
    print("=" * 50)
    print(f"AI News Dashboard - Update Started")
    print(f"Time: {datetime.now().isoformat()}")
    print(f"Zip: {WEATHER_ZIP}")
    print("=" * 50)

    # 1. Weather
    print(f"\n[1/11] Fetching weather for {WEATHER_ZIP}...")
    weather_data = get_weather(WEATHER_ZIP)
    city = weather_data.get('city', '')
    state = weather_data.get('state', '')
    temp = weather_data.get('current', {}).get('temperature', 'N/A')
    print(f"       {city}, {state}: {temp}F")

    # 2. Local news channels
    print(f"\n[2/11] Fetching local TV/paper news ({city})...")
    local_channels = get_local_channel_news(city, state)
    print(f"       Found {len(local_channels)} channel headlines")

    # 3. Local Reddit
    print(f"\n[3/11] Fetching local Reddit (r/{city.lower()}, r/{state.lower()})...")
    local_reddit = get_local_reddit_from_weather(weather_data, max_posts=6)
    print(f"       Found {len(local_reddit)} local reddit posts")

    # 4. Local X/Twitter
    print(f"\n[4/11] Fetching local X posts for {city}...")
    local_tweets = get_local_x_posts(city, state, max_results=8)
    print(f"       Found {len(local_tweets)} local X posts")

    # 5. World news
    print("\n[5/11] Fetching AP News...")
    news_data = get_ap_data()
    print(f"       Found {len(news_data.get('all_news', []))} world articles")

    # 6. Defense
    print("\n[6/11] Fetching defense/geopolitics...")
    defense_data = get_defense_data()
    print(f"       Found {len(defense_data.get('conflicts', []))} conflict articles")

    # 7. Ticker + stocks
    print("\n[7/11] Fetching stocks & ticker...")
    stocks_data = get_stocks_data()
    ticker_data = generate_ticker_json()
    print(f"       Stocks: {len(stocks_data.get('trending', []))} trending, {len(stocks_data.get('meme_momentum', []))} meme")
    print(f"       Ticker: {len(ticker_data.get('items', []))} items")

    # 8. Crypto
    print("\n[8/11] Fetching crypto...")
    crypto_data = get_crypto()
    print(f"       Found {len(crypto_data.get('prices', []))} coins")

    # 9. Reddit (global)
    print("\n[9/11] Fetching global Reddit posts...")
    reddit_posts = get_reddit_posts()
    print(f"       Found {len(reddit_posts)} posts")

    # 10. GitHub
    print("\n[10/11] Fetching GitHub trending...")
    github_repos = get_trending_repos()
    print(f"       Found {len(github_repos)} repos")

    # 11. Bittensor
    print("\n[11/11] Fetching Bittensor data...")
    bittensor_data = get_bittensor_data()
    print(f"       TAO: ${bittensor_data.get('price', 0):.2f}  |  Subnets: {bittensor_data.get('active_subnets', 0)}")

    # Summary
    print("\n[12] Generating summary...")
    summary_data = create_daily_summary(reddit_posts, [], github_repos, bittensor_data)

    # Assemble data.json
    data = {
        "timestamp": datetime.now().isoformat(),
        "zip": WEATHER_ZIP,
        "summary": summary_data["summary"],
        "signals": summary_data["signals"],
        "reddit": reddit_posts,
        "local_reddit": local_reddit,
        "local_tweets": local_tweets,
        "crypto": crypto_data,
        "news": news_data.get("all_news", []),
        "stocks": stocks_data,
        "ticker": ticker_data,
        "defense": defense_data.get("conflicts", []),
        "weather": weather_data,
        "local_news": get_local_news(city, state, NEWSAPI_KEY).get("articles", []),
        "local_channels": local_channels,
        "github": github_repos,
        "bittensor": {
            "price": bittensor_data.get("price", 0),
            "price_change_24h": bittensor_data.get("price_change_24h", 0),
            "active_subnets": bittensor_data.get("active_subnets", 0),
            "total_subnets": bittensor_data.get("total_subnets", 0),
            "top_subnets": bittensor_data.get("top_subnets", [])
        }
    }

    output_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data.json")
    with open(output_path, 'w') as f:
        json.dump(data, f, indent=2)

    print(f"\n[OK] Data written to {output_path}")
    print("=" * 50)
    return data


if __name__ == "__main__":
    build_dashboard_data()
