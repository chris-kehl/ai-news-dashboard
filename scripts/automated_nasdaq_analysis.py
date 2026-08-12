#!/usr/bin/env python3
"""
Standalone daily update script — preserves weekly_pick via cache.
Run this every 15 minutes via cron:
  */15 * * * * cd ~/ai-news-dashboard && python3 scripts/automated_nasdaq_analysis.py >> scripts/cron.log 2>&1
"""
import json, os, sys, subprocess
from datetime import datetime
from pathlib import Path

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

ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = ROOT / ".cache"

def load_cached_pick():
    cache_path = CACHE_DIR / "weekly_pick_cache.json"
    try:
        with open(cache_path) as f:
            return json.load(f)
    except Exception:
        return None

def should_regenerate(now):
    return now.weekday() == 0 and 11 <= now.hour <= 17

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

    # Weekly Pick: prefer standalone weekly_pick.json (from pipeline_v2), else cache, else old
    now = datetime.now()
    weekly_pick_data = None

    # 1. Try standalone file (pipeline_v2 writes this)
    wp_file = ROOT / "weekly_pick.json"
    try:
        with open(wp_file) as f:
            wp_json = json.load(f)
        if wp_json.get('top_pick',{}).get('name'):
            weekly_pick_data = wp_json
            print(f"      [weekly_pick] Using weekly_pick.json: {wp_json['top_pick']['name']}")
    except Exception:
        pass

    # 2. Fallback to cache
    if not weekly_pick_data:
        cached_pick = load_cached_pick()
        if cached_pick:
            weekly_pick_data = cached_pick
            print(f"      [weekly_pick] Using cache: {cached_pick['week_label']}")

    # 3. Monday regen via old get_weekly_pick
    if not weekly_pick_data and should_regenerate(now):
        print("      [weekly_pick] Monday fallback to get_weekly_pick()")
        try:
            fresh = get_weekly_pick()
            if fresh and fresh.get('top_pick', {}).get('name'):
                weekly_pick_data = fresh
                with open(CACHE_DIR / "weekly_pick_cache.json", "w") as f:
                    json.dump(fresh, f, indent=2, default=str)
        except Exception as e:
            print(f"      [weekly_pick] Fallback failed: {e}")

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

    outfile = str(ROOT / "data.json")

    # Preserve weekly_pick from existing data if new pick is empty
    if not data.get('weekly_pick') or not data['weekly_pick'].get('top_pick', {}).get('name'):
        try:
            with open(outfile, 'r') as f:
                old_data = json.load(f)
            old_wp = old_data.get('weekly_pick')
            if old_wp and old_wp.get('top_pick', {}).get('name'):
                data['weekly_pick'] = old_wp
                print(f"      [weekly_pick] Preserved: {old_wp['top_pick']['name']}")
        except Exception:
            pass

    with open(outfile, 'w') as f:
        json.dump(data, f, indent=2)
    print(f"[OK] Written to {outfile}")

    try:
        subprocess.run(['git', 'add', 'data.json'], cwd=str(ROOT), check=False)
        subprocess.run(['git', 'commit', '-m', f'data: update {datetime.now().strftime("%Y-%m-%d %H:%M")}'], cwd=str(ROOT), check=True)
        subprocess.run(['git', 'push'], cwd=str(ROOT), check=True)
        print("[OK] Pushed to GitHub")
    except subprocess.CalledProcessError as e:
        print(f"[WARN] Git push failed: {e}")

if __name__ == '__main__':
    run_update()
