#!/usr/bin/env python3
"""Batch scraper for 25 major cities. Runs every 30s via launchd.

- Weather + News: all 25 cities every cycle (~5s with 5 threads)
- Reddit: rotates 5 cities/cycle -> full coverage every 2.5 min
- X removed from batch (too slow via Playwright); client fallback handles it
- Auto-clears cache entries >24h old
- Lockfile prevents overlapping runs
"""
import json, os, sys, time, random, requests
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import quote

SCRAPER_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(SCRAPER_DIR)
CACHE_FILE = os.path.join(REPO_ROOT, "city_cache.json")
LOCK_FILE = os.path.join(REPO_ROOT, ".batch_lock")
CYCLE_FILE = os.path.join(SCRAPER_DIR, ".batch_cycle")

HEADERS = {"User-Agent": "AI-News-Dashboard/1.0"}
BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

# Top 25 cities by metro population + Toronto + London
CITIES = [
    {"name": "New York",         "state": "New York",             "lat": 40.71, "lon": -74.01},
    {"name": "Los Angeles",      "state": "California",           "lat": 34.05, "lon": -118.24},
    {"name": "Chicago",          "state": "Illinois",             "lat": 41.88, "lon": -87.63},
    {"name": "Houston",          "state": "Texas",                "lat": 29.76, "lon": -95.37},
    {"name": "Phoenix",          "state": "Arizona",              "lat": 33.45, "lon": -112.07},
    {"name": "Philadelphia",     "state": "Pennsylvania",         "lat": 39.95, "lon": -75.17},
    {"name": "San Antonio",      "state": "Texas",                "lat": 29.42, "lon": -98.49},
    {"name": "San Diego",        "state": "California",           "lat": 32.72, "lon": -117.16},
    {"name": "Dallas",           "state": "Texas",                "lat": 32.78, "lon": -96.80},
    {"name": "San Jose",         "state": "California",           "lat": 37.34, "lon": -121.89},
    {"name": "Austin",           "state": "Texas",                "lat": 30.27, "lon": -97.74},
    {"name": "Jacksonville",     "state": "Florida",              "lat": 30.33, "lon": -81.66},
    {"name": "Fort Worth",       "state": "Texas",                "lat": 32.76, "lon": -97.33},
    {"name": "Columbus",         "state": "Ohio",                 "lat": 39.96, "lon": -83.00},
    {"name": "Charlotte",        "state": "North Carolina",       "lat": 35.23, "lon": -80.84},
    {"name": "Indianapolis",     "state": "Indiana",              "lat": 39.77, "lon": -86.16},
    {"name": "San Francisco",    "state": "California",           "lat": 37.77, "lon": -122.42},
    {"name": "Seattle",          "state": "Washington",           "lat": 47.61, "lon": -122.33},
    {"name": "Denver",           "state": "Colorado",             "lat": 39.74, "lon": -105.00},
    {"name": "Washington DC",    "state": "District of Columbia", "lat": 38.91, "lon": -77.04},
    {"name": "Boston",           "state": "Massachusetts",        "lat": 42.36, "lon": -71.06},
    {"name": "Nashville",        "state": "Tennessee",            "lat": 36.16, "lon": -86.78},
    {"name": "Detroit",          "state": "Michigan",             "lat": 42.33, "lon": -83.05},
    {"name": "Miami",            "state": "Florida",              "lat": 25.76, "lon": -80.19},
    {"name": "Atlanta",          "state": "Georgia",              "lat": 33.75, "lon": -84.39},
    {"name": "London",           "state": "United Kingdom",       "lat": 51.51, "lon": -0.13},
    {"name": "Toronto",          "state": "Ontario",              "lat": 43.65, "lon": -79.38},
]


def city_key(city):
    return city["name"].lower().replace(" ", "_")


