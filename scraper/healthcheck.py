#!/usr/bin/env python3
"""Health-check ping — notify if scraper stops running."""

import os
import sys
import time
import json
import requests
from datetime import datetime

HEALTHCHECK_URL = os.getenv("HEALTHCHECK_URL", "")

def load_last_run(data_path="data.json"):
    """Get timestamp of last successful scrape from data.json."""
    try:
        with open(data_path) as f:
            data = json.load(f)
        ts = datetime.fromisoformat(data.get("timestamp", ""))
        age_seconds = (datetime.now() - ts).total_seconds()
        return ts, age_seconds
    except Exception as e:
        print(f"[health] Cannot read data.json: {e}")
        return None, float('inf')

def ping_uptime_service(status="up", msg=""):
    """Ping a Uptime Kuma / Healthchecks.io / Cronitor URL."""
    url = HEALTHCHECK_URL
    if not url:
        return False
    try:
        payload = {"status": status, "msg": msg, "ping": int(time.time())}
        r = requests.post(url, json=payload, timeout=15)
        r.raise_for_status()
        print(f"[health] Pinged {status}")
        return True
    except Exception as e:
        print(f"[health] Ping failed: {e}")
        return False

def check_and_report(data_path="data.json", max_age_minutes=30):
    """Check data freshness and report status."""
    last_ts, age = load_last_run(data_path)

    if last_ts is None:
        status = "down"
        msg = f"No data.json found or unreadable at {datetime.now().isoformat()}"
    elif age > max_age_minutes * 60:
        status = "down"
        msg = f"Data stale: {age/60:.0f} minutes old (last: {last_ts.isoformat()})"
    else:
        status = "up"
        msg = f"Data fresh: {age/60:.1f} minutes old"

    print(f"[health] Status: {status} — {msg}")
    ping_uptime_service(status, msg)
    return status == "up"

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", default="../data.json")
    parser.add_argument("--max-age", type=int, default=30)
    args = parser.parse_args()

    ok = check_and_report(args.data, args.max_age)
    sys.exit(0 if ok else 1)
