#!/usr/bin/env python3
"""Weather scraper - NWS (US, server-side) + Open-Meteo (global, no key)."""

import requests
import json
from datetime import datetime

HEADERS = {"User-Agent": "AI-News-Dashboard/1.0"}

def lat_lon_from_zip(zip_code):
    """Free zip to lat/lon using Zippopotam.us."""
    try:
        r = requests.get(f"https://api.zippopotam.us/us/{zip_code}", headers=HEADERS, timeout=10)
        if not r.ok:
            # Fallback: use open-meteo geocoding
            return None, None, None, None
        data = r.json()
        places = data.get("places", [{}])[0]
        return (
            float(places.get("latitude", 0)),
            float(places.get("longitude", 0)),
            places.get("place name", ""),
            places.get("state abbreviation", "")
        )
    except Exception as e:
        print(f"Zip lookup error: {e}")
        return None, None, None, None

def get_weather_openmeteo(lat, lon, city=""):
    """Fetch weather from Open-Meteo (global, CORS-friendly, no key)."""
    try:
        url = "https://api.open-meteo.com/v1/forecast"
        params = {
            "latitude": lat,
            "longitude": lon,
            "current": "temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m",
            "daily": "temperature_2m_max,temperature_2m_min,weather_code",
            "timezone": "auto",
            "temperature_unit": "fahrenheit",
            "wind_speed_unit": "mph",
            "forecast_days": 4
        }
        r = requests.get(url, params=params, headers=HEADERS, timeout=15)
        r.raise_for_status()
        d = r.json()
        current = d.get("current", {})
        daily = d.get("daily", {})
        
        codes = {
            0: "Clear", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
            45: "Fog", 48: "Rime fog", 51: "Light drizzle", 53: "Drizzle",
            55: "Heavy drizzle", 61: "Light rain", 63: "Rain", 65: "Heavy rain",
            71: "Light snow", 73: "Snow", 75: "Heavy snow", 77: "Snow grains",
            80: "Light showers", 81: "Showers", 82: "Heavy showers", 85: "Snow showers",
            86: "Heavy snow showers", 95: "Thunderstorm", 96: "Thunderstorm + hail",
            99: "Heavy thunderstorm"
        }
        
        forecast = []
        days = daily.get("time", [])
        maxs = daily.get("temperature_2m_max", [])
        mins = daily.get("temperature_2m_min", [])
        wcodes = daily.get("weather_code", [])
        for i in range(min(len(days), 4)):
            forecast.append({
                "date": days[i],
                "high": maxs[i],
                "low": mins[i],
                "description": codes.get(wcodes[i], "Unknown")
            })
        
        return {
            "temperature": current.get("temperature_2m"),
            "humidity": current.get("relative_humidity_2m"),
            "description": codes.get(current.get("weather_code"), "Unknown"),
            "wind_speed": current.get("wind_speed_10m"),
            "forecast": forecast
        }
    except Exception as e:
        print(f"Open-Meteo error: {e}")
        return {}

def get_weather_nws(zip_code):
    """Fetch US weather from National Weather Service (most accurate for US)."""
    lat, lon, city, state = lat_lon_from_zip(zip_code)
    if not lat:
        return None
    try:
        r = requests.get(f"https://api.weather.gov/points/{lat},{lon}", headers=HEADERS, timeout=10)
        r.raise_for_status()
        props = r.json().get("properties", {})
        
        # Forecast
        forecast_url = props.get("forecast", "")
        forecast = []
        if forecast_url:
            fr = requests.get(forecast_url, headers=HEADERS, timeout=10)
            if fr.ok:
                periods = fr.json().get("properties", {}).get("periods", [])[:6]
                for p in periods:
                    forecast.append({
                        "name": p.get("name", ""),
                        "temp": p.get("temperature"),
                        "description": p.get("shortForecast", ""),
                        "detailed": (p.get("detailedForecast") or "")[:120]
                    })
        
        # Current conditions from nearest station
        current = {}
        stations_url = props.get("observationStations", "")
        if stations_url:
            sr = requests.get(stations_url, headers=HEADERS, timeout=10)
            if sr.ok:
                first = sr.json().get("features", [{}])[0]
                obs_url = first.get("id", "") + "/observations/latest"
                obs_r = requests.get(obs_url, headers=HEADERS, timeout=10)
                if obs_r.ok:
                    obs = obs_r.json().get("properties", {})
                    temp = obs.get("temperature", {}).get("value")
                    unit = obs.get("temperature", {}).get("unitCode", "")
                    desc = obs.get("textDescription", "")
                    # Convert C to F
                    if temp and unit == "wmoUnit:degC":
                        temp = temp * 9/5 + 32
                    current = {
                        "temperature": round(temp, 1) if temp else None,
                        "description": desc,
                        "humidity": obs.get("relativeHumidity", {}).get("value"),
                        "wind_speed": obs.get("windSpeed", {}).get("value")
                    }
        
        return {
            "city": city,
            "state": state,
            "current": current,
            "forecast": forecast,
            "source": "NWS"
        }
    except Exception as e:
        print(f"NWS error: {e}")
        return None

def get_weather(zip_code="10001"):
    """Master weather fetcher - tries NWS first (US), falls back to Open-Meteo."""
    print(f"[ ] Fetching weather for {zip_code}...")
    
    # Try NWS for US zips
    result = get_weather_nws(zip_code)
    if result:
        return {
            "zip": zip_code,
            "timestamp": datetime.utcnow().isoformat(),
            **result
        }
    
    # Fallback: Open-Meteo (global)
    lat, lon, city, state = lat_lon_from_zip(zip_code)
    if lat:
        om = get_weather_openmeteo(lat, lon, city)
        return {
            "zip": zip_code,
            "city": city,
            "state": state,
            "timestamp": datetime.utcnow().isoformat(),
            "current": {
                "temperature": om.get("temperature"),
                "description": om.get("description"),
                "humidity": om.get("humidity"),
                "wind_speed": om.get("wind_speed")
            },
            "forecast": om.get("forecast", []),
            "source": "Open-Meteo"
        }
    
    return {"error": f"Could not fetch weather for {zip_code}", "zip": zip_code}


if __name__ == "__main__":
    import sys
    z = sys.argv[1] if len(sys.argv) > 1 else "10001"
    print(json.dumps(get_weather(z), indent=2))
