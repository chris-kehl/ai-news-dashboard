#!/usr/bin/env python3
"""Unified location resolver: city name or ZIP → {zip, city, state, lat, lon}

APIs (all free, no key):
- Zippopotam.us  : US ZIP → city, state, lat, lon
- Open-Meteo geo : city name → lat, lon (worldwide)
- Open-Meteo rev : lat, lon → city name (worldwide)
"""
import requests, json, os, re

HEADERS = {"User-Agent": "AI-News-Dashboard/1.0 (Education)"}


def resolve_from_zip(zip_code: str) -> dict:
    """US ZIP via Zippopotam.us"""
    try:
        z = re.sub(r"\D", "", zip_code)[:5]
        if len(z) != 5:
            return {}
        r = requests.get(f"https://api.zippopotam.us/us/{z}", headers=HEADERS, timeout=10)
        if not r.ok:
            return {}
        data = r.json()
        place = data.get("places", [{}])[0]
        return {
            "zip": z,
            "city": place.get("place name", ""),
            "state": place.get("state", ""),
            "state_abbrev": place.get("state abbreviation", ""),
            "lat": float(place.get("latitude", 0) or 0),
            "lon": float(place.get("longitude", 0) or 0),
        }
    except Exception as e:
        print(f"[WARN] ZIP lookup failed: {e}")
        return {}


def geocode_city(query: str) -> dict:
    """City name → lat, lon via Open-Meteo geocoding (free, no key)."""
    try:
        params = {"name": query, "count": 1, "language": "en", "format": "json"}
        r = requests.get("https://geocoding-api.open-meteo.com/v1/search", params=params, headers=HEADERS, timeout=10)
        r.raise_for_status()
        results = r.json().get("results", [])
        if not results:
            return {}
        p = results[0]
        return {
            "zip": "",
            "city": p.get("name", ""),
            "state": p.get("admin1", ""),
            "state_abbrev": "",
            "country": p.get("country", ""),
            "lat": p.get("latitude", 0),
            "lon": p.get("longitude", 0),
        }
    except Exception as e:
        print(f"[WARN] City geocoding failed: {e}")
        return {}


def resolve_location(query: str) -> dict:
    """Universal resolver: auto-detects ZIP (5 digits) or city name."""
    query = query.strip()
    # If it looks like a US ZIP code
    if re.match(r"^\d{5}(-\d{4})?$", query):
        return resolve_from_zip(query)
    # Otherwise treat as city name
    return geocode_city(query)


def load_config(scraper_dir: str) -> dict:
    """Read scraper/config.json if it exists."""
    path = os.path.join(scraper_dir, "config.json")
    if os.path.exists(path):
        try:
            with open(path) as f:
                return json.load(f).get("config", {})
        except Exception:
            pass
    return {"zip": "40272", "city": "Louisville", "state": "Kentucky", "lat": 38.0846, "lon": -85.851}


def save_config(scraper_dir: str, location: dict) -> None:
    """Write scraper/config.json with new location."""
    path = os.path.join(scraper_dir, "config.json")
    config = load_config(scraper_dir)
    config = {**config, **location}
    with open(path, "w") as f:
        json.dump({"config": config}, f, indent=2)
    print(f"[OK] Config saved: {config.get('city')}, {config.get('state')}")


if __name__ == "__main__":
    import sys
    q = sys.argv[1] if len(sys.argv) > 1 else "Louisville"
    print(json.dumps(resolve_location(q), indent=2))