def acquire_lock():
    try:
        fd = os.open(LOCK_FILE, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.write(fd, str(os.getpid()).encode())
        os.close(fd)
        return True
    except FileExistsError:
        # Check if stale lock
        try:
            with open(LOCK_FILE) as f:
                pid = int(f.read().strip())
            os.kill(pid, 0)
            return False  # process alive
        except (ValueError, OSError, ProcessLookupError):
            os.remove(LOCK_FILE)
            return acquire_lock()


def release_lock():
    try:
        os.remove(LOCK_FILE)
    except OSError:
        pass


def load_cache():
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, 'r') as f:
                return json.load(f)
        except Exception as e:
            print(f"[CACHE] Load error: {e}")
    return {}


def save_cache(cache):
    tmp = CACHE_FILE + ".tmp"
    with open(tmp, 'w') as f:
        json.dump(cache, f, indent=2)
    os.replace(tmp, CACHE_FILE)


def clear_stale(cache):
    cutoff = datetime.utcnow() - timedelta(hours=24)
    stale = []
    for k, v in cache.items():
        try:
            ts = datetime.fromisoformat(v.get("timestamp", "2000-01-01")).replace(tzinfo=None)
            if ts < cutoff:
                stale.append(k)
        except Exception:
            stale.append(k)
    for k in stale:
        del cache[k]
    if stale:
        print(f"[CACHE] Cleared {len(stale)} stale entries")
    return cache


def get_cycle():
    try:
        with open(CYCLE_FILE) as f:
            return int(f.read().strip())
    except Exception:
        return 0


def set_cycle(n):
    with open(CYCLE_FILE, 'w') as f:
        f.write(str(n))


def get_rotation_batch(cities, cycle, batch_size=5):
    total = len(cities)
    start = (cycle * batch_size) % total
    end = start + batch_size
    if end <= total:
        return cities[start:end]
    return cities[start:] + cities[:end - total]


# ── Weather ──────────────────────────────────────────────────────────────────

WEATHER_CODES = {
    0: "Clear", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
    45: "Fog", 48: "Rime fog", 51: "Light drizzle", 53: "Drizzle", 55: "Heavy drizzle",
    61: "Light rain", 63: "Rain", 65: "Heavy rain", 71: "Light snow", 73: "Snow",
    75: "Heavy snow", 77: "Snow grains", 80: "Light showers", 81: "Showers",
    82: "Heavy showers", 85: "Snow showers", 86: "Heavy snow showers",
    95: "Thunderstorm", 96: "Thunderstorm + hail", 99: "Heavy thunderstorm",
}


def fetch_weather(city):
    try:
        time.sleep(random.uniform(0.05, 0.2))
        url = "https://api.open-meteo.com/v1/forecast"
        params = {
            "latitude": city["lat"], "longitude": city["lon"],
            "current": "temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m",
            "daily": "temperature_2m_max,temperature_2m_min,weather_code",
            "timezone": "auto", "temperature_unit": "fahrenheit",
            "wind_speed_unit": "mph", "forecast_days": 4,
        }
        r = requests.get(url, params=params, headers=HEADERS, timeout=12)
        r.raise_for_status()
        d = r.json()
        cur = d.get("current", {})
        daily = d.get("daily", {})
        forecast = []
        for i in range(min(len(daily.get("time", [])), 4)):
            forecast.append({
                "date": daily["time"][i],
                "high": daily["temperature_2m_max"][i],
                "low": daily["temperature_2m_min"][i],
                "description": WEATHER_CODES.get(daily["weather_code"][i], "Unknown"),
            })
        return {
            "temperature": cur.get("temperature_2m"),
            "humidity": cur.get("relative_humidity_2m"),
            "description": WEATHER_CODES.get(cur.get("weather_code"), "Unknown"),
            "wind_speed": cur.get("wind_speed_10m"),
            "forecast": forecast,
        }
    except Exception as e:
        print(f"  [WEATHER] {city['name']}: {e}")
        return {}


# ── News (Bing RSS) ──────────────────────────────────────────────────────────


