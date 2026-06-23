#!/usr/bin/env python3
"""LLM summarizer for AI news. Uses OpenRouter free tier by default."""
import os, json, requests
from typing import List, Dict

OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"
FREE_MODELS = [
    "meta-llama/llama-4-scout:free",
    "google/gemini-2.5-flash-preview:free",
    "moonshotai/kimi-k2:free",
]

def try_models(api_key, prompt):
    for model in FREE_MODELS:
        try:
            resp = requests.post(OPENROUTER_API_URL, headers={
                "Authorization": f"Bearer {api_key}", "Content-Type": "application/json",
                "HTTP-Referer": "https://chris-kehl.github.io/ai-news-dashboard", "X-Title": "AI News Dashboard"
            }, json={"model": model, "messages": [{"role": "user", "content": prompt}], "max_tokens": 400, "temperature": 0.4, "transforms": ["middle-out"]}, timeout=45)
            data = resp.json()
            if "error" in data:
                continue
            print(f"      Summarized with {model}")
            return data["choices"][0]["message"]["content"].strip()
        except:
            continue
    return None

def summarize_with_openrouter(content, api_key=None):
    if api_key is None:
        api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        return generate_basic_summary(content)
    prompt = f"""You are a sharp tech analyst writing for an AI/crypto dashboard. Summarize the following headlines into 3-4 crisp, actionable bullet points. Each bullet should be one sentence max. Focus on:
- Major AI product releases or model updates
- Developer/infrastructure trends affecting trading or investing
- Bittensor/crypto ecosystem moves
- Regulatory or competitive shifts
Headlines:
{content}
Summary:"""
    result = try_models(api_key, prompt)
    return result if result else generate_basic_summary(content)

def generate_basic_summary(content):
    lines = content.split("\n")
    parts = [l.strip()[:200] for l in lines[:15] if len(l.strip()) > 20 and not l.strip().startswith("http")]
    if parts:
        return "Key topics today:\n- " + "\n- ".join(parts[:5])
    return "No summary available."

def generate_trading_signals(reddit_posts, x_posts, bittensor_data):
    signals = []
    if bittensor_data:
        pc = bittensor_data.get("price_change_24h", 0)
        if pc > 8:
            signals.append({"type": "buy", "text": f"TAO +{pc:.1f}% breakout"})
        elif pc < -5:
            signals.append({"type": "watch", "text": f"TAO dip {pc:.1f}% - accumulation zone"})
        for sn in bittensor_data.get("top_subnets", [])[:3]:
            try:
                cv = float(sn.get("change", "0%").replace("%","").replace("+",""))
                if cv > 5:
                    signals.append({"type": "buy", "text": f"{sn['name']} growing +{cv}%"})
                elif cv < -5:
                    signals.append({"type": "sell", "text": f"{sn['name']} declining {cv}%"})
            except:
                pass
    all_text = " ".join([p.get("title","") for p in reddit_posts[:10]] + [p.get("text","") for p in x_posts[:5]]).lower()
    if any(k in all_text for k in ["openai", "gpt-5", "gpt5"]):
        signals.append({"type": "watch", "text": "OpenAI news - AI sector momentum"})
    if any(k in all_text for k in ["local llm", "local inference", "consumer gpu"]):
        signals.append({"type": "watch", "text": "Local AI trend - edge compute plays"})
    if any(k in all_text for k in ["bittensor", "tao ", "subnet"]):
        signals.append({"type": "watch", "text": "Bittensor mentions in feeds"})
    return signals[:6]

def create_daily_summary(reddit_posts, x_posts, github_repos, bittensor_data):
    parts = ["REDDIT TRENDS:"]
    for p in reddit_posts[:8]:
        parts.append(f"- {p['title'][:120]} (r/{p['subreddit']}, {p['score']} pts)")
    parts += ["\nX/TWITTER:"] + [f"- {p['author']}: {p['text'][:150]}" for p in x_posts[:5]]
    parts += ["\nGITHUB:"] + [f"- {r['name']}: {r['description'][:100]} ({r['stars']} stars)" for r in github_repos[:5]]
    parts += ["\nBITTENSOR:"]
    if bittensor_data:
        parts.append(f"- TAO: ${bittensor_data.get('price',0):.2f} ({bittensor_data.get('price_change_24h',0):+.1f}%)")
        for sn in bittensor_data.get("top_subnets",[])[:3]:
            parts.append(f"- {sn['name']}: {sn['miners']} miners, {sn['emission']} TAO/day ({sn['change']})")
    return {"summary": summarize_with_openrouter("\n".join(parts)), "signals": generate_trading_signals(reddit_posts, x_posts, bittensor_data)}

if __name__ == "__main__":
    test_reddit = [{"title": "GPT-5 announced", "subreddit": "LocalLLaMA", "score": 1200}]
    test_x = [{"author": "@karpathy", "text": "LLMs are getting efficient", "likes": 5000}]
    test_gh = [{"name": "test/repo", "description": "AI tool", "stars": 1000}]
    result = create_daily_summary(test_reddit, test_x, test_gh, None)
    print("Summary:", result["summary"][:200])
    print("Signals:", result["signals"])
