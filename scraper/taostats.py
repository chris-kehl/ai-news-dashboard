"""Fetch Bittensor subnet data from TAOSTATS (free tier).
Falls back to cached static data if API is unavailable.
"""
import os, json, requests, sys

def fetch_taostats():
    key = os.environ.get('TAOSTATS_API_KEY', '')
    if not key:
        print("[WARN] No TAOSTATS_API_KEY found. Returning cached static data.")
        return None

    headers = {"Authorization": key}
    try:
        # Subnets list endpoint
        r = requests.get(
            "https://api.taostats.io/api/v1/subnets",
            headers=headers,
            timeout=15
        )
        r.raise_for_status()
        data = r.json()
        subnets = data.get('subnets', data.get('data', []))
        print(f"[OK] TAOSTATS: fetched {len(subnets)} subnets")
        return subnets
    except Exception as e:
        print(f"[WARN] TAOSTATS API error: {e}")
        return None

def format_subnets(raw_subnets):
    """Convert TAOSTATS subnet list to our format."""
    formatted = []
    for sn in raw_subnets:
        name = sn.get('name') or f"SN{sn.get('netuid', '?')}"
        emission = float(sn.get('emission', 0))
        miners = int(sn.get('total_miners', sn.get('miner_count', sn.get('neurons', 0))))
        change_pct = float(sn.get('price_change_24h', sn.get('change_24h', 0)))
        change_str = ("+" if change_pct >= 0 else "") + f"{change_pct:.1f}%"
        formatted.append({
            "name": name,
            "miners": miners,
            "emission": round(emission, 1),
            "change": change_str
        })
    # Sort by emission descending
    formatted.sort(key=lambda x: x["emission"], reverse=True)
    return formatted

def get_bittensor_data():
    raw = fetch_taostats()
    if raw:
        top = format_subnets(raw)
        # Get TAO price from CoinGecko as backup (or from first subnet's parent data)
        try:
            cg = requests.get(
                "https://api.coingecko.com/api/v3/simple/price?ids=bittensor&vs_currencies=usd&include_24hr_change=true",
                timeout=10
            ).json()
            tao_usd = cg['bittensor']['usd']
            tao_change = cg['bittensor']['usd_24h_change']
        except Exception as e:
            print(f"[WARN] CG price fallback failed: {e}")
            tao_usd = 216.58
            tao_change = -0.6
        return {
            "price": tao_usd,
            "price_change_24h": tao_change,
            "active_subnets": len(top),
            "total_miners": sum(s["miners"] for s in top),
            "top_subnets": top[:12]  # Return top 12
        }
    else:
        # Fallback static data
        return {
            "price": 216.58,
            "price_change_24h": -0.613,
            "active_subnets": 128,
            "total_miners": 8870,
            "top_subnets": [
                {"name": "SN1 (Text)", "miners": 2560, "emission": 18.5, "change": "+1.2%"},
                {"name": "SN39 (Vision)", "miners": 1450, "emission": 15.1, "change": "+0.8%"},
                {"name": "SN22 (Data)", "miners": 1840, "emission": 12.5, "change": "+2.3%"},
                {"name": "SN7 (Storage)", "miners": 2100, "emission": 11.0, "change": "-1.5%"},
                {"name": "SN41 (Audio)", "miners": 920, "emission": 8.2, "change": "-5.1%"}
            ]
        }

if __name__ == '__main__':
    data = get_bittensor_data()
    print(json.dumps(data, indent=2))