def fetch_news(city):
    try:
        time.sleep(random.uniform(0.1, 0.3))
        query = f"{city['name']} news"
        url = f"https://www.bing.com/news/search?q={quote(query)}&format=rss"
        r = requests.get(url, headers=BROWSER_HEADERS, timeout=12)
        if r.status_code != 200:
            return []
        root = ET.fromstring(r.content)
        articles = []
        for item in root.findall(".//item"):
            title = item.findtext("title", "").strip()
            link = item.findtext("link", "").strip()
            if title and link:
                articles.append({"title": title[:200], "url": link, "source": "Bing News"})
            if len(articles) >= 5:
                break
        return articles
    except Exception as e:
        print(f"  [NEWS] {city['name']}: {e}")
        return []


# ── Reddit (old.reddit search RSS) ───────────────────────────────────────────


def fetch_reddit(city):
    try:
        time.sleep(random.uniform(1.0, 2.0))
        q = quote(f"{city['name']}")
        url = f"https://old.reddit.com/search/.rss?q={q}&sort=new&limit=5"
        r = requests.get(url, headers=BROWSER_HEADERS, timeout=12)
        if r.status_code != 200:
            return []
        root = ET.fromstring(r.content)
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        posts = []
        for entry in root.findall("atom:entry", ns):
            title_el = entry.find("atom:title", ns)
            link_el = entry.find("atom:link", ns)
            if title_el is None or link_el is None:
                continue
            title = title_el.text or ""
            link = link_el.get("href", "")
            if title and link:
                posts.append({"title": title[:200], "url": link, "subreddit": "search", "score": 0})
            if len(posts) >= 5:
                break
        return posts
    except Exception as e:
        print(f"  [REDDIT] {city['name']}: {e}")
        return []


# ── Main ─────────────────────────────────────────────────────────────────────


def run_batch():
    if not acquire_lock():
        print("[BATCH] Another instance is running. Exiting.")
        return
    try:
        t0 = time.time()
        now_str = datetime.utcnow().isoformat()
        print(f"\n{'='*55}\n[BATCH] {now_str} | {len(CITIES)} cities\n{'='*55}")

        cache = load_cache()
        cache = clear_stale(cache)
        cycle = get_cycle()
        print(f"[BATCH] Cycle #{cycle}")

        # 1. Weather — all cities, 5 threads
        print("[BATCH] Fetching weather...")
        with ThreadPoolExecutor(max_workers=5) as ex:
            futs = {ex.submit(fetch_weather, c): c for c in CITIES}
            for f in as_completed(futs):
                c = futs[f]
                k = city_key(c)
                try:
                    w = f.result()
                    if k not in cache:
                        cache[k] = {"city": c["name"], "state": c["state"],
                                   "lat": c["lat"], "lon": c["lon"]}
                    cache[k]["timestamp"] = now_str
                    if w:
                        cache[k]["weather"] = w
                except Exception as e:
                    print(f"  [ERR] Weather {c['name']}: {e}")

        # 2. News — all cities, 4 threads
        print("[BATCH] Fetching news...")
        with ThreadPoolExecutor(max_workers=4) as ex:
            futs = {ex.submit(fetch_news, c): c for c in CITIES}
            for f in as_completed(futs):
                c = futs[f]
                k = city_key(c)
                try:
                    n = f.result()
                    if k in cache:
                        cache[k]["news"] = n
                except Exception as e:
                    print(f"  [ERR] News {c['name']}: {e}")

        # 3. Reddit — rotate 5 cities per cycle
        reddit_batch = get_rotation_batch(CITIES, cycle, batch_size=5)
        print(f"[BATCH] Reddit batch: {', '.join(c['name'] for c in reddit_batch)}")
        for c in reddit_batch:
            k = city_key(c)
            posts = fetch_reddit(c)
            if k in cache:
                cache[k]["reddit"] = posts

        save_cache(cache)
        set_cycle(cycle + 1)
        elapsed = round(time.time() - t0, 1)
        print(f"[BATCH] Saved {len(cache)} cities -> {CACHE_FILE}")
        print(f"[BATCH] Done in {elapsed}s")
    finally:
        release_lock()


if __name__ == "__main__":
    run_batch()
