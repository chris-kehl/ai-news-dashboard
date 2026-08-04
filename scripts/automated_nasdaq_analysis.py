#!/usr/bin/env python3
"""Daily automated NASDAQ analysis generator.

Runs at 0900 daily via cron. Reads NDX data from ticker.json,
generates a fresh technical analysis via OpenRouter, writes it to
the static NASDAQ paragraph in index.html, commits + pushes.
"""
import json
import os
import re
import subprocess
import sys

# ── CONFIG ──
INDEX_HTML = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "index.html")
TICKER_JSON = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scraper", "ticker.json")
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"


def load_ticker_data():
    """Read NDX data from ticker.json."""
    try:
        with open(TICKER_JSON, "r") as f:
            ticker = json.load(f)
        items = ticker.get("items", [])
        nitem = next(
            (i for i in items if i.get("symbol") in (".NDX", "NDX", "IXIC", ".IXIC")),
            None,
        )
        if not nitem:
            return None, None
        price = nitem.get("price")
        change_pct = nitem.get("change")
        return round(price, 2) if price else None, round(change_pct, 2) if change_pct else None
    except Exception as e:
        print(f"Error loading ticker: {e}")
        return None, None


def get_signal(change_pct):
    if change_pct is None:
        return "NEUTRAL"
    if change_pct > 0.5:
        return "BULLISH"
    if change_pct < -0.5:
        return "BEARISH"
    return "NEUTRAL"


def generate_analysis(price, change_pct, signal):
    """Call OpenRouter for a fresh daily NASDAQ analysis."""
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        # Fallback to local generation
        return generate_fallback_analysis(price, change_pct, signal)

    prompt = f"""You are a senior technical analyst writing a daily NASDAQ-100 (NDX) market outlook.
Current data: NDX at {price:,}, {change_pct:+.2f}% today, signal is {signal}.

Write 3-4 concise sentences covering:
- Key technical levels (support, resistance)
- Momentum indicators (RSI, MACD, moving averages — describe generally)
- What to watch for catalysts/reversal signals
- Price direction bias

Keep it under 120 words. No fluff. Write for active traders."""

    try:
        import requests
        response = requests.post(
            OPENROUTER_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://geek-n-news.com",
            },
            json={
                "model": "mistralai/mistral-7b-instruct:free",
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 250,
                "temperature": 0.6,
            },
            timeout=45,
        )
        data = response.json()
        analysis = data["choices"][0]["message"]["content"].strip()

        # Validate — must contain price or NDX
        if str(price) not in analysis and "NASDAQ" not in analysis:
            raise ValueError("Response missing price/reference")

        week_range = get_week_range()
        return f"NASDAQ-100 outlook for the week of {week_range}. {analysis}"

    except Exception as e:
        print(f"OpenRouter error: {e}")
        return generate_fallback_analysis(price, change_pct, signal)


def generate_fallback_analysis(price, change_pct, signal):
    """Local fallback when OpenRouter fails."""
    week_range = get_week_range()
    if signal == "BULLISH":
        return (
            f"NASDAQ-100 outlook for the week of {week_range}. NDX at {price:,}, up {change_pct:+.2f}% today — "
            f"momentum is positive. Near-term resistance sits at previous highs; expect a test into mid-week "
            f"if volume confirms. Support holds at the 20-day MA. Watch tech earnings, yields, and AI headlines for reversal triggers. "
            f"Bias BULLISH above {int(price * 0.995):,}."
        )
    elif signal == "BEARISH":
        return (
            f"NASDAQ-100 outlook for the week of {week_range}. NDX at {price:,}, down {change_pct:.2f}% today — "
            f"price action remains under pressure. Immediate support zone needs to hold or risk accelerates to the next down-leg. "
            f"RSI and MACD suggest continued weakness. Upside is capped near prior support-turned-resistance. "
            f"Reclaim {int(price * 1.015):,} on a close to flip bias. Watch macro events and large-cap tech for catalysts."
        )
    else:
        return (
            f"NASDAQ-100 outlook for the week of {week_range}. NDX at {price:,}, nearly flat ({change_pct:+.2f}%) — "
            f"consolidation continues. Price is coiling between support and resistance; a breakout or breakdown sets the next direction. "
            f"Momentum is neutral. Wait for volume confirmation. Levels to watch: resistance near {int(price * 1.012):,}, support near {int(price * 0.988):,}."
        )


def get_week_range():
    """Return week range like '3–7 August 2026'."""
    from datetime import datetime, timedelta
    today = datetime.now()
    # If today is weekend, jump to next Monday
    while today.weekday() >= 5:
        today += timedelta(days=1)
    monday = today - timedelta(days=today.weekday())
    friday = monday + timedelta(days=4)
    if monday.month == friday.month:
        return f"{monday.day}–{friday.day} {monday.strftime('%B')} {monday.year}"
    else:
        return f"{monday.day} {monday.strftime('%b')}–{friday.day} {friday.strftime('%b')} {monday.year}"


def write_analysis_to_html(analysis_text):
    """Replace the NASDAQ analysis paragraph in index.html."""
    with open(INDEX_HTML, "r") as f:
        html = f.read()

    # Match the specific div pattern
    pattern = r'(<div class="tv-desc" style="font-size:\.82rem;padding-top:10px" id="nasdaq-analysis">).*?(</div>)'

    if not re.search(pattern, html, re.DOTALL):
        print("ERROR: Could not find nasdaq-analysis div in index.html")
        return False

    new_html = re.sub(
        pattern,
        lambda m: m.group(1) + analysis_text + m.group(2),
        html,
        count=1,
        flags=re.DOTALL,
    )

    with open(INDEX_HTML, "w") as f:
        f.write(new_html)

    print("Updated index.html with new analysis")
    return True


def git_push():
    """Stage, commit, push index.html."""
    try:
        os.chdir(os.path.dirname(INDEX_HTML))
        subprocess.run(["git", "add", "index.html"], check=True, capture_output=True)
        result = subprocess.run(
            ["git", "commit", "-m", "auto: daily NASDAQ analysis update"],
            capture_output=True,
            text=True,
        )
        # Commit may be empty if nothing changed — that's OK
        push_result = subprocess.run(
            ["git", "push"],
            capture_output=True,
            text=True,
            check=True,
        )
        print("Pushed to GitHub Pages")
        return True
    except subprocess.CalledProcessError as e:
        print(f"Git push failed: {e.stderr if hasattr(e, 'stderr') else e}")
        return False


def main():
    print("=" * 50)
    print("Daily NASDAQ Analysis Generator")
    print("=" * 50)

    price, change_pct = load_ticker_data()
    if price is None:
        print("ERROR: Could not load NDX data from ticker.json")
        sys.exit(1)

    signal = get_signal(change_pct)
    print(f"NDX: {price:,} | {change_pct:+.2f}% | Signal: {signal}")

    analysis = generate_analysis(price, change_pct, signal)
    print(f"Analysis: {analysis[:80]}...")

    if not write_analysis_to_html(analysis):
        sys.exit(1)

    if not git_push():
        sys.exit(1)

    print("Done. Analysis live on site.")


if __name__ == "__main__":
    main()
