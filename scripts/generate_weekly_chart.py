#!/usr/bin/env python3
"""
Weekly AI Pick Chart Generator (Multi-panel)

Creates a dark-themed chart with:
  - Top panel: Price + SMA 10/20/50 with fill bands
  - Bottom panel: RSI(14) with overbought/oversold zones

Reads top pick from data/weekly_scores.json, saves weekly_pick_chart.png.
"""
import json
import os
import sys
from datetime import datetime
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import numpy as np
import yfinance as yf

ROOT = Path(__file__).resolve().parent.parent
SCORES_PATH = ROOT / "data" / "weekly_scores.json"
OUT_PATH = ROOT / "weekly_pick_chart.png"


def fetch_history(ticker: str, period="90d"):
    try:
        t = yf.Ticker(ticker)
        hist = t.history(period=period, interval="1d")
        return hist
    except Exception as e:
        print(f"Error fetching {ticker}: {e}", file=sys.stderr)
        return None


def rsi(series, window=14):
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)
    avg_gain = gain.rolling(window=window, min_periods=1).mean()
    avg_loss = loss.rolling(window=window, min_periods=1).mean()
    rs = avg_gain / np.maximum(avg_loss, 1e-10)
    return 100 - (100 / (1 + rs))


def generate(ticker, name, score):
    hist = fetch_history(ticker)
    if hist is None or len(hist) < 20:
        print(f"Insufficient data for {ticker}", file=sys.stderr)
        return False

    closes = hist["Close"]
    dates = hist.index
    sma10 = closes.rolling(10, min_periods=1).mean()
    sma20 = closes.rolling(20, min_periods=1).mean()
    sma50 = closes.rolling(50, min_periods=1).mean()
    rsi_val = rsi(closes)

    # Color aliases
    c_good = (34/255, 197/255, 94/255)
    c_danger = (239/255, 68/255, 68/255)
    c_price = (232/255, 234/255, 237/255)
    c_sma10 = (59/255, 130/255, 246/255)
    c_sma20 = (247/255, 165/255, 29/255)
    c_sma50 = (34/255, 197/255, 94/255)
    c_rsi = (139/255, 92/255, 246/255)
    c_bg = (11/255, 13/255, 16/255)
    c_panel = (17/255, 19/255, 24/255)
    c_grid = (34/255, 38/255, 46/255)
    c_text = (107/255, 114/255, 128/255)

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 8), dpi=150,
                                   gridspec_kw={"height_ratios": [3, 1]},
                                   facecolor=c_bg)

    # === Top: Price ===
    ax1.set_facecolor(c_panel)
    ax1.plot(dates, closes, color=c_price, linewidth=1.4, label="Close")
    ax1.plot(dates, sma10, color=c_sma10, linewidth=0.8, label="SMA 10")
    ax1.plot(dates, sma20, color=c_sma20, linewidth=0.8, label="SMA 20")
    ax1.plot(dates, sma50, color=c_sma50, linewidth=0.8, label="SMA 50")

    ax1.fill_between(dates, closes, sma50,
                     where=(closes >= sma50).values, color=(*c_good, 0.08),
                     interpolate=True)
    ax1.fill_between(dates, closes, sma50,
                     where=(closes < sma50).values, color=(*c_danger, 0.08),
                     interpolate=True)

    last_price = closes.iloc[-1]
    ax1.axhline(last_price, color=c_price, linestyle="--", alpha=0.2, linewidth=0.5)
    ax1.annotate(f"${last_price:,.2f}",
                 xy=(dates[-1], last_price),
                 xytext=(12, 4), textcoords="offset points",
                 color=c_price, fontsize=10, fontweight="bold",
                 bbox=dict(boxstyle="round,pad=0.2", facecolor=c_panel, edgecolor=c_grid, alpha=0.9))

    score_color = c_good if score >= 70 else (*c_sma20,) if score >= 50 else c_danger
    ax1.set_title(f"AI Weekly Pick — {name} ({ticker})    Score: {score}/100",
                  color=c_price, fontsize=14, fontweight="bold", pad=12)
    leg = ax1.legend(loc="upper left", facecolor=c_panel, edgecolor=c_grid,
                     labelcolor=c_price, fontsize=9, framealpha=0.95)
    for text in leg.get_texts():
        text.set_color(c_price)

    ax1.grid(True, alpha=0.12, color=c_price, linestyle="-")
    ax1.tick_params(colors=c_text, labelsize=9)
    for spine in ax1.spines.values():
        spine.set_color(c_grid)
    ax1.set_ylabel("Price ($)", color=c_text, fontsize=10)

    # === Bottom: RSI ===
    ax2.set_facecolor(c_panel)
    ax2.plot(dates, rsi_val, color=c_rsi, linewidth=1.2)
    ax2.axhline(70, color=c_danger, linestyle="--", alpha=0.5, linewidth=0.8)
    ax2.axhline(30, color=c_good, linestyle="--", alpha=0.5, linewidth=0.8)
    ax2.axhline(50, color=c_price, linestyle="--", alpha=0.12, linewidth=0.5)

    ax2.fill_between(dates, rsi_val, 70,
                     where=(rsi_val >= 70).values, color=(*c_danger, 0.2),
                     interpolate=True)
    ax2.fill_between(dates, rsi_val, 30,
                     where=(rsi_val <= 30).values, color=(*c_good, 0.2),
                     interpolate=True)

    last_rsi = rsi_val.iloc[-1]
    ax2.annotate(f"RSI {last_rsi:.1f}",
                 xy=(dates[-1], last_rsi),
                 xytext=(12, 4), textcoords="offset points",
                 color=c_rsi, fontsize=10, fontweight="bold",
                 bbox=dict(boxstyle="round,pad=0.2", facecolor=c_panel, edgecolor=c_grid, alpha=0.9))

    ax2.set_ylim(0, 100)
    ax2.set_ylabel("RSI(14)", color=c_text, fontsize=10)
    ax2.grid(True, alpha=0.12, color=c_price, linestyle="-")
    ax2.tick_params(colors=c_text, labelsize=9)
    for spine in ax2.spines.values():
        spine.set_color(c_grid)

    ax2.xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))
    ax2.xaxis.set_major_locator(mdates.WeekdayLocator(interval=2))
    plt.xticks(rotation=30, ha="right", color=c_text, fontsize=8)

    fig.text(0.5, 0.005,
             f"Generated {datetime.now().strftime('%Y-%m-%d %H:%M')}  |  90-day lookback  |  Auto-generated, not financial advice",
             ha="center", fontsize=7.5, color=c_text)

    plt.tight_layout(rect=[0, 0.02, 1, 1])
    plt.savefig(OUT_PATH, facecolor=fig.get_facecolor(), edgecolor="none",
                bbox_inches="tight", pad_inches=0.15)
    plt.close()
    print(f"[chart] Saved: {OUT_PATH} ({OUT_PATH.stat().st_size:,} bytes)")
    return True


def main():
    if not SCORES_PATH.exists():
        print(f"Missing {SCORES_PATH}", file=sys.stderr)
        sys.exit(1)

    with open(SCORES_PATH) as f:
        scores = json.load(f)

    picks = scores.get("top_picks", [])
    if not picks:
        print("[chart] No top picks available.", file=sys.stderr)
        sys.exit(1)

    # Check if we have qualifying picks (≥80)
    qualifying = [p for p in picks if p.get("score", 0) >= 80]
    if not qualifying:
        print(f"[chart] No qualifying pick (≥80). Best is {picks[0]['ticker']} at {picks[0]['score']}. Generating placeholder.", file=sys.stderr)
        # Generate chart for best available anyway, but highlight it's sub-threshold
        top = picks[0]
    else:
        top = qualifying[0]

    print(f"[chart] Generating chart for {top['ticker']} ({top['name']})...")
    ok = generate(top["ticker"], top["name"], top["score"])
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
