import yfinance as yf
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import matplotlib.ticker as mticker
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import os

# ============================================================
# 1. Fetch data
# ============================================================
ticker = yf.Ticker("ACWX")
hist = ticker.history(period="6mo")

# Ensure index is DatetimeIndex without timezone for plotting
hist.index = hist.index.tz_localize(None)

# Current price
current = round(hist["Close"].iloc[-1], 2)

# Moving averages
hist["MA20"] = hist["Close"].rolling(window=20).mean()
hist["MA50"] = hist["Close"].rolling(window=50).mean()

# 52-week high from 1y data
hist_1y = ticker.history(period="1y")
hist_1y.index = hist_1y.index.tz_localize(None)
w52_high = round(hist_1y["High"].max(), 2)

# ============================================================
# 2. Figure setup — dark theme matching Geek-N-News
# ============================================================
bg_color      = "#0b0d10"
card_color    = "#111318"
line_color    = "#e8eaed"
ma20_color    = "#3b82f6"   # blue
ma50_color    = "#f7a51d"   # orange accent
bullish_color = "#22c55e"   # green
resist_color  = "#ef4444"   # red
text_color    = "#e8eaed"
muted_color   = "#9ca3af"
grid_color    = "#22262e"

fig, ax = plt.subplots(figsize=(14, 7), facecolor=bg_color)
ax.set_facecolor(bg_color)

# ============================================================
# 3. Plot price and MAs
# ============================================================
ax.plot(hist.index, hist["Close"], color=line_color, linewidth=1.6, label="ACWX Close")
ax.plot(hist.index, hist["MA20"], color=ma20_color, linewidth=1.2, linestyle="--", label="20-Day MA")
ax.plot(hist.index, hist["MA50"], color=ma50_color, linewidth=1.2, linestyle="--", label="50-Day MA")

# ============================================================
# 4. Horizontal levels
# ============================================================
# 52-week high resistance
ax.axhline(y=w52_high, color=resist_color, linestyle=":", linewidth=1.0, alpha=0.8)
ax.text(hist.index[-1] + timedelta(days=2), w52_high, f"52W HIGH  ${w52_high}",
        color=resist_color, fontsize=9, va="bottom", ha="left", fontweight="bold")

# Current price dashed line
ax.axhline(y=current, color=muted_color, linestyle="-", linewidth=0.8, alpha=0.5)

# ============================================================
# 5. Bullish forecast annotations
# ============================================================
# Dynamic support = actual 50-day MA; forecast based on distance to 52w high
support_zone = round(hist["MA50"].dropna().iloc[-1], 2)

pct_to_high = (w52_high - current) / current * 100 if current else 0
if abs(pct_to_high) < 3:
    forecast_target = round(current * 1.03, 2)
elif pct_to_high > 10:
    forecast_target = round(current * 1.05, 2)
else:
    forecast_target = round(current * 1.04, 2)

# Forecast arrow zone (right side of chart)
forecast_start = hist.index[-1]
forecast_end   = hist.index[-1] + timedelta(days=14)

# Green forecast zone band
ax.fill_between([forecast_start, forecast_end], current, forecast_target,
                color=bullish_color, alpha=0.08)

# Target annotation
target_pct = round((forecast_target - current) / current * 100, 1)
ax.annotate(f"FORECAST TARGET\n${forecast_target}  (+{target_pct}%)",
            xy=(forecast_end, forecast_target),
            xytext=(forecast_end - timedelta(days=10), forecast_target + (current * 0.015)),
            arrowprops=dict(arrowstyle="->", color=bullish_color, lw=1.5),
            color=bullish_color, fontsize=10, fontweight="bold",
            ha="center", va="bottom")

# Support annotation
ax.annotate(f"KEY SUPPORT\n${support_zone} (50-D MA)",
            xy=(hist.index[-20], support_zone),
            xytext=(hist.index[-40], support_zone - (current * 0.03)),
            arrowprops=dict(arrowstyle="->", color=ma50_color, lw=1.2),
            color=ma50_color, fontsize=9, fontweight="bold",
            ha="center", va="top")

# Breakout callout near current price
ax.annotate("BREAKOUT ZONE  $77.65",
            xy=(hist.index[-1], w52_high),
            xytext=(hist.index[-15], w52_high + 1.8),
            arrowprops=dict(arrowstyle="->", color=resist_color, lw=1.2),
            color=resist_color, fontsize=9, fontweight="bold",
            ha="center", va="bottom")

# ============================================================
# 6. Formatting
# ============================================================
ax.set_title("ACWX (MSCI ACWI ex-US)  —  6-Month Price Action & Bullish Forecast",
             color=text_color, fontsize=14, fontweight="bold", pad=15)
ax.set_ylabel("Price (USD)", color=muted_color, fontsize=10)
ax.set_xlabel("")

# Grid
ax.grid(True, linestyle="-", linewidth=0.4, color=grid_color, alpha=0.6)
ax.set_axisbelow(True)

# Y-axis formatting
ax.yaxis.set_major_formatter(mticker.FormatStrFormatter("$%.2f"))
ax.tick_params(axis="y", colors=muted_color, labelsize=9)

# X-axis dates
ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))
ax.xaxis.set_major_locator(mdates.MonthLocator())
ax.xaxis.set_minor_locator(mdates.WeekdayLocator())
ax.tick_params(axis="x", colors=muted_color, labelsize=9)
plt.xticks(rotation=0)

# Legend
legend = ax.legend(loc="upper left", framealpha=0.15, facecolor=card_color,
                   edgecolor=grid_color, labelcolor=text_color, fontsize=9)

# Tight layout and save
plt.tight_layout()
out_path = "/Users/chris/ai-news-dashboard/acwx_chart.png"
plt.savefig(out_path, dpi=150, facecolor=bg_color, edgecolor="none", bbox_inches="tight")
plt.close()

print(f"Chart saved to: {out_path}")
print(f"File size: {os.path.getsize(out_path)} bytes")
