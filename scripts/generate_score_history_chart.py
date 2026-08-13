#!/usr/bin/env python3
"""
Score History Line Chart Generator
Renders a multi-ticker line graph of weekly scores out of 100.
Reads data/score_history.json and writes score_history_chart.png
"""

import json, sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path.home() / "ai-news-dashboard" / "venv" / "lib" / "python3.11" / "site-packages"))

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

BASE = Path.home() / "ai-news-dashboard"
HISTORY = BASE / "data" / "score_history.json"
OUT = BASE / "score_history_chart.png"


def generate_chart():
    if not HISTORY.exists():
        print("No history yet.")
        return

    with open(HISTORY) as f:
        history = json.load(f)

    if not history:
        print("Empty history.")
        return

    dates = sorted(history.keys())
    if len(dates) < 2:
        print(f"Only {len(dates)} week(s) of history — chart needs 2+ weeks.")
        return
    # Show last 12 weeks max
    dates = dates[-12:]
    x = [datetime.strptime(d, "%Y-%m-%d") for d in dates]

    # Collect all tickers that have data in this window
    ticker_scores = {}
    for d in dates:
        for ticker, score in history[d].items():
            ticker_scores.setdefault(ticker, []).append((d, score))

    # Only plot tickers with at least 3 data points in the window
    plot_tickers = {t: s for t, s in ticker_scores.items() if len(s) >= 3}
    # Top movers (highest latest score) or explicitly tracked
    latest_scores = {}
    for t, series in plot_tickers.items():
        latest_scores[t] = series[-1][1]

    # Pick top 20 by latest score for readability
    top_tickers = sorted(latest_scores.items(), key=lambda kv: kv[1], reverse=True)[:20]

    fig, ax = plt.subplots(figsize=(12, 7), facecolor='#0A0E17')
    ax.set_facecolor('#0A0E17')

    colors = [
        '#00E676', '#00B0FF', '#FF4081', '#FFD740', '#AA00FF',
        '#FF6E40', '#69F0AE', '#448AFF', '#E040FB', '#FFAB40',
        '#18FFFF', '#B2FF59', '#F50057', '#7C4DFF', '#FFC400',
        '#64FFDA', '#EEFF41', '#FF1744', '#C6FF00', '#2979FF',
    ]

    for i, (ticker, _) in enumerate(top_tickers):
        series = plot_tickers[ticker]
        series_dates = [datetime.strptime(d, "%Y-%m-%d") for d, _ in series]
        series_scores = [s for _, s in series]
        ax.plot(series_dates, series_scores, label=ticker, color=colors[i % len(colors)],
                marker='o', markersize=4, linewidth=1.5, alpha=0.85)

    ax.set_xlabel('Week', color='#A0AEC0', fontfamily='JetBrains Mono', fontsize=10)
    ax.set_ylabel('Score', color='#A0AEC0', fontfamily='JetBrains Mono', fontsize=10)
    ax.set_title('Weekly AI Pick Scores — 12-Week Trend', color='#E2E8F0',
                 fontfamily='JetBrains Mono', fontsize=14, fontweight='bold')

    ax.tick_params(colors='#A0AEC0', axis='both')
    ax.grid(True, color='#1E293B', linestyle='--', linewidth=0.5)
    ax.spines['bottom'].set_color('#1E293B')
    ax.spines['left'].set_color('#1E293B')
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)

    ax.xaxis.set_major_formatter(mdates.DateFormatter('%b %d'))
    ax.xaxis.set_major_locator(mdates.WeekdayLocator(interval=max(1, len(x)//6)))
    plt.xticks(rotation=25, ha='right')
    ax.set_ylim(0, 105)

    leg = ax.legend(loc='upper left', facecolor='#0F172A', edgecolor='#1E293B',
                    labelcolor='#A0AEC0', fontsize=8, ncol=2)
    plt.legend().set_draggable(False)
    plt.tight_layout()
    plt.savefig(OUT, dpi=150, facecolor='#0A0E17', bbox_inches='tight')
    plt.close()
    print(f"[score_history_chart] Saved: {OUT} ({OUT.stat().st_size:,} bytes)")


if __name__ == "__main__":
    generate_chart()
