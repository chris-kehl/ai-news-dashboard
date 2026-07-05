#!/usr/bin/env python3
"""Main orchestrator - runs all scrapers and generates data.json.

Location is dynamic: scraper/config.json drives city/state for
weather, local news, X, Reddit.  location_scraper.py resolves
ZIP or free-text city names.
"""
import json, sys, os
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from location_scraper import resolve_location, load_config, save_config
from reddit_scraper import get_reddit_posts, get_world_reddit_posts
from x_scraper import get_world_x_posts
from business_scraper import get_business_data
from crypto_scraper import get_crypto_data as get_crypto
from ap_news_scraper import get_ap_data
from stocks_scraper import get_stocks_data, generate_ticker_json
from defense_scraper import get_defense_data
from weather_scraper import get_weather
from local_news_scraper import get_local_news
from local_channels_scraper import get_local_channel_news
from local_scraper import get_local_content
from taostats import get_bittensor_data
from github_scraper import get_trending_repos
from summarizer import create_daily_summary

SCRAPER_DIR = os.path.dirname(os.path.abspath(__file__))

# Load location from config.json
cfg = load_config(SCRAPER_DIR)
WEATHER_ZIP = cfg.get("zip", "40272")
CITY = cfg.get("city", "")
STATE = cfg.get("state", "")

NEWSAPI_KEY = os.environ.get("NEWSAPI_KEY", "")


def build_dashboard_data():
    print("=" * 50)
    print(f"AI News Dashboard - Update Started")
    print(f"Time: {datetime.now().isoformat()}")
    print(f"Location: {CITY}, {STATE} (zip: {WEATHER_ZIP})")
    print("=" * 50)

    # 1. Weather
    print(f"\n[1/13] Weather for {CITY} ({WEATHER_ZIP})...")
    weather_data = get_weather(WEATHER_ZIP)
    weather_data["city"] = CITY or weather_data.get("city", "")
    weather_data["state"] = STATE or weather_data.get("state", "")
    temp = weather_data.get("current", {}).get("temperature", "N/A")
    print(f"       {CITY}, {STATE}: {temp}F")

    # 2. Local channels
    print(f"\n[2/13] Local TV/paper ({CITY})...")
    local_channels = get_local_channel_news(CITY, STATE)
    print(f"       Found {len(local_channels)} headlines")

    # 3+4. Local X & Reddit
    print(f"\n[3/13] Local X & Reddit ({CITY}, {STATE})...")
    local_data = get_local_content(CITY, STATE, max_x=8, max_reddit=8)
    local_reddit = local_data.get("reddit_posts", [])
    local_tweets = local_data.get("x_posts", [])
    print(f"       Reddit: {len(local_reddit)} | X: {len(local_tweets)}")

    # 5-13. Aggregated content (global, location-agnostic)
    print("\n[5/13] AP News...")
    news_data = get_ap_data()
    print(f"       {len(news_data.get('all_news', []))} articles")

    print("\n[6/13] Defense...")
    defense_data = get_defense_data()
    print(f"       {len(defense_data.get('conflicts', []))} articles")

    print("\n[7/13] Stocks & ticker...")
    stocks_data = get_stocks_data()
    ticker_data = generate_ticker_json()

    print("\n[8/13] Business...")
    business_data = get_business_data()
    print(f"       {len(business_data)} items")

    print("\n[9/13] Crypto...")
    crypto_data = get_crypto()

    print("\n[9/13] Global Reddit...")
    reddit_posts = get_reddit_posts()

    print("\n[10/13] World News Reddit...")
    world_reddit_posts = get_world_reddit_posts()
    print(f"       {len(world_reddit_posts)} posts")

    print("\n[11/13] World X posts...")
    world_x_posts = get_world_x_posts()
    print(f"       {len(world_x_posts)} posts")

    print("\n[12/13] GitHub...")
    github_repos = get_trending_repos()

    print("\n[13/13] Bittensor...")
    bittensor_data = get_bittensor_data()
    print(f"       TAO: ${bittensor_data.get('price', 0):.2f}")

    # Summary
    print("\n[14] Summary...")
    summary_data = create_daily_summary(reddit_posts, [], github_repos, bittensor_data)

    data = {
        "timestamp": datetime.now().isoformat(),
        "location": {
            "zip": WEATHER_ZIP,
            "city": CITY,
            "state": STATE,
            "lat": cfg.get("lat", 0),
            "lon": cfg.get("lon", 0),
        },
        "summary": summary_data["summary"],
        "signals": summary_data["signals"],
        "reddit": reddit_posts,
        "world_reddit": world_reddit_posts,
        "world_x": world_x_posts,
        "local_reddit": local_reddit,
        "local_tweets": local_tweets,
        "crypto": crypto_data,
        "news": news_data.get("all_news", []),
        "stocks": stocks_data,
        "ticker": ticker_data,
        "business": business_data,
        "defense": defense_data.get("conflicts", []),
        "weather": weather_data,
        "local_news": get_local_news(CITY, STATE, NEWSAPI_KEY).get("articles", []),
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
