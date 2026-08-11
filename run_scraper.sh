#!/bin/bash
# AI News Dashboard scraper — runs data.json update + git push
set -e
cd "$(dirname "$0")"
venv/bin/python scripts/automated_nasdaq_analysis.py >> scripts/cron.log 2>&1
