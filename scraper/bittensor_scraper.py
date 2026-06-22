#!/usr/bin/env python3
"""Bittensor subnet intelligence scraper."""

import requests
import json
from datetime import datetime

BITTENSOR_RPC = "https://api.chainweb.com/chainweb/0.0/mainnet01/chain/0/pact"
# Alternative public endpoints
SUBSCAN_API = "https://bittensor.api.subscan.io/api"

# Fallback: simple HTTP endpoints for subnet data
TAO_STATS_API = "https://taostats.io/api/"

def get_tao_price():
    """Get TAO price from CoinGecko or similar."""
    try:
        response = requests.get(
            "https://api.coingecko.com/api/v3/simple/price?ids=bittensor&vs_currencies=usd&include_24hr_change=true",
            timeout=10
        )
        data = response.json()
        return {
            "price": data["bittensor"]["usd"],
            "price_change_24h": data["bittensor"]["usd_24h_change"]
        }
    except Exception as e:
        print(f"Price fetch error: {e}")
        return {"price": 0, "price_change_24h": 0}

def get_subnet_data():
    """Fetch subnet data from public sources."""
    # Try taostats API first
    subnet_data = []
    try:
        response = requests.get(
            "https://taostats.io/api/subnets",
            headers={"User-Agent": "AI-News-Dashboard/1.0"},
            timeout=15
        )
        if response.status_code == 200:
            data = response.json()
            for sn in data.get("subnets", [])[:10]:
                subnet_data.append({
                    "name": f"SN{sn.get('netuid', 0)}",
                    "miners": sn.get("miners", 0),
                    "emission": round(sn.get("emission", 0), 2),
                    "change": f"{sn.get('change_24h', 0):+.1f}%"
                })
    except Exception as e:
        print(f"Subnet data error: {e}")
    
    if not subnet_data:
        # Fallback mock data for development
        subnet_data = [
            {"name": "SN1", "miners": 2560, "emission": 18.5, "change": "+1.2%"},
            {"name": "SN22", "miners": 1840, "emission": 12.5, "change": "+2.3%"},
            {"name": "SN41", "miners": 920, "emission": 8.2, "change": "-5.1%"},
            {"name": "SN39", "miners": 1450, "emission": 15.1, "change": "+0.8%"},
            {"name": "SN7", "miners": 2100, "emission": 11.0, "change": "-1.5%"},
        ]
    
    return subnet_data

def get_bittensor_intelligence():
    """Get full Bittensor intelligence report."""
    price_data = get_tao_price()
    subnets = get_subnet_data()
    
    # Calculate metrics
    total_miners = sum(sn["miners"] for sn in subnets)
    active_subnets = len(subnets)
    
    # Generate signals
    signals = []
    for sn in subnets[:5]:
        change_val = float(sn["change"].replace('%', '').replace('+', ''))
        if change_val > 3:
            signals.append({
                "type": "watch",
                "text": f"{sn['name']} emissions +{change_val}%"
            })
        elif change_val < -4:
            signals.append({
                "type": "sell",
                "text": f"{sn['name']} miners leaving ({change_val}%)"
            })
    
    if price_data["price_change_24h"] > 5:
        signals.append({"type": "buy", "text": "TAO breakout +5%"})
    elif price_data["price_change_24h"] < -5:
        signals.append({"type": "watch", "text": "TAO dip -5% accumulation"})
    
    return {
        **price_data,
        "active_subnets": active_subnets,
        "total_miners": total_miners,
        "top_subnets": subnets,
        "signals": signals
    }

if __name__ == "__main__":
    data = get_bittensor_intelligence()
    print(f"TAO Price: ${data['price']:.2f} ({data['price_change_24h']:+.1f}%)")
    print(f"Active Subnets: {data['active_subnets']}")
    print(f"Total Miners: {data['total_miners']}")
    print("\nTop Subnets:")
    for sn in data['top_subnets'][:5]:
        print(f"  {sn['name']}: {sn['miners']} miners, {sn['emission']} TAO/day ({sn['change']})")
    print("\nSignals:")
    for sig in data['signals']:
        print(f"  [{sig['type']}] {sig['text']}")
