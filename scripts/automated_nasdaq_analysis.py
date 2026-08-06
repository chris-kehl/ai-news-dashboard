#!/usr/bin/env python3
"""
Standalone daily update script — now includes Weekly Pick generation.
Run this on macbook1 every 15 minutes via cron:
  */15 * * * * cd ~/ai-news-dashboard && python3 scripts/automated_nasdaq_analysis.py >> scripts/cron.log 2>&1
"""
import json, os, sys, subprocess
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scraper'))

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
from weekly_pick_scraper import get_weekly_pick

def run_update():
    print(f"\n{'='*50}\nStandalone Update — {datetime.now().isoformat()}\n{'='*50}")

    news_data = get_ap_data()
    defense_data = get_defense_data()
    stocks_data = get_stocks_data()
    futures_data = get_futures_data()
    ticker_data = generate_ticker_json()
    ticker_data["items"] = add_av_to_ticker(ticker_data.get("items", []))

    business_data = get_business_data()
    tech_business_data = get_tech_business_data()
    crypto_data = get_crypto()
    reddit_posts = get_reddit_posts()
    world_reddit_posts = get_world_reddit_posts()
    world_x_posts = get_world_x_posts()
    github_repos = get_trending_repos()
    nasdaq_data = get_nasdaq_data()
    sticky_data = get_sticky_tab_data()
    weekly_pick_data = get_weekly_pick()

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
        "weekly_pick": weekly_pick_data,
    }

    outfile = os.path.join(os.path.dirname(__file__), '..', 'data.json')
    with open(outfile, 'w') as f:
        json.dump(data, f, indent=2)
    print(f"[OK] Written to {outfile}")

    # Git push
    try:
        repo_dir = os.path.join(os.path.dirname(__file__), '..')
        subprocess.run(['git', 'add', 'data.json'], cwd=repo_dir, check=True)
        subprocess.run(['git', 'commit', '-m', f'data: update {datetime.now().strftime("%Y-%m-%d %H:%M")}'], cwd=repo_dir, check=True)
        subprocess.run(['git', 'push'], cwd=repo_dir, check=True)
        print("[OK] Pushed to GitHub")
    except subprocess.CalledProcessError as e:
        print(f"[WARN] Git push failed: {e}")

if __name__ == '__main__':
    run_update()
