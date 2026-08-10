#!/usr/bin/env python3
"""
Weekly AI Pick Chart Generator

Generates a dark-themed technical chart for the current weekly pick.
Reads ticker from data.json['weekly_pick']['top_pick']['ticker'],
fetches 6mo OHLCV via yfinance (handles YF cookies/crumbs, avoids 429s),
and saves weekly_pick_chart.png in the repo root.

Called by weekly_pick_scraper.py after a new pick is selected.
"""
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import matplotlib.ticker as mticker
import numpy as np
import yfinance as yf

# ─── Paths ──────────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent
DATA_PATH = ROOT / "data.json"
OUT_PATH = ROOT / "weekly_pick_chart.png"

# ─── Theme (matches Geek-N-News dark mode) ──────────────────────────────────
BG_COLOR = "#0b0d10"
CARD_COLOR = "#111318"
LINE_COLOR = "#e8eaed"
MA20_COLOR = "#3b82f6"   # blue
MA50_COLOR = "#f7a51d"   # orange accent
BULLISH_COLOR = "#22c55e"
RESIST_COLOR = "#ef4444"
TEXT_COLOR = "#e8eaed"
MUTED_COLOR = "#9ca3af"
GRID_COLOR = "#22262e"


def fetch_hist(ticker: str, period: str = "6mo"):
    """Fetch price history via yfinance (handles cookies/crumbs)."""
    try:
        t = yf.Ticker(ticker)
        hist = t.history(period=period)
        if hist.empty or len(hist) < 30:
            return None
        hist.index = hist.index.tz_localize(None)
        return hist
    except Exception as e:
        print(f"[chart] yfinance error for {ticker}: {e}")
        return None


