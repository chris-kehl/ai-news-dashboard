#!/usr/bin/env python3
"""Generate weekly pick chart image (dark theme)."""
import json, sys, os
from datetime import datetime
from pathlib import Path

os.environ['MPLBACKEND'] = 'Agg'
import matplotlib
matplotlib.rcParams['xtick.color'] = '#9ca3af'
matplotlib.rcParams['ytick.color'] = '#9ca3af'
matplotlib.rcParams['axes.labelcolor'] = '#9ca3af'
matplotlib.rcParams['axes.edgecolor'] = '#22262e'
matplotlib.rcParams['figure.facecolor'] = '#111318'
matplotlib.rcParams['axes.facecolor'] = '#111318'
matplotlib.rcParams['axes.titlecolor'] = '#e8eaed'

import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import yfinance as yf
import pandas as pd


def generate_chart(ticker, name, output_path='/Users/chris/ai-news-dashboard/weekly_pick_chart.png'):
    ticker = ticker.replace('$','').strip()
    try:
        h = yf.Ticker(ticker).history(period='90d', interval='1d')
        if len(h) < 20:
            print(f'{ticker}: insufficient data ({len(h)} rows)')
            return False

        fig, ax = plt.subplots(figsize=(8, 4), dpi=120)

        # Price line
        ax.plot(h.index, h['Close'], color='#f7a51d', linewidth=2, zorder=3)

        # Volume bars (bottom)
        ax2 = ax.twinx()
        ax2.bar(h.index, h['Volume'], color='#3b2a0a', alpha=0.4, width=0.8, zorder=1)
        ax2.set_ylim(0, h['Volume'].max() * 3)
        ax2.axis('off')

        # 20d SMA
        sma20 = h['Close'].rolling(20).mean()
        ax.plot(h.index, sma20, color='#3b82f6', linewidth=1, alpha=0.7, zorder=2)

        last = h['Close'].iloc[-1]
        high = h['High'].max()
        low = h['Low'].min()

        # Annotations
        ax.annotate(f'${last:.2f}', xy=(h.index[-1], last),
                    fontsize=11, fontweight='bold', color='#f7a51d',
                    xytext=(h.index[-1] + pd.Timedelta(days=2), last),
                    arrowprops=dict(arrowstyle='->', color='#f7a51d', lw=1.5))

        ax.set_title(f'{name} ({ticker}) — 90-Day Chart', fontsize=13, fontweight='bold', color='#e8eaed')
        ax.set_xlabel('')
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%b %d'))
        for label in ax.get_xticklabels():
            label.set_color('#9ca3af')
        ax.tick_params(colors='#9ca3af')
        ax.grid(True, linestyle='--', alpha=0.15, color='#6b7280')

        # Stats box
        stats = f'High: ${high:.2f}  |  Low: ${low:.2f}  |  Avg Vol: {h["Volume"].mean()/1e6:.1f}M'
        ax.text(0.5, 0.02, stats, transform=ax.transAxes, ha='center',
                fontsize=8.5, color='#6b7280', fontfamily='JetBrains Mono')

        fig.tight_layout()
        fig.savefig(output_path, dpi=120, bbox_inches='tight', facecolor='#111318')
        plt.close(fig)
        print(f'Chart saved: {output_path} ({os.path.getsize(output_path)} bytes)')
        return True
    except Exception as e:
        print(f'Chart error: {e}')
        return False


if __name__ == '__main__':
    ticker = sys.argv[1] if len(sys.argv) > 1 else 'AMGN'
    name = sys.argv[2] if len(sys.argv) > 2 else 'Amgen'
    generate_chart(ticker, name)
