#!/usr/bin/env python3
"""Weather scraper - NWS grid forecast with daily aggregation (high/low/QPF/POP).

Matches Wunderground 5-day format: dayName, high|low °F, condition, precip inches.
Uses NWS forecastGridData for QPF aggregation and daily min/max temps.
"""

import requests
from datetime import datetime, timedelta
import re

HEADERS = {"User-Agent": "AI-News-Dashboard/1.0"}


def lat_lon_from_zip(zip_code):
    try:
        r = requests.get(f"https://api.zippopotam.us/us/{zip_code}", headers=HEADERS, timeout=10)
        if not r.ok:
            return None, None, None, None
        p = r.json()["places"][0]
        return float(p["latitude"]), float(p["longitude"]), p["place name"], p["state abbreviation"]
    except Exception:
        return None, None, None, None


def _parse_valid_time(vt):
    """Parse NWS validTime string: '2026-07-07T12:00:00+00:00/PT6H' -> (start_utc, duration_hours)."""
    m = re.match(r'(.+?)/(PT(\d+)H)?', vt)
    if not m:
        return None, 0
    start = datetime.fromisoformat(m.group(1))
    dur = int(m.group(3)) if m.group(3) else 0
    return start, dur


def _agg_daily(data_list, hours_per_day=24):
    """Aggregate NWS time-bucketed values into calendar-day totals.
    Returns list of {date_str, value}.
    """
    daily = {}
    for item in data_list:
        start, dur = _parse_valid_time(item["validTime"])
        if not start:
            continue
        val = item.get("value", 0) or 0
        # Distribute value across hours, bucket by calendar day (UTC for simplicity,
        # then convert. For US zips, EDT is UTC-4, EST is UTC-5)
        for h in range(dur):
            dt = start + timedelta(hours=h)
            dstr = dt.strftime("%Y-%m-%d")
            daily[dstr] = daily.get(dstr, 0) + (val / dur)
    return daily


def _max_daily(data_list):
    """Take max value per calendar day (for POP)."""
    daily = {}
    for item in data_list:
        start, dur = _parse_valid_time(item["validTime"])
        if not start:
            continue
        val = item.get("value", 0) or 0
        for h in range(dur):
            dt = start + timedelta(hours=h)
            dstr = dt.strftime("%Y-%m-%d")
            if val > daily.get(dstr, -1):
                daily[dstr] = val
    return daily


def _get_daily_periods(forecast_url, days=7):
    """Fetch 12-hourly periods and pair into day/night for daily summary."""
    r = requests.get(forecast_url, headers=HEADERS, timeout=15)
    if not r.ok:
        return []
    periods = r.json()["properties"]["periods"][:days * 2]

    # Pair consecutive periods (day + night)
    dailies = []
    for i in range(0, len(periods), 2):
        day = periods[i]
        night = periods[i + 1] if i + 1 < len(periods) else None
        dailies.append({
            "name": day["name"].split()[0] if " " in day["name"] else day["name"],  # "Wed" from "Wednesday"
            "full_name": day["name"],
            "date": day.get("startTime", "")[:10],
            "high": day["temperature"] if day.get("isDaytime") else (night["temperature"] if night else day["temperature"]),
            "low": night["temperature"] if night else day["temperature"],
            "condition": day.get("shortForecast", ""),
            "icon": day.get("icon", ""),
            "pop": day.get("probabilityOfPrecipitation", {}).get("value", 0) or 0,
        })
    return dailies


