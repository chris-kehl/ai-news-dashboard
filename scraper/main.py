#!/usr/bin/env python3
"""Main orchestrator - runs market-focused scrapers and generates data.json."""
import json, sys, os
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from reddit_scraper import get_reddit_posts, get_world_reddit_posts
from x_scraper import get_world_x_posts
from business_scraper import get_business_data, get_tech_business_data
from crypto_scraper import get_crypto_data as get_crypto
from ap_news_scraper import get_ap_data
from stocks_scraper import get_stocks_data, generate_ticker_json, get_futures_data
from alpha_vantage_scraper import add_av_to_ticker
from defense_scraper import get_defense_data
from github_scraper import get_trending_repos
from summarizer import create_daily_summary
from nasdaq_scraper import get_nasdaq_data
from sticky_tab_scraper import get_sticky_tab_data

SCRAPER_DIR = os.path.dirname(os.path.abspath(__file__))


def build_dashboard_data():
    print("=" * 50)
    print(f"Market Dashboard - Update Started")
    print(f"Time: {datetime.now().isoformat()}")
    print("=" * 50)

    # 1. Aggregated content
    print("\n[1/11] AP News...")
    news_data = get_ap_data()
    print(f"       {len(news_data.get('all_news', []))} articles")

    print("\n[2/11] Defense...")
    defense_data = get_defense_data()
    print(f"       {len(defense_data.get('conflicts', []))} articles")

    print("\n[3/11] Stocks & ticker...")
    stocks_data = get_stocks_data()
    futures_data = get_futures_data()
    ticker_data = generate_ticker_json()

    # Inject AV sentiment into ticker items
    enriched_items = add_av_to_ticker(ticker_data.get("items", []))
    ticker_data["items"] = enriched_items

    print("\n[4/11] Business...")
    business_data = get_business_data()
    print(f"       {len(business_data)} items")

    print("\n[5/11] Tech Business...")
    tech_business_data = get_tech_business_data()
    print(f"       {len(tech_business_data)} items")

    print("\n[6/11] Crypto...")
    crypto_data = get_crypto()

    print("\n[7/11] Global Reddit...")
    reddit_posts = get_reddit_posts()

    print("\n[8/11] World News Reddit...")
    world_reddit_posts = get_world_reddit_posts()
    print(f"       {len(world_reddit_posts)} posts")

    print("\n[9/11] World X posts...")
    world_x_posts = get_world_x_posts()
    print(f"       {len(world_x_posts)} posts")

    print("\n[10/11] GitHub...")
    github_repos = get_trending_repos()

    print("\n[11/11] NASDAQ data...")
    nasdaq_data = get_nasdaq_data()
    print(f"       NASDAQ: ${nasdaq_data.get('price', 0):,.2f}  {nasdaq_data.get('signal', '?')}  ({nasdaq_data.get('changePercent', 0):+.2f}%)")

    print("\n[12/11] Sticky tab feeds...")
    sticky_data = get_sticky_tab_data()

    # Summary
    print("\n[13] Summary...")
    summary_data = create_daily_summary(reddit_posts, [], github_repos,
                                        crypto_data=crypto_data, stocks_data=stocks_data)

    data = {
        "timestamp": datetime.now().isoformat(),
        "summary": summary_data["summary"],
        "signals": summary_data["signals"],
        "reddit": reddit_posts,
        "world_reddit": world_reddit_posts,
        "world_x": world_x_posts,
        "crypto": crypto_data,
        "news": news_data.get("all_news", []),
        "stocks": stocks_data,
        "ticker": ticker_data,
        "business": business_data,
        "tech_business": tech_business_data,
        "defense": defense_data.get("conflicts", []),
        "github": github_repos,
        "nasdaq_data": nasdaq_data,
        "sticky": sticky_data,
        "futures": futures_data,
    }

    output_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data.json")
    with open(output_path, 'w') as f:
        json.dump(data, f, indent=2)
    print(f"\n[OK] Data written to {output_path}")
    print("=" * 50)
    return data


if __name__ == "__main__":
    build_dashboard_data()
