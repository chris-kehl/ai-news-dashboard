#!/bin/bash
cd /Users/chris/ai-news-dashboard
python3 scripts/automated_nasdaq_analysis.py >> scripts/cron.log 2>&1
