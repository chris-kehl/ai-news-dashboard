# AI News Dashboard

Self-updating AI news dashboard hosted on **GitHub Pages**, powered by a **2016 Intel MacBook** running scrapers.

---

## What It Does

| Module | Data Source | Output |
|--------|------------|--------|
| Reddit Scraper | r/LocalLLaMA, r/MachineLearning, r/Bittensor | Top AI posts with scores |
| X/Twitter Scraper | Nitter instances (free, no API key) | AI thought leader tweets |
| GitHub Scraper | GitHub Trending + Search | Top AI repositories |
| Bittensor Scraper | RPC endpoints + CoinGecko | Subnet intel, TAO price, trading signals |
| Email Notifier | SMTP (Gmail/iCloud/Outlook) | HTML + plain text daily digest |
| Bot Notifier | Telegram API + Discord Webhooks | Compact mobile digests |
| Health Check | Uptime Kuma / Healthchecks.io | Alert if scraper goes down |

**Live dashboard:** `https://YOURUSERNAME.github.io/ai-news-dashboard`

---

## Notifications + Health Stack

| Feature | Method | Setup |
|---------|--------|-------|
| Email | SMTP | Add credentials to `.env` |
| Telegram | Bot API + Chat ID | Message @BotFather, @userinfobot |
| Discord | Webhook URL | Server Settings > Integrations > Webhooks |
| Health Ping | Push URL | Uptime Kuma push monitor or Healthchecks.io |

## New: Email Notifications + SSH Deploy Keys

Both features are now built in:

### Email Notifications
- Sends HTML email summary after each scrape
- Includes AI digest, trading signals, Reddit top 5, TAO price
- Works with Gmail, iCloud, Outlook (any SMTP)
- Configured via `.env` — no CLI tools needed

## Bot Notifications
- **Telegram**: Compact HTML digest to your DMs or a group chat
- **Discord**: Webhook messages to any channel
- Both fire automatically after every scrape, zero config beyond `.env`

## Health-Check Ping
- Pings a Uptime Kuma / Healthchecks.io / Cronitor URL on every successful scrape
- If the ping stops (scraper dies, MacBook offline), you get alerted
- Separate `healthcheck.py` runs every 30 min to double-check data freshness

## SSH Deploy Keys
- Passwordless GitHub pushes from the MacBook
- Dedicated `setup_ssh.sh` script generates the key
- Prints the public key to paste into GitHub deploy keys
- Auto-configures `~/.ssh/config` with a host alias

---

## Architecture

```
                          +------------------+     +----------------+
         email digest --> |    Your Email    |     | Telegram /     |
                          +------------------+     | Discord        |
                                    ^              +--------+-------+
                                    | SMTP                ^
                                    |                     | Bot API /
                                    |                     | Webhook
+------------------+     SSH / Git  |    +----------------+-----+
|  GitHub Pages    | <-------------+----|  2016 Intel MacBook    |
|  (Static Site)   |     push      |     \  (Scraper Server)    /
+------------------+    data.json  |      \                     /
        ^                          |       +-------------------+
        | auto-refresh             |       | Health Ping URL   | <- push every run
        | (5 min interval)         |       | (Uptime Kuma / HC)| <- alert if down
   [browser]                        +--------------+
```

---

## Setup Instructions

### Part 1: GitHub Repository (one-time)

1. Create a new repo on GitHub: `ai-news-dashboard`
2. Enable GitHub Pages:
   - Settings > Pages > Source: Deploy from a branch
   - Branch: `main` / `master`, folder: `/ (root)`
3. Clone locally and copy these files into it, or push this entire folder

### Part 2: MacBook Scraper Server

On your 2016 Intel MacBook (with internet access):

```bash
# 1. SSH into the MacBook (or work directly on it)
ssh user@macbook-ip

# 2. Clone the repo
git clone https://github.com/YOURUSERNAME/ai-news-dashboard.git
cd ai-news-dashboard

# 3. Run the setup script (installs deps, SSH key, launchd agent)
chmod +x setup_macbook.sh
./setup_macbook.sh https://github.com/YOURUSERNAME/ai-news-dashboard.git

# 4. Configure your secrets
nano .env
# Add: OPENROUTER_API_KEY=sk-or-v1-...  (free at openrouter.ai)
# Add: EMAIL_USERNAME=you@gmail.com
# Add: EMAIL_PASSWORD=your_app_password   (Gmail app password)
# Add: EMAIL_TO=you@gmail.com             (where to send digests)

# 5. Add the SSH deploy key to GitHub
# The setup script printed a key — copy it and paste at:
# https://github.com/YOURUSERNAME/ai-news-dashboard/settings/keys
# CHECK "Allow write access"

# 6. Switch remote from HTTPS to SSH
git remote set-url origin git@github-ai-dashboard:YOURUSERNAME/ai-news-dashboard.git

# 7. Test everything
python3 scraper/main.py
./deploy.sh
python3 scraper/email_notifier.py
```

The MacBook now auto-runs every 15 minutes via `launchd`, sends you email, and pushes to GitHub without passwords.

### Part 3: Remote Commands from Your M5 Mac

```bash
# Check recent scraper output
ssh user@macbook-ip "tail -30 /tmp/ai-news-scraper.log"

# Check for errors
ssh user@macbook-ip "tail -20 /tmp/ai-news-scraper.err"

# Force a manual scrape + email + deploy
ssh user@macbook-ip "cd ~/ai-news-dashboard && ./run_scraper.sh"

# Check if launch agent is loaded
ssh user@macbook-ip "launchctl list | grep ai-news"

# Restart the scheduler
ssh user@macbook-ip "launchctl unload ~/Library/LaunchAgents/com.ai-news.scraper.plist && launchctl load ~/Library/LaunchAgents/com.ai-news.scraper.plist"
```

