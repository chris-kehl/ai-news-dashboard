#!/bin/bash
# Batch scraper wrapper — runs every 30s via launchd

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [ -x "/opt/anaconda3/bin/python3" ]; then
    PYTHON="/opt/anaconda3/bin/python3"
else
    PYTHON="python3"
fi

echo "[$(date)] Starting batch scraper..."
cd scraper
$PYTHON batch_scraper.py
cd ..

echo "[$(date)] Batch scraper done."