def get_weather_nws(zip_code, days=6):
    print(f"[ ] Fetching NWS grid weather for {zip_code}...")
    lat, lon, city, state = lat_lon_from_zip(zip_code)
    if not lat:
        return None

    # 1. Get grid metadata
    r = requests.get(f"https://api.weather.gov/points/{lat},{lon}", headers=HEADERS, timeout=10)
    if not r.ok:
        return None
    props = r.json()["properties"]

    # 2. Get grid forecast data (QPF, temps, POP)
    grid_url = props.get("forecastGridData", "")
    grid = None
    if grid_url:
        gr = requests.get(grid_url, headers=HEADERS, timeout=15)
        if gr.ok:
            grid = gr.json()["properties"]

    # 3. Get 12-hourly forecast for conditions and paired highs/lows
    forecast_url = props.get("forecast", "")
    daily_periods = _get_daily_periods(forecast_url, days=days) if forecast_url else []

    # 4. Aggregate grid data
    qpf_inches = {}
    pop_daily = {}
    max_temp = {}
    min_temp = {}

    if grid:
        # QPF: mm -> inches (divide by 25.4)
        qpf_mm = _agg_daily(grid.get("quantitativePrecipitation", {}).get("values", []))
        qpf_inches = {k: round(v / 25.4, 2) for k, v in qpf_mm.items()}

        # POP: max per day (percent)
        pop_raw = _max_daily(grid.get("probabilityOfPrecipitation", {}).get("values", []))
        pop_daily = {k: round(v) for k, v in pop_raw.items()}

        # Temps from grid (degC -> F)
        max_c = _max_daily(grid.get("maxTemperature", {}).get("values", []))
        min_c = _max_daily(grid.get("minTemperature", {}).get("values", []))
        max_temp = {k: round(v * 9/5 + 32) for k, v in max_c.items()}
        min_temp = {k: round(v * 9/5 + 32) for k, v in min_c.items()}

    # 5. Fetch current conditions from nearest observation station
    current = {}
    stations = props.get("observationStations", "")
    if stations:
        sr = requests.get(stations, headers=HEADERS, timeout=10)
        if sr.ok:
            first = sr.json()["features"][0]
            obs_r = requests.get(first["id"] + "/observations/latest", headers=HEADERS, timeout=10)
            if obs_r.ok:
                ob = obs_r.json()["properties"]
                temp_c = ob.get("temperature", {}).get("value")
                if temp_c:
                    current["temperature"] = round(temp_c * 9/5 + 32, 1)
                current["description"] = ob.get("textDescription", "")
                current["humidity"] = ob.get("relativeHumidity", {}).get("value")
                current["wind_speed"] = ob.get("windSpeed", {}).get("value")

    # 6. Build unified forecast list
    # Prefer daily_periods order, fill grid data where available
    seen_dates = set()
    forecast = []

    for dp in daily_periods:
        d = dp["date"]
        if d in seen_dates:
            continue
        seen_dates.add(d)

        # Use grid temps if available, else period temps
        high = max_temp.get(d, dp.get("high"))
        low = min_temp.get(d, dp.get("low"))
        pop = pop_daily.get(d, dp.get("pop", 0))
        qpf = qpf_inches.get(d, 0.0)

        forecast.append({
            "name": dp.get("name", ""),
            "date": d,
            "high": high,
            "low": low,
            "condition": dp.get("condition", ""),
            "pop": pop,
            "qpf": qpf,  # inches
            "icon": dp.get("icon", "")
        })

        if len(forecast) >= days:
            break

    return {
        "zip": zip_code,
        "city": city,
        "state": state,
        "lat": lat,
        "lon": lon,
        "current": current,
        "forecast": forecast,
        "source": "NWS",
        "timestamp": datetime.utcnow().isoformat()
    }


def get_weather_openmeteo(lat, lon, city=""):
    """Fallback: Open-Meteo for global locations."""
    try:
        url = "https://api.open-meteo.com/v1/forecast"
        params = {
            "latitude": lat, "longitude": lon,
            "current": "temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m",
            "daily": "temperature_2m_max,temperature_2m_min,weather_code,precipitation_sum",
            "timezone": "auto", "temperature_unit": "fahrenheit",
            "forecast_days": 7
        }
        r = requests.get(url, params=params, headers=HEADERS, timeout=15)
        r.raise_for_status()
        d = r.json()
        cur = d.get("current", {})
        daily = d.get("daily", {})

        codes = {
            0: "Clear", 1: "Mainly Clear", 2: "Partly Cloudy", 3: "Overcast",
            45: "Fog", 48: "Rime Fog", 51: "Light Drizzle", 53: "Drizzle",
            55: "Heavy Drizzle", 61: "Light Rain", 63: "Rain", 65: "Heavy Rain",
            71: "Light Snow", 73: "Snow", 75: "Heavy Snow", 77: "Snow Grains",
            80: "Light Showers", 81: "Showers", 82: "Heavy Showers",
            85: "Snow Showers", 86: "Heavy Snow Showers",
            95: "Thunderstorm", 96: "Thunderstorm + Hail", 99: "Heavy Thunderstorm"
        }

        forecast = []
        for i, day in enumerate(daily.get("time", [])):
            forecast.append({
                "name": day,
                "date": day,
                "high": daily["temperature_2m_max"][i],
                "low": daily["temperature_2m_min"][i],
                "condition": codes.get(daily["weather_code"][i], "Unknown"),
                "pop": 0,
                "qpf": round((daily.get("precipitation_sum") or [0] * 7)[i], 2),
                "icon": ""
            })

        return {
            "current": {
                "temperature": cur.get("temperature_2m"),
                "description": codes.get(cur.get("weather_code"), "Unknown"),
                "humidity": cur.get("relative_humidity_2m"),
                "wind_speed": cur.get("wind_speed_10m")
            },
            "forecast": forecast,
            "source": "Open-Meteo"
        }
    except Exception as e:
        print(f"Open-Meteo error: {e}")
        return {}


def get_weather(zip_code="10001"):
    """Master fetcher: NWS grid (US) with daily aggregation, fallback Open-Meteo."""
    result = get_weather_nws(zip_code)
    if result and result.get("forecast"):
        return result

    # Fallback
    lat, lon, city, state = lat_lon_from_zip(zip_code)
    if lat:
        om = get_weather_openmeteo(lat, lon, city)
        return {
            "zip": zip_code, "city": city, "state": state,
            "timestamp": datetime.utcnow().isoformat(),
            "current": om.get("current", {}),
            "forecast": om.get("forecast", []),
            "source": "Open-Meteo"
        }

    return {"error": f"Could not fetch weather for {zip_code}", "zip": zip_code}


if __name__ == "__main__":
    import json, sys
    z = sys.argv[1] if len(sys.argv) > 1 else "40272"
    w = get_weather(z)
    print(json.dumps(w, indent=2))
