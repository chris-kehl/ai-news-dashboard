#!/usr/bin/env python3
"""Quick test of tech_analysis_scraper.py"""
import json, os, sys

# Load .env
env_path = os.path.join(os.path.dirname(__file__), "..", ".env")
if os.path.exists(env_path):
    with open(env_path) as f:
        for line in f:
            if "=" in line and not line.startswith("#"):
                k, v = line.strip().split("=", 1)
                os.environ.setdefault(k, v)

sys.path.insert(0, os.path.dirname(__file__))
import tech_analysis_scraper as t

print("Key present:", bool(t.API_KEY))
if t.API_KEY:
    result = t.get_tech_analysis()
    print(json.dumps(result, indent=2))
else:
    print("No Alpha Vantage API key found")
