# backend/app/clients/tomtom.py
import os, requests

BASE_URL = (
"https://api.tomtom.com/traffic/services/4/flowSegmentData/absolute/10/json"
)

def get_flow_by_point(lat: float, lon: float, api_key: str) -> dict:
    """Fetch current traffic flow near a specific lat/lon point."""
    params = {"point": f"{lat},{lon}", "key": api_key}
    r = requests.get(BASE_URL, params=params, timeout=10)
    r.raise_for_status()
    return r.json()