---

## File Structure

```
ai-news-dashboard/
|__ index.html              # Dashboard served by GitHub Pages
|__ data.json               # Generated by scraper, auto-committed + pushed
|__ .env                    # API keys + email SMTP settings (gitignored)
|__ .env.example            # Template for .env
|__ .gitignore              # Excludes .env, __pycache__, logs
|__ deploy.sh               # Git commit + push script
|__ run_scraper.sh          # Full pipeline: scrape → bots → email → deploy → health ping
|__ setup_macbook.sh        # One-time MacBook setup (installs everything)
|__ setup_ssh.sh            # Generate SSH deploy key for passwordless push
|__ requirements.txt        # Python dependencies
|__ README.md               # This file
|
|__ scraper/
|   |__ main.py             # Orchestrator — runs all modules
|   |__ reddit_scraper.py   # Reddit (PRAW, no auth needed)
|   |__ x_scraper.py        # X/Twitter via Nitter (free scraping)
|   |__ bittensor_scraper.py # Bittensor RPC + CoinGecko + signals
|   |__ github_scraper.py   # GitHub trending/search AI repos
|   |__ summarizer.py       # OpenRouter LLM summaries (free tier)
|   |__ email_notifier.py   # SMTP email with HTML digest
|   |__ bot_notifier.py     # Telegram + Discord notifications
|   |__ healthcheck.py      # Push ping + stale data detector
|
|__ macos/
    |__ com.ai-news.scraper.plist    # launchd: runs scraper every 15 min
    |__ com.ai-news.healthcheck.plist # launchd: checks health every 30 min
```

---

## Scheduling Options

### Option A: MacBook stays awake (recommended if plugged in)
The `launchd` plist runs every 15 minutes automatically.

### Option B: MacBook sleeps when idle
Add a cron job that runs when the Mac wakes, or use `cron` + `anacron`:

```bash
# Edit crontab
crontab -e

# Add: run every hour
0 * * * * cd ~/ai-news-dashboard && ./run_scraper.sh >> /tmp/ai-news-cron.log 2>&1
```

---

## Customization

### Change subreddits
Edit `scraper/reddit_scraper.py`:
```python
subreddits = ["LocalLLaMA", "MachineLearning", "YourSubreddit"]
```

### Change X accounts
Edit `scraper/x_scraper.py`:
```python
AI_ACCOUNTS = ["karpathy", "swyx", "your_account"]
```

### Change update frequency
Edit `macos/com.ai-news.scraper.plist`:
```xml
<key>StartInterval</key>
<integer>1800</integer>  <!-- 30 minutes -->
```

### Add email notifications
Install the `himalaya` skill and add to `run_scraper.sh`:
```bash
himalaya send --to you@email.com --subject "AI News Update" --body "$(cat scraper/summary.txt)"
```

---

## Troubleshooting

| Issue | Fix |
|-------|-----|
| `data.json` not updating | Check `/tmp/ai-news-scraper.err` on MacBook |
| Git push fails | Set up SSH key or use `GITHUB_TOKEN` in `.env` |
| Nitter instances down | Update `NITTER_INSTANCES` in `x_scraper.py` |
| Reddit rate limited | Scraper uses read-only mode; should be fine |
| LLM summaries blank | Add `OPENROUTER_API_KEY` to `.env` for free tier |

---

## Dashboard Preview

The dashboard features:
- Dark theme optimized for reading
- Auto-refresh every 5 minutes
- Responsive grid layout (mobile-friendly)
- Trading signal badges
- Bittensor subnet intelligence
- Top Reddit / X / GitHub content
- LLM-generated daily summary

---

## Free API Tiers Used

| Service | Limit | Cost |
|---------|-------|------|
| Reddit (PRAW read-only) | 30 req/min | Free |
| Nitter instances | ~10 req/min | Free |
| GitHub API | 60 req/hr (unauth) | Free |
| CoinGecko | 10-30 calls/min | Free |
| OpenRouter | 200 req/day (free models) | Free |

---

## Next Steps

1. [ ] Create GitHub repo `ai-news-dashboard` and enable Pages
2. [ ] Copy this project and push to the repo
3. [ ] On the MacBook: `git clone` it and run `./setup_macbook.sh`
4. [ ] Add SSH deploy key to GitHub (printed by setup script)
5. [ ] Edit `.env` with OpenRouter key + email SMTP credentials
6. [ ] Switch git remote to SSH: `git remote set-url origin git@github-ai-dashboard:...`
7. [ ] Test: `python3 scraper/main.py && ./deploy.sh && python3 scraper/email_notifier.py`
8. [ ] Verify: `https://YOURUSERNAME.github.io/ai-news-dashboard`

## Quick Reference

| Command | Purpose |
|---------|---------|
| `python3 scraper/main.py` | Run scraper manually, creates `data.json` |
| `./deploy.sh` | Commit and push `data.json` to GitHub |
| `./run_scraper.sh` | Full pipeline: scrape → email → deploy |
| `python3 scraper/email_notifier.py` | Send test email digest |
| `./setup_ssh.sh` | Generate deploy key for passwordless push |
| `tail -f /tmp/ai-news-scraper.log` | Watch scraper live |

## SMTP Providers

| Provider | Server | Port |
|----------|--------|------|
| Gmail | `smtp.gmail.com` | 587 |
| iCloud | `smtp.mail.me.com` | 587 |
| Outlook/Hotmail | `smtp.office365.com` | 587 |
| Yahoo | `smtp.mail.yahoo.com` | 587 |

**Gmail users:** Use an [App Password](https://myaccount.google.com/apppasswords), not your login password.
**iCloud users:** Use an [App-Specific Password](https://appleid.apple.com).

