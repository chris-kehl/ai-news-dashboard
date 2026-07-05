#!/usr/bin/env python3
"""Main orchestrator - runs all scrapers and generates data.json.

Location config read from scraper/config.json (zip, city, state).
Falls back to scraper/zip.txt if config.json missing.
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
from local_channels_scraper import get_local_channel_news
from local_scraper import get_local_content
from taostats import get_bittensor_data
from github_scraper import get_trending_repos
from summarizer import create_daily_summary

SCRAPER_DIR = os.path.dirname(os.path.abspath(__file__))

# Load config.json or fall back to zip.txt
CONFIG_PATH = os.path.join(SCRAPER_DIR, "config.json")
ZIP_FILE = os.path.join(SCRAPER_DIR, "zip.txt")

config = {"location": {"zip": "40272", "city": "", "state": ""}}
if os.path.exists(CONFIG_PATH):
    try:
        with open(CONFIG_PATH) as f:
            loaded = json.load(f)
            if "location" in loaded:
                config = loaded
    except Exception as e:
        print(f"[WARN] Failed to load config.json: {e}")

WEATHER_ZIP = config.get("location", {}).get("zip", "")
if not WEATHER_ZIP and os.path.exists(ZIP_FILE):
    try:
        with open(ZIP_FILE) as f:
            WEATHER_ZIP = f.read().strip()
    except Exception:
        pass
if not WEATHER_ZIP:
    WEATHER_ZIP = os.environ.get("WEATHER_ZIP", "40272")

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
    # Override with config if explicitly set
    city = config.get("location", {}).get("city") or city
    state = config.get("location", {}).get("state") or state
    temp = weather_data.get('current', {}).get('temperature', 'N/A')
    print(f"       {city}, {state}: {temp}F")

    # 2. Local news channels
    print(f"\n[2/11] Fetching local TV/paper news ({city})...")
    local_channels = get_local_channel_news(city, state)
    print(f"       Found {len(local_channels)} channel headlines")

    # 3+4. Local X + Reddit via unified scraper (data-universe patterns)
    print(f"\n[3/11] Fetching local X & Reddit ({city}, {state})...")
    local_data = get_local_content(city, state, max_x=8, max_reddit=8)
    local_reddit = local_data["reddit_posts"]
    local_tweets = local_data["x_posts"]
    print(f"       Found {len(local_reddit)} local reddit posts, {len(local_tweets)} local X posts")

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
