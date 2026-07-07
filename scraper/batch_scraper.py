#!/usr/bin/env python3
"""Batch scraper - rotates through 50 major cities every 30 seconds.
Caches weather, news, Reddit, X per city. Evicts >24h.
"""
import json, os, sys, time, hashlib, traceback
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

SCRAPER_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR    = os.path.dirname(SCRAPER_DIR)
CACHE_DIR   = os.path.join(ROOT_DIR, "cache")
os.makedirs(CACHE_DIR, exist_ok=True)

CITIES = [
    ("New York","NY"),("Los Angeles","CA"),("Chicago","IL"),("Houston","TX"),
    ("Phoenix","AZ"),("Philadelphia","PA"),("San Antonio","TX"),("San Diego","CA"),
    ("Dallas","TX"),("San Jose","CA"),("Austin","TX"),("Jacksonville","FL"),
    ("Fort Worth","TX"),("Columbus","OH"),("Charlotte","NC"),("Indianapolis","IN"),
    ("San Francisco","CA"),("Seattle","WA"),("Denver","CO"),("Washington","DC"),
    ("Boston","MA"),("El Paso","TX"),("Nashville","TN"),("Detroit","MI"),
    ("Oklahoma City","OK"),("Portland","OR"),("Las Vegas","NV"),("Louisville","KY"),
    ("Baltimore","MD"),("Milwaukee","WI"),("Albuquerque","NM"),("Tucson","AZ"),
    ("Fresno","CA"),("Mesa","AZ"),("Sacramento","CA"),("Atlanta","GA"),
    ("Kansas City","MO"),("Colorado Springs","CO"),("Omaha","NE"),("Raleigh","NC"),
    ("Miami","FL"),("Long Beach","CA"),("Virginia Beach","VA"),("Oakland","CA"),
    ("Minneapolis","MN"),("Tulsa","OK"),("Arlington","TX"),("New Orleans","LA"),
    ("Wichita","KS"),("Cleveland","OH"),("Tampa","FL")
]

TTL_HOURS = 24
BATCH_INTERVAL = 30  # seconds between city scrapes

sys.path.insert(0, SCRAPER_DIR)
from weather_scraper import get_weather
from local_scraper import get_local_content
from local_news_scraper import get_local_news

NEWSAPI_KEY=os.environ.get("NEWSAPI_KEY","")

def _city_slug(city, state):
    return f"{city.lower().replace(' ','_')}_{state.lower()}"

def _cache_path(city, state):
    return os.path.join(CACHE_DIR, f"{_city_slug(city,state)}.json")

def _is_stale(city, state):
    cp = _cache_path(city, state)
    if not os.path.exists(cp):
        return True
    try:
        mtime = datetime.fromtimestamp(os.path.getmtime(cp))
        if datetime.now() - mtime > timedelta(hours=TTL_HOURS):
            return True
    except Exception:
        return True
    return False

def _load_cache(city, state):
    cp = _cache_path(city, state)
    if os.path.exists(cp):
        try:
            with open(cp) as f:
                return json.load(f)
        except Exception:
            pass
    return None

def _save_cache(city, state, data):
    cp = _cache_path(city, state)
    data["cached_at"] = datetime.now().isoformat()
    with open(cp, 'w') as f:
        json.dump(data, f, indent=2)