def generate_chart(ticker: str, name: str, week_label: str, price: float):
    # ── Fetch data ─────────────────────────────────────────────────────────
    hist = fetch_hist(ticker, period="6mo")
    if hist is None or len(hist) < 30:
        print(f"[chart] Insufficient data for {ticker}")
        return False

    dates = list(hist.index)
    closes = np.array(hist["Close"].values)
    current = round(closes[-1], 2)

    # Moving averages
    ma20 = hist["Close"].rolling(window=20).mean().values
    ma50 = hist["Close"].rolling(window=50).mean().values

    # 52-week high from 1y data
    hist_1y = fetch_hist(ticker, period="1y")
    w52_high = round(hist_1y["High"].max(), 2) if hist_1y is not None else round(max(closes), 2)

    # ── Figure ─────────────────────────────────────────────────────────────
    fig, ax = plt.subplots(figsize=(14, 7), facecolor=BG_COLOR)
    ax.set_facecolor(BG_COLOR)

    # Price line
    ax.plot(dates, closes, color=LINE_COLOR, linewidth=1.6, label=f"{ticker} Close")

    # MAs (pad NaNs for plotting alignment)
    ax.plot(dates, ma20, color=MA20_COLOR, linewidth=1.2, linestyle="--", label="20-Day MA")
    ax.plot(dates, ma50, color=MA50_COLOR, linewidth=1.2, linestyle="--", label="50-Day MA")

    # 52-week high horizontal
    ax.axhline(y=w52_high, color=RESIST_COLOR, linestyle=":", linewidth=1.0, alpha=0.8)
    ax.text(dates[-1] + timedelta(days=2), w52_high, f"52W HIGH  ${w52_high}",
            color=RESIST_COLOR, fontsize=9, va="bottom", ha="left", fontweight="bold")

    # Current price dashed
    ax.axhline(y=current, color=MUTED_COLOR, linestyle="-", linewidth=0.8, alpha=0.5)

    # ── Forecast / target zone ─────────────────────────────────────────────
    pct_to_high = (w52_high - current) / current * 100 if current else 0
    if abs(pct_to_high) < 3:
        forecast_target = round(current * 1.03, 2)
    elif pct_to_high > 10:
        forecast_target = round(current * 1.05, 2)
    else:
        forecast_target = round(current * 1.04, 2)

    support_zone = round(current * 0.97, 2)

    forecast_start = dates[-1]
    forecast_end = dates[-1] + timedelta(days=14)

    # Green forecast band
    ax.fill_between([forecast_start, forecast_end], current, forecast_target,
                    color=BULLISH_COLOR, alpha=0.08)

    # Target annotation
    target_pct = round((forecast_target - current) / current * 100, 1)
    ax.annotate(f"FORECAST TARGET\n${forecast_target}  (+{target_pct}%)",
                xy=(forecast_end, forecast_target),
                xytext=(forecast_end - timedelta(days=10), forecast_target + (current * 0.015)),
                arrowprops=dict(arrowstyle="->", color=BULLISH_COLOR, lw=1.5),
                color=BULLISH_COLOR, fontsize=10, fontweight="bold",
                ha="center", va="bottom")

    # Support annotation
    ax.annotate(f"KEY SUPPORT\n${support_zone} (50-D MA)",
                xy=(dates[-20], support_zone),
                xytext=(dates[-40], support_zone - (current * 0.03)),
                arrowprops=dict(arrowstyle="->", color=MA50_COLOR, lw=1.2),
                color=MA50_COLOR, fontsize=9, fontweight="bold",
                ha="center", va="top")

    # Breakout callout near 52w high
    if abs(pct_to_high) < 5:
        ax.annotate(f"BREAKOUT ZONE  ${w52_high}",
                    xy=(dates[-1], w52_high),
                    xytext=(dates[-15], w52_high + (current * 0.022)),
                    arrowprops=dict(arrowstyle="->", color=RESIST_COLOR, lw=1.2),
                    color=RESIST_COLOR, fontsize=9, fontweight="bold",
                    ha="center", va="bottom")

    # ── Formatting ─────────────────────────────────────────────────────────
    ax.set_title(f"{ticker} ({name})  —  {week_label}  —  6-Month Price Action & Forecast",
                 color=TEXT_COLOR, fontsize=14, fontweight="bold", pad=15)
    ax.set_ylabel("Price (USD)", color=MUTED_COLOR, fontsize=10)
    ax.set_xlabel("")

    ax.grid(True, linestyle="-", linewidth=0.4, color=GRID_COLOR, alpha=0.6)
    ax.set_axisbelow(True)

    ax.yaxis.set_major_formatter(mticker.FormatStrFormatter("$%.2f"))
    ax.tick_params(axis="y", colors=MUTED_COLOR, labelsize=9)

    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))
    ax.xaxis.set_major_locator(mdates.MonthLocator())
    ax.xaxis.set_minor_locator(mdates.WeekdayLocator())
    ax.tick_params(axis="x", colors=MUTED_COLOR, labelsize=9)
    plt.xticks(rotation=0)

    legend = ax.legend(loc="upper left", framealpha=0.15, facecolor=CARD_COLOR,
                       edgecolor=GRID_COLOR, labelcolor=TEXT_COLOR, fontsize=9)

    plt.tight_layout()
    plt.savefig(str(OUT_PATH), dpi=150, facecolor=BG_COLOR, edgecolor="none", bbox_inches="tight")
    plt.close()

    print(f"[chart] Saved: {OUT_PATH} ({os.path.getsize(OUT_PATH)} bytes)")
    return True


def main():
    try:
        with open(DATA_PATH) as f:
            data = json.load(f)
    except Exception as e:
        print(f"[chart] Cannot read {DATA_PATH}: {e}")
        return False

    wp = data.get("weekly_pick", {})
    top = wp.get("top_pick", {})
    ticker = top.get("ticker")
    name = top.get("name", ticker)
    week_label = wp.get("week_label", "This Week")
    price = top.get("price", 0)

    if not ticker:
        print("[chart] No weekly pick ticker found")
        return False

    print(f"[chart] Generating chart for {ticker} ({name})...")
    return generate_chart(ticker, name, week_label, price)


if __name__ == "__main__":
    ok = main()
    sys.exit(0 if ok else 1)
