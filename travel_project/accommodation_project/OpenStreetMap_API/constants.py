"""
Constants for OpenStreetMap_API:
- POI type definitions with Leaflet-compatible icons
- Overpass API tag mappings
"""

import os


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


# Nominatim base URL (no API key required)
NOMINATIM_BASE_URL = os.getenv("OSM_NOMINATIM_BASE_URL", "https://nominatim.openstreetmap.org").rstrip("/")
NOMINATIM_SEARCH_URL = os.getenv("OSM_NOMINATIM_URL", f"{NOMINATIM_BASE_URL}/search")
NOMINATIM_REVERSE_URL = os.getenv("OSM_NOMINATIM_REVERSE_URL", f"{NOMINATIM_BASE_URL}/reverse")

# Overpass API interpreters — tried in order (public instances may block some client IPs)
DEFAULT_OVERPASS_API_URLS = (
    "https://z.overpass-api.de/api/interpreter",
    "https://lz4.overpass-api.de/api/interpreter",
    "https://overpass.osm.ch/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.openstreetmap.fr/api/interpreter",
    "https://overpass-api.de/api/interpreter",
)
OVERPASS_API_URLS = tuple(
    url.strip()
    for url in os.getenv("OVERPASS_API_URLS", ",".join(DEFAULT_OVERPASS_API_URLS)).split(",")
    if url.strip()
)
OVERPASS_API_URL = OVERPASS_API_URLS[0]

# Default request timeout (seconds)
REQUEST_TIMEOUT = _env_int("OSM_REQUEST_TIMEOUT_SECONDS", 10)

# User-Agent required by Nominatim ToS
DEFAULT_NOMINATIM_USER_AGENT = "TravelProjectAccommodation/1.0"
NOMINATIM_USER_AGENT = os.getenv("GEOCODER_USER_AGENT", DEFAULT_NOMINATIM_USER_AGENT).strip()
if not NOMINATIM_USER_AGENT:
    NOMINATIM_USER_AGENT = DEFAULT_NOMINATIM_USER_AGENT

# ── POI type registry ────────────────────────────────────────────────────────
# Each entry: label, icon emoji, hex color, overpass tag(s)
POI_TYPES = {
    "restaurant": {
        "label": "Nhà hàng",
        "icon": "🍽️",
        "color": "#e53e3e",
        "tags": [("amenity", "restaurant")],
    },
    "cafe": {
        "label": "Quán cà phê",
        "icon": "☕",
        "color": "#dd6b20",
        "tags": [("amenity", "cafe")],
    },
    "hospital": {
        "label": "Bệnh viện",
        "icon": "🏥",
        "color": "#38a169",
        "tags": [("amenity", "hospital")],
    },
    "pharmacy": {
        "label": "Nhà thuốc",
        "icon": "💊",
        "color": "#319795",
        "tags": [("amenity", "pharmacy")],
    },
    "supermarket": {
        "label": "Siêu thị",
        "icon": "🛒",
        "color": "#3182ce",
        "tags": [("shop", "supermarket")],
    },
    "atm": {
        "label": "ATM",
        "icon": "🏧",
        "color": "#805ad5",
        "tags": [("amenity", "atm")],
    },
    "tourist_attraction": {
        "label": "Điểm du lịch",
        "icon": "🏛️",
        "color": "#d69e2e",
        "tags": [("tourism", "attraction"), ("tourism", "museum"), ("historic", "monument")],
    },
    "bar": {
        "label": "Quán bar",
        "icon": "🍺",
        "color": "#c05621",
        "tags": [("amenity", "bar"), ("amenity", "pub")],
    },
    "park": {
        "label": "Công viên",
        "icon": "🌳",
        "color": "#276749",
        "tags": [("leisure", "park")],
    },
    "bank": {
        "label": "Ngân hàng",
        "icon": "🏦",
        "color": "#4a5568",
        "tags": [("amenity", "bank")],
    },
    "gas_station": {
        "label": "Trạm xăng",
        "icon": "⛽",
        "color": "#718096",
        "tags": [("amenity", "fuel")],
    },
}

# Valid radius options (metres)
RADIUS_CHOICES = [1000, 2000, 3000, 4000, 5000]
DEFAULT_RADIUS = 1000
