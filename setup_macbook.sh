#!/bin/bash
# Setup script for the 2016 Intel MacBook scraper server

set -e

REPO_URL="${1:-https://github.com/YOURUSERNAME/ai-news-dashboard.git}"
INSTALL_DIR="$HOME/ai-news-dashboard"

echo "=========================================="
echo "AI News Dashboard - MacBook Setup"
echo "=========================================="

# 1. Check prerequisites
echo "[1] Checking prerequisites..."
python3 --version || { echo "Python 3 required"; exit 1; }
git --version || { echo "Git required"; exit 1; }

# 2. Clone or update repo
if [ -d "$INSTALL_DIR/.git" ]; then
    echo "[2] Updating existing repo..."
    cd "$INSTALL_DIR"
    git pull origin $(git rev-parse --abbrev-ref HEAD) || true
else
    echo "[2] Cloning repository..."
    git clone "$REPO_URL" "$INSTALL_DIR"
    cd "$INSTALL_DIR"
fi

# 3. Install Python deps
echo "[3] Installing Python dependencies..."
python3 -m pip install --user -r requirements.txt

# 4. Create .env file if missing
if [ ! -f ".env" ]; then
    echo "[4] Creating .env file..."
    cp .env.example .env
    echo "      EDIT .env to add your OPENROUTER_API_KEY (free at openrouter.ai)"
    echo "      EDIT .env to add your EMAIL settings for notifications"
fi

# 5. Setup SSH key for passwordless GitHub pushes (optional but recommended)
echo "[5] Setting up SSH deploy key..."
./setup_ssh.sh || echo "      (SSH setup skipped or failed - you can do this manually)"

# 6. Install LaunchAgent for scheduled runs
echo "[6] Installing LaunchAgent (runs every 15 minutes)..."
PLIST_SOURCE="$INSTALL_DIR/macos/com.ai-news.scraper.plist"
PLIST_DEST="$HOME/Library/LaunchAgents/com.ai-news.scraper.plist"

mkdir -p "$HOME/Library/LaunchAgents"
cp "$PLIST_SOURCE" "$PLIST_DEST"

# Update paths in plist
sed -i '' "s|/Users/chris/ai-news-dashboard|$INSTALL_DIR|g" "$PLIST_DEST"

launchctl unload "$PLIST_DEST" 2>/dev/null || true
launchctl load "$PLIST_DEST"

# 7. Install health-check LaunchAgent
echo "[7] Installing health-check LaunchAgent (runs every 30 minutes)..."
HEALTH_PLIST_SOURCE="$INSTALL_DIR/macos/com.ai-news.healthcheck.plist"
HEALTH_PLIST_DEST="$HOME/Library/LaunchAgents/com.ai-news.healthcheck.plist"

cp "$HEALTH_PLIST_SOURCE" "$HEALTH_PLIST_DEST"
sed -i '' "s|/Users/chris/ai-news-dashboard|$INSTALL_DIR|g" "$HEALTH_PLIST_DEST"

launchctl unload "$HEALTH_PLIST_DEST" 2>/dev/null || true
launchctl load "$HEALTH_PLIST_DEST"

echo ""
echo "=========================================="
echo "[OK] Setup complete!"
echo ""
echo "Next steps:"
echo "  1. Edit $INSTALL_DIR/.env with your API keys + email + bots"
echo "  2. Add SSH deploy key to GitHub (see output above)"
echo "  3. Switch git remote to SSH:"
echo "       git remote set-url origin git@github-ai-dashboard:YOURUSER/ai-news-dashboard.git"
echo "  4. Test manually:"
echo "       python3 scraper/main.py"
echo "       ./deploy.sh"
echo "       python3 scraper/bot_notifier.py"
echo "       python3 scraper/email_notifier.py"
echo ""
echo "The scraper will run automatically every 15 minutes."
echo "Health checks run every 30 minutes."
echo "Logs: tail -f /tmp/ai-news-scraper.log"
echo "=========================================="
