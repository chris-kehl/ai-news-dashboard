#!/usr/bin/env python3
"""Main orchestrator - runs all scrapers and generates data.json."""

import json
import sys
import os
from datetime import datetime

# Add scraper directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from reddit_scraper import get_reddit_posts
from x_scraper import get_x_posts
from bittensor_scraper import get_bittensor_intelligence
from github_scraper import get_trending_repos
from summarizer import create_daily_summary

def build_dashboard_data():
    """Run all scrapers and build the data.json payload."""
    print("=" * 50)
    print(f"AI News Dashboard - Update Started")
    print(f"Time: {datetime.now().isoformat()}")
    print("=" * 50)
    
    # Fetch data
    print("\n[1/5] Fetching Reddit posts...")
    reddit_posts = get_reddit_posts()
    print(f"      Found {len(reddit_posts)} posts")
    
    print("\n[2/5] Fetching X/Twitter posts...")
    x_posts = get_x_posts()
    print(f"      Found {len(x_posts)} posts")
    
    print("\n[3/5] Fetching GitHub trending repos...")
    github_repos = get_trending_repos()
    print(f"      Found {len(github_repos)} repos")
    
    print("\n[4/5] Fetching Bittensor intelligence...")
    bittensor_data = get_bittensor_intelligence()
    print(f"      TAO: ${bittensor_data.get('price', 0):.2f}")
    
    print("\n[5/5] Generating summary...")
    summary_data = create_daily_summary(reddit_posts, x_posts, github_repos, bittensor_data)
    print(f"      Summary length: {len(summary_data['summary'])} chars")
    
    # Build data.json
    data = {
        "timestamp": datetime.now().isoformat(),
        "summary": summary_data["summary"],
        "signals": summary_data["signals"],
        "reddit": reddit_posts,
        "x_posts": x_posts,
        "github": github_repos,
        "bittensor": {
            "price": bittensor_data.get("price", 0),
            "price_change_24h": bittensor_data.get("price_change_24h", 0),
            "active_subnets": bittensor_data.get("active_subnets", 0),
            "total_miners": bittensor_data.get("total_miners", 0),
            "top_subnets": bittensor_data.get("top_subnets", [])
        }
    }
    
    # Write data.json to parent directory (where index.html is)
    output_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data.json")
    with open(output_path, 'w') as f:
        json.dump(data, f, indent=2)
    
    print(f"\n[OK] Data written to {output_path}")
    print(f"     {len(reddit_posts)} Reddit, {len(x_posts)} X, {len(github_repos)} GitHub, {len(bittensor_data.get('top_subnets', []))} subnets")
    print("=" * 50)
    
    return data

if __name__ == "__main__":
    build_dashboard_data()
