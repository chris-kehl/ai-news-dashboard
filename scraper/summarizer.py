#!/usr/bin/env python3
"""LLM summarizer for AI news."""

import os, json, requests

OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"


def summarize_with_openrouter(content: str, api_key: str = None) -> str:
    if api_key is None:
        api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        return generate_basic_summary(content)

    prompt = f"""You are an AI news analyst. Summarize the following AI-related content into 3-4 clear, actionable bullet points. Focus on:
- Major announcements/releases
- Technical breakthroughs
- Market/trading implications
- Trends worth watching

Content:
{content}

Summary:"""

    try:
        response = requests.post(
            OPENROUTER_API_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://ai-news-dashboard.github.io"
            },
            json={
                "model": "mistralai/mistral-7b-instruct:free",
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 300,
                "temperature": 0.5
            },
            timeout=30
        )
        data = response.json()
        return data["choices"][0]["message"]["content"].strip()
    except Exception as e:
        print(f"OpenRouter error: {e}")
        return generate_basic_summary(content)


def generate_basic_summary(content: str) -> str:
    lines = content.split('\n')
    summary_parts = []
    for line in lines[:15]:
        line = line.strip()
        if len(line) > 20 and not line.startswith('http'):
            summary_parts.append(line[:200])
    if summary_parts:
        return "Key topics today:\n- " + "\n- ".join(summary_parts[:5])
    return "No summary available. Scraper needs configuration."


def generate_trading_signals(reddit_posts, x_posts, bittensor_data, crypto_data=None, stocks_data=None):
    signals = []

    # ── CRYPTO LEADERS / LAGGARDS ──
    if crypto_data:
        prices = crypto_data.get("prices", [])
        # Sort by absolute move, pick top movers
        movers = sorted(prices, key=lambda c: abs(c.get("change_24h", 0)), reverse=True)
        for coin in movers[:3]:
            ch = coin.get("change_24h", 0)
            sym = coin.get("symbol", "")
            pr = coin.get("price", 0)
            if ch > 5:
                signals.append({
                    "type": "buy",
                    "asset": sym,
                    "price": pr,
                    "change": ch,
                    "category": "crypto",
                    "text": f"{sym} +{ch:.1f}% breakout @ ${pr:,.2f}"
                })
            elif ch < -5:
                signals.append({
                    "type": "sell",
                    "asset": sym,
                    "price": pr,
                    "change": ch,
                    "category": "crypto",
                    "text": f"{sym} {ch:.1f}% dump @ ${pr:,.2f} — watch support"
                })
            elif abs(ch) >= 2:
                signals.append({
                    "type": "watch",
                    "asset": sym,
                    "price": pr,
                    "change": ch,
                    "category": "crypto",
                    "text": f"{sym} {ch:+.1f}% @ ${pr:,.2f}"
                })

    # ── TAO / BITTENSOR ──
    if bittensor_data:
        price_change = bittensor_data.get("price_change_24h", 0)
        tao_price = bittensor_data.get("price", 0)
        if price_change > 5:
            signals.append({
                "type": "buy", "asset": "TAO", "price": tao_price,
                "change": price_change, "category": "bittensor",
                "text": f"TAO +{price_change:.1f}% breakout @ ${tao_price:.2f}"
            })
        elif price_change < -5:
            signals.append({
                "type": "watch", "asset": "TAO", "price": tao_price,
                "change": price_change, "category": "bittensor",
                "text": f"TAO dip {price_change:.1f}% @ ${tao_price:.2f} — accumulation zone"
            })
        else:
            signals.append({
                "type": "watch", "asset": "TAO", "price": tao_price,
                "change": price_change, "category": "bittensor",
                "text": f"TAO {price_change:+.1f}% @ ${tao_price:.2f} — hold"
            })

        for sn in bittensor_data.get("top_subnets", [])[:4]:
            ch = sn.get("price_change_24h", 0)
            name = sn.get("name", "")
            price = sn.get("price", 0)
            if ch > 5:
                signals.append({
                    "type": "buy", "asset": name, "price": price,
                    "change": ch, "category": "subnet",
                    "text": f"{name} +{ch:.1f}% — strong subnet momentum"
                })
            elif ch < -10:
                signals.append({
                    "type": "sell", "asset": name, "price": price,
                    "change": ch, "category": "subnet",
                    "text": f"{name} {ch:.1f}% — deep subnet drawdown"
                })
            elif abs(ch) >= 3:
                signals.append({
                    "type": "watch", "asset": name, "price": price,
                    "change": ch, "category": "subnet",
                    "text": f"{name} {ch:+.1f}% subnet moving"
                })

    # ── STOCK MOMENTUM ──
    if stocks_data:
        all_stocks = (stocks_data.get("trending", []) +
                      stocks_data.get("meme_momentum", []))
        movers = sorted(all_stocks, key=lambda s: abs(s.get("change_percent", 0)), reverse=True)
        for s in movers[:3]:
            ch = s.get("change_percent", 0)
            sym = s.get("symbol", "")
            pr = s.get("price", 0)
            if ch > 5:
                signals.append({
                    "type": "buy", "asset": sym, "price": pr,
                    "change": ch, "category": "stock",
                    "text": f"{sym} +{ch:.1f}% momentum @ ${pr:.2f}"
                })
            elif ch < -5:
                signals.append({
                    "type": "sell", "asset": sym, "price": pr,
                    "change": ch, "category": "stock",
                    "text": f"{sym} {ch:.1f}% drop @ ${pr:.2f}"
                })
            elif abs(ch) >= 2:
                signals.append({
                    "type": "watch", "asset": sym, "price": pr,
                    "change": ch, "category": "stock",
                    "text": f"{sym} {ch:+.1f}% @ ${pr:.2f}"
                })

    # ── SENTIMENT SIGNALS ──
    all_text = " ".join([p.get("title", "") for p in reddit_posts[:10]] +
                        [p.get("text", "") for p in x_posts[:5]]).lower()
    if any(k in all_text for k in ["openai", "gpt-5", "gpt5", "anthropic", "claude"]):
        signals.append({
            "type": "watch", "asset": "AI SECTOR", "price": None,
            "change": None, "category": "sentiment",
            "text": "AI sector chatter up — watch NVDA, MSFT, TAO"
        })
    if any(k in all_text for k in ["local llm", "local inference", "consumer gpu", "ollama"]):
        signals.append({
            "type": "watch", "asset": "EDGE AI", "price": None,
            "change": None, "category": "sentiment",
            "text": "Edge AI trend — local inference plays"
        })
    if any(k in all_text for k in ["bitcoin", "btc", "crypto rally", "bull run", "altcoin"]):
        signals.append({
            "type": "watch", "asset": "CRYPTO", "price": None,
            "change": None, "category": "sentiment",
            "text": "Crypto chatter heating up — risk-on bias"
        })
    if any(k in all_text for k in ["recession", "fed rate", "interest rate", "inflation"]):
        signals.append({
            "type": "watch", "asset": "MACRO", "price": None,
            "change": None, "category": "sentiment",
            "text": "Macro news flow — watch volatility"
        })

    return signals[:10]


