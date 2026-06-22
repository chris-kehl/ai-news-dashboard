#!/bin/bash
# Wrapper: run scraper + bots + email + deploy + health ping

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Use Anaconda Python if available, fallback to system python3
if [ -x "/opt/anaconda3/bin/python3" ]; then
    PYTHON="/opt/anaconda3/bin/python3"
else
    PYTHON="python3"
fi

# Load env vars
export $(grep -v '^#' .env | xargs) 2>/dev/null || true

# Run scraper
echo "[$(date)] Running scraper with $PYTHON..."
cd scraper
$PYTHON main.py
cd ..

# Send bot notifications (Telegram + Discord)
echo "[$(date)] Sending bot notifications..."
$PYTHON scraper/bot_notifier.py data.json || true

# Send email notification
echo "[$(date)] Sending email notification..."
$PYTHON scraper/email_notifier.py data.json || true

# Deploy
echo "[$(date)] Deploying..."
./deploy.sh

# Ping healthcheck service on success
if [ -n "$HEALTHCHECK_URL" ]; then
    echo "[$(date)] Pinging healthcheck..."
    curl -fsS -m 15 --retry 3 "$HEALTHCHECK_URL" > /dev/null || true
fi

echo "[$(date)] Done."
