#!/bin/bash
# Setup SSH deploy key for passwordless GitHub pushes

set -e

KEY_NAME="github_ai_dashboard_deploy"
KEY_PATH="$HOME/.ssh/$KEY_NAME"
REPO="${1:-YOURUSERNAME/ai-news-dashboard}"

echo "=========================================="
echo "SSH Deploy Key Setup for GitHub Pages"
echo "=========================================="
echo ""
echo "This creates a dedicated SSH key so the MacBook can push"
echo "to GitHub without typing a password or using a token."
echo ""

# 1. Generate key if missing
if [ ! -f "$KEY_PATH" ]; then
    echo "[1] Generating SSH key: $KEY_PATH"
    ssh-keygen -t ed25519 -C "ai-dashboard@$(hostname)" -f "$KEY_PATH" -N ""
else
    echo "[1] SSH key already exists: $KEY_PATH"
fi

# 2. Start ssh-agent if not running
if ! pgrep -q ssh-agent; then
    eval "$(ssh-agent -s)" > /dev/null
fi

# 3. Add key to ssh-agent
ssh-add "$KEY_PATH" 2>/dev/null || true

# 4. Configure SSH for this repo
HOST_ALIAS="github-ai-dashboard"
SSH_CONFIG="$HOME/.ssh/config"

if ! grep -q "Host $HOST_ALIAS" "$SSH_CONFIG" 2>/dev/null; then
    echo "[2] Adding SSH config entry..."
    mkdir -p "$HOME/.ssh"
    cat >> "$SSH_CONFIG" <<EOF

Host $HOST_ALIAS
    HostName github.com
    User git
    IdentityFile $KEY_PATH
    IdentitiesOnly yes
EOF
else
    echo "[2] SSH config entry already exists"
fi

# 5. Show public key for GitHub
echo ""
echo "=========================================="
echo "[3] ADD THIS DEPLOY KEY TO GITHUB:"
echo "=========================================="
echo ""
cat "${KEY_PATH}.pub"
echo ""
echo "Steps:"
echo "  1. Go to: https://github.com/$REPO/settings/keys"
echo "  2. Click 'Add deploy key'"
echo "  3. Title: MacBook Scraper Server"
echo "  4. Paste the key above"
echo "  5. CHECK 'Allow write access'"
echo "  6. Click 'Add key'"
echo ""
echo "Then update your Git remote:"
echo "  cd ~/ai-news-dashboard"
echo "  git remote set-url origin git@$HOST_ALIAS:YOURUSERNAME/ai-news-dashboard.git"
echo ""
echo "Test with:"
echo "  ssh -T $HOST_ALIAS"
echo "=========================================="
