#!/usr/bin/env python3
"""LLM summarizer for AI news. Uses OpenRouter free tier by default."""

import os
import json
import requests
from typing import List, Dict

OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"

def summarize_with_openrouter(content: str, api_key: str = None) -> str:
    """Summarize using OpenRouter (free tier available)."""
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
    """Fallback: extract key topics without LLM."""
    lines = content.split('\n')
    # Simple extraction - return first meaningful lines
    summary_parts = []
    for line in lines[:15]:
        line = line.strip()
        if len(line) > 20 and not line.startswith('http'):
            summary_parts.append(line[:200])
    
    if summary_parts:
        return "Key topics today:\n- " + "\n- ".join(summary_parts[:5])
    return "No summary available. Scraper needs configuration."

def generate_trading_signals(reddit_posts, x_posts, bittensor_data) -> List[Dict]:
    """Generate trading/investment signals from data."""
    signals = []
    
    # Bittensor signals
    if bittensor_data:
        price_change = bittensor_data.get("price_change_24h", 0)
        if price_change > 5:
            signals.append({"type": "buy", "text": f"TAO +{price_change:.1f}% breakout"})
        elif price_change < -5:
            signals.append({"type": "watch", "text": f"TAO dip {price_change:.1f}% - accumulation zone"})
        
        for sn in bittensor_data.get("top_subnets", [])[:3]:
            change_str = sn.get("change", "0%")
            try:
                change_val = float(change_str.replace('%', '').replace('+', ''))
                if change_val > 3:
                    signals.append({"type": "watch", "text": f"{sn['name']} growing +{change_val}%"})
                elif change_val < -5:
                    signals.append({"type": "sell", "text": f"{sn['name']} declining {change_val}%"})
            except:
                pass
    
    # Content-based signals
    all_text = " ".join([p.get("title", "") for p in reddit_posts[:10]] + 
                        [p.get("text", "") for p in x_posts[:5]]).lower()
    
    if any(k in all_text for k in ["openai", "gpt-5", "gpt5"]):
        signals.append({"type": "watch", "text": "OpenAI news - AI sector momentum"})
    if any(k in all_text for k in ["local llm", "local inference", "consumer gpu"]):
        signals.append({"type": "watch", "text": "Local AI trend - edge compute plays"})
    
    return signals[:6]

def create_daily_summary(reddit_posts, x_posts, github_repos, bittensor_data) -> Dict:
    """Create the complete daily summary."""
    # Build content for LLM
    content_parts = []
    
    content_parts.append("REDDIT TRENDS:")
    for p in reddit_posts[:8]:
        content_parts.append(f"- {p['title'][:120]} (r/{p['subreddit']}, {p['score']} pts)")
    
    content_parts.append("\nX/TWITTER:")
    for p in x_posts[:5]:
        content_parts.append(f"- {p['author']}: {p['text'][:150]}")
    
    content_parts.append("\nGITHUB:")
    for r in github_repos[:5]:
        content_parts.append(f"- {r['name']}: {r['description'][:100]} ({r['stars']} stars)")
    
    content_parts.append("\nBITTENSOR:")
    if bittensor_data:
        content_parts.append(f"- TAO: ${bittensor_data.get('price', 0):.2f} ({bittensor_data.get('price_change_24h', 0):+.1f}%)")
        for sn in bittensor_data.get("top_subnets", [])[:3]:
            content_parts.append(f"- {sn['name']}: {sn['miners']} miners, {sn['emission']} TAO/day ({sn['change']})")
    
    full_content = "\n".join(content_parts)
    
    # Generate summary
    summary = summarize_with_openrouter(full_content)
    
    # Generate signals
    signals = generate_trading_signals(reddit_posts, x_posts, bittensor_data)
    
    return {
        "summary": summary,
        "signals": signals
    }

if __name__ == "__main__":
    # Test with dummy data
    test_reddit = [{"title": "GPT-5 announced", "subreddit": "LocalLLaMA", "score": 1200}]
    test_x = [{"author": "@karpathy", "text": "LLMs are getting efficient", "likes": 5000}]
    test_gh = [{"name": "test/repo", "description": "AI tool", "stars": 1000}]
    
    result = create_daily_summary(test_reddit, test_x, test_gh, None)
    print("Summary:", result["summary"][:200])
    print("Signals:", result["signals"])