def create_daily_summary(reddit_posts, x_posts, github_repos, bittensor_data,
                         crypto_data=None, stocks_data=None):
    content_parts = []

    content_parts.append("REDDIT TRENDS:")
    for p in reddit_posts[:8]:
        content_parts.append(f"- {p['title'][:120]} (r/{p['subreddit']}, {p['score']} pts)")

    content_parts.append("\nX/TWITTER:")
    for p in x_posts[:5]:
        content_parts.append(f"- {p['author']}: {p['text'][:150]}")

    content_parts.append("\nGITHUB:")
    for r in github_repos[:5]:
        content_parts.append(f"- {r['name']}: {r.get('description','')[:100]} ({r['stars']} stars)")

    content_parts.append("\nBITTENSOR:")
    if bittensor_data:
        content_parts.append(f"- TAO: ${bittensor_data.get('price', 0):.2f} ({bittensor_data.get('price_change_24h', 0):+.1f}%)")
        for sn in bittensor_data.get("top_subnets", [])[:3]:
            content_parts.append(
                f"- {sn['name']}: price ${sn.get('price',0)} ({sn.get('price_change_24h',0):+.1f}%), "
                f"rank #{sn.get('rank','?')}, mcap {sn.get('market_cap',0):.0f}TAO"
            )

    full_content = "\n".join(content_parts)
    summary = summarize_with_openrouter(full_content)
    signals = generate_trading_signals(reddit_posts, x_posts, bittensor_data,
                                       crypto_data=crypto_data, stocks_data=stocks_data)

    return {"summary": summary, "signals": signals}


def create_daily_summary_legacy(reddit_posts, x_posts, github_repos, bittensor_data):
    """Legacy compatibility: delegates to new signature."""
    return create_daily_summary(reddit_posts, x_posts, github_repos, bittensor_data)


if __name__ == "__main__":
    test_reddit = [{"title": "GPT-5 announced", "subreddit": "LocalLLaMA", "score": 1200}]
    test_x = [{"author": "@karpathy", "text": "LLMs are getting efficient", "likes": 5000}]
    test_gh = [{"name": "test/repo", "description": "AI tool", "stars": 1000}]
    result = create_daily_summary(test_reddit, test_x, test_gh, None)
    print("Summary:", result["summary"][:200])
    print("Signals:", result["signals"])
