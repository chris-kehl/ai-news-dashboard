#!/usr/bin/env python3
"""Force a fresh weekly pick generation for testing sentiment integration."""
import asyncio
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from weekly_pick_scraper import main

if __name__ == "__main__":
    # Override the Monday gate by monkey-patching
    import weekly_pick_scraper
    # Skip cache check: set DATA_PATH to non-existent path
    weekly_pick_scraper.DATA_PATH = Path("/dev/null/nonexistent_cache")
    wp = asyncio.run(main())
    if wp and wp.get("top_pick"):
        tp = wp["top_pick"]
        print(f"\n{'='*60}")
        print(f"TOP PICK: {tp['name']} ({tp['ticker']})")
        print(f"SCORE: {tp['score']}")
        print(f"SENTIMENT: {tp.get('sentiment_score', 'N/A')}")
        print(f"SOURCES: {wp.get('sentiment_summary', {}).get('sources', [])}")
        print(f"{'='*60}")
