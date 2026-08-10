# Geek-N-News Dashboard: Chart Maintenance

## Project paths
- Repo: `~/ai-news-dashboard`
- Venv Python: `~/ai-news-dashboard/venv/bin/python`
- Weekly pick chart script: `~/ai-news-dashboard/scripts/generate_weekly_pick_chart.py`
- Supporting (ACWX) chart script: `~/ai-news-dashboard/generate_acwx_chart.py`
- Fix script (runs both): `~/ai-news-dashboard/fix_weekly_chart.sh`
- Market analysis updater: `~/ai-news-dashboard/scripts/update_market_analysis.py`
- HTML: `~/ai-news-dashboard/index.html`
- Data: `~/ai-news-dashboard/data.json`

## Chart scripts

### Weekly Pick Chart (`generate_weekly_pick_chart.py`)
- Reads `data.json["weekly_pick"]["top_pick"]["ticker"]`
- Fetches 6mo OHLCV via yfinance
- Generates `weekly_pick_chart.png` with 20/50-day MA, 52w high, forecast band
- Uses venv Python (matplotlib + yfinance)

### ACWX Supporting Chart (`generate_acwx_chart.py`)
- Fetches ACWX 6mo + 1y via yfinance
- Generates `acwx_chart.png` with same dark theme
- **Dynamic annotations** (not hardcoded):
  - `support_zone` = actual 50-day MA from data
  - `forecast_target` computed from distance to 52-week high:
    - `< 3%` to 52w high → `current * 1.03`
    - `> 10%` to 52w high → `current * 1.05`
    - else → `current * 1.04`
  - Percentage and positions scale with current price

## One-off fixes

```bash
cd ~/ai-news-dashboard
venv/bin/python scripts/generate_weekly_pick_chart.py
venv/bin/python generate_acwx_chart.py
```

Or run the combined fix script:
```bash
cd ~/ai-news-dashboard && bash fix_weekly_chart.sh
```

## Weekly automatic tasks

### 1. Market Analysis HTML Updater
- Cron: `market-analysis-auto-update` — Mondays 12:00
- Script: `scripts/update_market_analysis.py`
- Fetches live prices, regenerates analysis text, patches `index.html`
- Updates timestamps, commits & pushes

### 2. Weekly Pick Chart Fix
- Cron: `weekly-pick-chart-fix` — Mondays 14:00
- Script: `fix_weekly_chart.sh`
- Regenerates weekly pick chart + ACWX chart
- Commits & pushes both PNGs to `origin/main`

### 3. ACWX Supporting Chart (standalone)
- Cron: `weekly-acwx-chart` — Mondays 14:30
- Script: `generate_acwx_chart.py` directly
- Standalone regeneration + git push
- Use when ACWX data needs a refresh independent of weekly pick

## Git deployment
All chart jobs commit and push automatically if run via cron.  
For manual runs:
```bash
cd ~/ai-news-dashboard
git add weekly_pick_chart.png acwx_chart.png index.html data.json
git commit -m "chart: update charts ($(date +%Y-%m-%d))"
git push origin main
```

## Dependencies (venv)
- `yfinance`
- `matplotlib`
- `numpy`

Install if missing:
```bash
cd ~/ai-news-dashboard
venv/bin/pip install yfinance matplotlib numpy
```

## Troubleshooting

### yfinance 429 errors
- Script already handles cookies/crumbs via yfinance internals
- If persistent, add a small delay between requests or use `requests_cache`

### Chart missing / blank
- Check `data.json` has valid `weekly_pick.top_pick.ticker`
- Verify venv Python exists at `venv/bin/python`
- Run script manually to see full traceback

### Git push fails
- Ensure SSH key or HTTPS token is configured
- Check `origin` remote points to the correct GitHub Pages repo