def _lookup_zip(city, state):
    """Simple mapping for common cities to avoid geocode API churn."""
    mapping = {
        ("New York","NY"):"10001",("Los Angeles","CA"):"90001",("Chicago","IL"):"60601",
        ("Houston","TX"):"77001",("Phoenix","AZ"):"85001",("Philadelphia","PA"):"19019",
        ("San Antonio","TX"):"78201",("San Diego","CA"):"92014",("Dallas","TX"):"75201",
        ("San Jose","CA"):"95101",("Austin","TX"):"78701",("Jacksonville","FL"):"32099",
        ("Fort Worth","TX"):"76101",("Columbus","OH"):"43004",("Charlotte","NC"):"28201",
        ("Indianapolis","IN"):"46201",("San Francisco","CA"):"94102",("Seattle","WA"):"98101",
        ("Denver","CO"):"80201",("Washington","DC"):"20001",("Boston","MA"):"02101",
        ("El Paso","TX"):"79901",("Nashville","TN"):"37201",("Detroit","MI"):"48201",
        ("Oklahoma City","OK"):"73101",("Portland","OR"):"97201",("Las Vegas","NV"):"89101",
        ("Louisville","KY"):"40202",("Baltimore","MD"):"21201",("Milwaukee","WI"):"53201",
        ("Albuquerque","NM"):"87101",("Tucson","AZ"):"85701",("Fresno","CA"):"93701",
        ("Mesa","AZ"):"85201",("Sacramento","CA"):"95814",("Atlanta","GA"):"30301",
        ("Kansas City","MO"):"64101",("Colorado Springs","CO"):"80901",("Omaha","NE"):"68101",
        ("Raleigh","NC"):"27601",("Miami","FL"):"33101",("Long Beach","CA"):"90802",
        ("Virginia Beach","VA"):"23450",("Oakland","CA"):"94601",("Minneapolis","MN"):"55401",
        ("Tulsa","OK"):"74101",("Arlington","TX"):"76001",("New Orleans","LA"):"70112",
        ("Wichita","KS"):"67201",("Cleveland","OH"):"44101",("Tampa","FL"):"33601"
    }
    return mapping.get((city, state), "40272")

def _scrape_one(city, state):
    """Scrape a single city: weather, local news, Reddit, X."""
    t0 = time.time()
    slug = _city_slug(city, state)
    print(f"[BATCH] {city}, {state}")
    try:
        zipcode = _lookup_zip(city, state)
        weather = get_weather(zipcode)
        weather["city"] = city
        weather["state"] = state

        local_data = get_local_content(city, state, max_x=8, max_reddit=8)
        news_data  = get_local_news(city, state, NEWSAPI_KEY)

        payload = {
            "city": city,
            "state": state,
            "zip": zipcode,
            "weather": weather,
            "news": news_data.get("articles", []),
            "reddit": local_data.get("reddit_posts", []),
            "x_posts": local_data.get("x_posts", []),
            "channels": [],
            "cached_at": datetime.now().isoformat()
        }
        _save_cache(city, state, payload)
        dt = time.time() - t0
        print(f"[BATCH] {slug} OK ({len(payload['news'])} news, {len(payload['reddit'])} reddit, {len(payload['x_posts'])} x) in {dt:.1f}s")
        return True
    except Exception as e:
        print(f"[BATCH] {slug} FAILED: {e}")
        traceback.print_exc()
        return False

def run_batch():
    """One-pass: scrape every stale city in the 50-city list."""
    stale = [(c, s) for c, s in CITIES if _is_stale(c, s)]
    if not stale:
        print("[BATCH] All cities fresh, nothing to do.")
        return
    print(f"[BATCH] {len(stale)}/{len(CITIES)} cities stale, starting...")
    ok = 0
    for city, state in stale:
        if _scrape_one(city, state):
            ok += 1
        time.sleep(max(0, BATCH_INTERVAL - 5))  # ~30s between starts
    print(f"[BATCH] Done. {ok}/{len(stale)} succeeded.")

def get_city_data(city, state):
    """Read cached data for a city (used by frontend/bridge)."""
    if _is_stale(city, state):
        return None
    return _load_cache(city, state)

def get_all_cached():
    """Return list of all cached city slugs with freshness."""
    out = []
    for c, s in CITIES:
        cp = _cache_path(c, s)
        fresh = os.path.exists(cp) and not _is_stale(c, s)
        out.append({"city": c, "state": s, "slug": _city_slug(c,s), "fresh": fresh})
    return out

if __name__ == "__main__":
    run_batch()
