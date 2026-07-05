#!/bin/bash
# Deploy script - commits updated data.json to GitHub Pages

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=== AI News Dashboard Deploy ==="
echo "Time: $(date)"

# Check if git repo
git rev-parse --git-dir > /dev/null 2>&1 || {
    echo "Error: Not a git repository. Please run:"
    echo "  git init"
    echo "  git remote add origin https://github.com/YOURUSER/ai-news-dashboard.git"
    exit 1
}

# Stage data.json and any other changes
git add data.json index.html scraper/
git diff --cached --quiet && {
    echo "No changes to commit."
    exit 0
}

# Commit with timestamp
git commit -m "Auto-update: $(date '+%Y-%m-%d %H:%M')"

# Push to GitHub (assumes branch is main or master)
CURRENT_BRANCH=$(git rev-parse --abbrev-ref HEAD)
echo "Pushing to origin/$CURRENT_BRANCH..."
git push origin "$CURRENT_BRANCH"

echo "[OK] Deployed successfully at $(date '+%H:%M:%S')"
