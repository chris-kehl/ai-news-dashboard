#!/usr/bin/env python3
"""Aggregate all city cache files into a single JSON for the frontend."""
import json, os, sys

SCRAPER_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(SCRAPER_DIR)
CACHE_DIR = os.path.join(ROOT_DIR, "cache")
OUT_PATH = os.path.join(ROOT_DIR, "city_cache.json")

try:
    sys.path.insert(0, SCRAPER_DIR)
    from batch_scraper import CITIES, _is_stale, _load_cache
except ImportError as e:
    print(f"[cache-export] Import error: {e}")
    CITIES = []

def export_all():
    aggregated = {"cities": {}, "meta": {"exported_at": "", "count": 0, "stale": 0}}
    exported = 0
    stale = 0
    for city, state in CITIES:
        slug = f"{city.lower().replace(' ', '_')}_{state.lower()}"
        if _is_stale(city, state):
            stale += 1
            continue
        data = _load_cache(city, state)
        if not data:
            stale += 1
            continue
        # Strip weather details to keep file small; keep essentials
        payload = {
            "city": city,
            "state": state,
            "zip": data.get("zip", ""),
            "weather_summary": _summarize_weather(data.get("weather", {})),
            "news": data.get("news", [])[:8],
            "reddit": data.get("reddit", [])[:8],
            "x_posts": data.get("x_posts", [])[:8],
            "channels": [],
            "cached_at": data.get("cached_at", "")
        }
        aggregated["cities"][slug] = payload
        exported += 1
    aggregated["meta"]["exported_at"] = __import__('datetime').datetime.now().isoformat()
    aggregated["meta"]["count"] = exported
    aggregated["meta"]["stale"] = stale
    os.makedirs(CACHE_DIR, exist_ok=True)
    with open(OUT_PATH, 'w') as f:
        json.dump(aggregated, f, indent=2)
    print(f"[cache-export] {exported} cities exported, {stale} stale. Written to {OUT_PATH} ({os.path.getsize(OUT_PATH)} bytes)")
    return aggregated

def _summarize_weather(weather):
    cur = weather.get("current", {})
    loc = weather.get("city", "") or weather.get("location", "")
    return {
        "city": loc,
        "temperature_f": cur.get("temperature", "N/A"),
        "condition": cur.get("condition", "N/A"),
        "humidity": cur.get("humidity", "N/A"),
        "wind": cur.get("wind", "N/A"),
    }

if __name__ == "__main__":
    export_all()
