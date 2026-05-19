"""
Service layer for OpenStreetMap_API.

All external HTTP calls to Nominatim / Overpass are isolated here.
Other apps should only import from this module (not from views directly).
"""

import logging
import math
import urllib.parse

import requests

from .constants import (
    DEFAULT_RADIUS,
    NOMINATIM_REVERSE_URL,
    NOMINATIM_SEARCH_URL,
    NOMINATIM_USER_AGENT,
    OVERPASS_API_URLS,
    POI_TYPES,
    RADIUS_CHOICES,
    REQUEST_TIMEOUT,
)

logger = logging.getLogger(__name__)


class OverpassUnavailableError(Exception):
    """Raised when all Overpass mirrors fail to respond."""


# ── shared session (reuse connections) ───────────────────────────────────────
_session = requests.Session()
_session.headers.update({"User-Agent": NOMINATIM_USER_AGENT})


# ── helpers ──────────────────────────────────────────────────────────────────

def _safe_get(url: str, params: dict) -> dict | list | None:
    """Perform a GET request and return parsed JSON or None on error."""
    try:
        resp = _session.get(url, params=params, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        return resp.json()
    except Exception as exc:  # noqa: BLE001
        logger.warning("OSM request failed: %s | url=%s params=%s", exc, url, params)
        return None


def _poi_meta(poi_type: str) -> dict:
    """Return icon / color / label for a POI type key."""
    return POI_TYPES.get(poi_type, {"label": poi_type, "icon": "📍", "color": "#718096"})


# ── public service functions ──────────────────────────────────────────────────

def geocode_address(address: str, country_codes: str = "vn") -> dict | None:
    """
    Forward-geocode an address string.

    Returns {'lat': float, 'lon': float, 'display_name': str, ...} or None.
    """
    data = _safe_get(
        NOMINATIM_SEARCH_URL,
        {
            "q": address,
            "format": "json",
            "limit": 1,
            "countrycodes": country_codes,
            "addressdetails": 1,
        },
    )
    if data and len(data) > 0:
        item = data[0]
        return {
            "lat": float(item["lat"]),
            "lon": float(item["lon"]),
            "display_name": item.get("display_name", address),
            "address": item.get("address", {}),
            "place_id": item.get("place_id"),
            "osm_id": item.get("osm_id"),
            "osm_type": item.get("osm_type"),
            "class": item.get("class"),
            "type": item.get("type"),
            "importance": item.get("importance"),
        }
    return None


def reverse_geocode(lat: float, lon: float) -> dict | None:
    """
    Reverse-geocode a coordinate pair.

    Returns address dict or None.
    """
    data = _safe_get(
        NOMINATIM_REVERSE_URL,
        {"lat": lat, "lon": lon, "format": "json"},
    )
    if data and "display_name" in data:
        return {
            "display_name": data["display_name"],
            "address": data.get("address", {}),
        }
    return None


def get_accommodation_coordinates(accommodation) -> dict:
    """
    Return the map-ready coordinate payload for an Accommodation instance.

    Tries stored lat/lon first, then falls back to geocoding the address.
    """
    geo = geocode_accommodation_address(accommodation)
    lat = geo.get("lat") if geo else None
    lon = geo.get("lon") if geo else None

    if lat is None or lon is None:
        return {"success": False, "error": "Không thể xác định tọa độ cho chỗ ở này."}

    return {
        "success": True,
        "accommodation_id": accommodation.pk,
        "name": accommodation.name,
        "lat": lat,
        "lon": lon,
        "address": f"{accommodation.address}, {accommodation.area}",
        "image_url": accommodation.image_url or "",
        "rating": accommodation.rating,
        "price_per_night": accommodation.price_per_night,
        "accommodation_type": accommodation.accommodation_type,
    }


def build_accommodation_geocode_query(accommodation) -> str:
    parts = [
        getattr(accommodation, "address", None),
        getattr(accommodation, "area", None),
        "Hồ Chí Minh",
        "Việt Nam",
    ]
    return ", ".join(str(part).strip() for part in parts if str(part or "").strip())


def geocode_accommodation_address(accommodation, *, save: bool = True) -> dict | None:
    """
    Resolve and cache an Accommodation coordinate pair.

    Stored latitude/longitude are always preferred; Nominatim is called only when
    either coordinate is missing.
    """
    lat = getattr(accommodation, "latitude", None)
    lon = getattr(accommodation, "longitude", None)
    if lat is not None and lon is not None:
        return {"lat": float(lat), "lon": float(lon), "source": "accommodation_cache"}

    query = build_accommodation_geocode_query(accommodation)
    if not query:
        return None

    try:
        from chat_api.services.geocoder import geocode_place

        geo_result = geocode_place(query)
    except Exception:
        geo_result = None

    if not geo_result or not geo_result.success:
        return None

    lat = geo_result.latitude
    lon = geo_result.longitude
    if lat is None or lon is None:
        return None

    if save:
        accommodation.latitude = float(lat)
        accommodation.longitude = float(lon)
        accommodation.save(update_fields=["latitude", "longitude"])

    return {
        "lat": float(lat),
        "lon": float(lon),
        "source": geo_result.source or "osm",
        "query": query,
        "display_name": geo_result.display_name,
    }


def _build_overpass_query(lat: float, lon: float, radius: int, poi_types: list[str]) -> str:
    """Build an Overpass QL query for multiple POI types around a point."""
    union_parts = []
    for poi_type in poi_types:
        meta = POI_TYPES.get(poi_type)
        if not meta:
            continue
        for key, value in meta["tags"]:
            union_parts.append(f'node["{key}"="{value}"](around:{radius},{lat},{lon});')
            union_parts.append(f'way["{key}"="{value}"](around:{radius},{lat},{lon});')

    if not union_parts:
        return ""

    parts_str = "\n  ".join(union_parts)
    return f"""
[out:json][timeout:25];
(
  {parts_str}
);
out center tags;
""".strip()


def _query_overpass(query: str) -> dict | None:
    """
    POST Overpass QL to public mirrors until one returns HTTP 200 and JSON.

    Mirrors differ in availability by region/IP; the main .de instance often
    returns 406 for some datacenter or cloud egress IPs.
    """
    timeout = REQUEST_TIMEOUT + 20
    last_detail = ""
    for url in OVERPASS_API_URLS:
        try:
            resp = _session.post(url, data={"data": query}, timeout=timeout)
            resp.raise_for_status()
            data = resp.json()
            if isinstance(data, dict):
                return data
            last_detail = f"{url}: response is not a JSON object"
        except ValueError as exc:
            last_detail = f"{url}: invalid JSON ({exc})"
        except requests.RequestException as exc:
            last_detail = f"{url}: {exc}"
    logger.warning("Overpass query failed on all mirrors: %s", last_detail)
    raise OverpassUnavailableError("Không thể kết nối đến dịch vụ bản đồ. Vui lòng thử lại sau.")


def search_pois(
    lat: float,
    lon: float,
    radius: int = DEFAULT_RADIUS,
    poi_types: list[str] | None = None,
) -> list[dict]:
    """
    Query Overpass API for POIs around (lat, lon).

    Parameters
    ----------
    lat, lon   : float  – centre point
    radius     : int    – search radius in metres (clamped to RADIUS_CHOICES)
    poi_types  : list   – subset of POI_TYPES keys; None means all types

    Returns list of POI dicts ready for JSON serialisation.
    Raises OverpassUnavailableError if all Overpass mirrors are unreachable.
    """
    if lat is None or lon is None:
        raise ValueError("Tọa độ không hợp lệ: lat/lon không được để trống.")

    # Clamp radius to nearest valid choice
    if radius not in RADIUS_CHOICES:
        radius = min(RADIUS_CHOICES, key=lambda r: abs(r - radius))

    types_to_query = poi_types if poi_types else list(POI_TYPES.keys())

    # Auto-expand radius when specific types requested but nothing found
    radii_to_try = [radius] + [r for r in RADIUS_CHOICES if r > radius]

    elements = []
    used_radius = radius
    for attempt_radius in radii_to_try:
        query = _build_overpass_query(lat, lon, attempt_radius, types_to_query)
        if not query:
            return []
        raw = _query_overpass(query)  # raises OverpassUnavailableError if all mirrors fail
        elements = raw.get("elements", [])
        if elements:
            used_radius = attempt_radius
            break
    pois = []
    seen = set()

    for el in elements:
        tags = el.get("tags", {})
        name = tags.get("name") or tags.get("name:vi") or tags.get("name:en")
        if not name:
            continue

        # Deduplicate by name + type (ways & nodes can both appear)
        el_lat = el.get("lat") or (el.get("center") or {}).get("lat")
        el_lon = el.get("lon") or (el.get("center") or {}).get("lon")
        if el_lat is None or el_lon is None:
            continue

        uid = (name, round(el_lat, 5), round(el_lon, 5))
        if uid in seen:
            continue
        seen.add(uid)

        # Detect which poi_type this element belongs to
        detected_type = _detect_poi_type(tags)
        meta = _poi_meta(detected_type)

        # Distance from centre
        dist = _haversine(lat, lon, el_lat, el_lon)

        pois.append(
            {
                "id": el.get("id"),
                "name": name,
                "type": detected_type,
                "type_label": meta["label"],
                "icon": meta["icon"],
                "color": meta["color"],
                "lat": el_lat,
                "lon": el_lon,
                "distance_m": round(dist),
                "tags": {
                    "phone": tags.get("phone") or tags.get("contact:phone", ""),
                    "website": tags.get("website") or tags.get("contact:website", ""),
                    "opening_hours": tags.get("opening_hours", ""),
                    "cuisine": tags.get("cuisine", ""),
                },
            }
        )

    # Sort by distance
    pois.sort(key=lambda p: p["distance_m"])
    return pois


def _detect_poi_type(tags: dict) -> str:
    """Match OSM tags against POI_TYPES definitions and return the type key."""
    for type_key, meta in POI_TYPES.items():
        for osm_key, osm_value in meta["tags"]:
            if tags.get(osm_key) == osm_value:
                return type_key
    return "other"


def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Return great-circle distance in metres between two coordinates."""
    R = 6_371_000  # Earth radius in metres
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def get_poi_centroid(
    poi_type: str,
    lat: float,
    lon: float,
    radius: int = 3000,
) -> tuple[float, float] | None:
    """
    Fetch all POIs of a given type around (lat, lon) and return their centroid.

    Used to resolve "gần cafe" intent: find the dense cluster of cafes and use
    its centre as the anchor for accommodation search — one Overpass call total.
    Returns None if no POIs found or Overpass is unavailable.
    """
    if lat is None or lon is None or poi_type not in POI_TYPES:
        return None
    try:
        query = _build_overpass_query(lat, lon, radius, [poi_type])
        if not query:
            return None
        raw = _query_overpass(query)
        elements = raw.get("elements", []) if raw else []
        lats, lons = [], []
        for el in elements:
            el_lat = el.get("lat") or (el.get("center") or {}).get("lat")
            el_lon = el.get("lon") or (el.get("center") or {}).get("lon")
            if el_lat is not None and el_lon is not None:
                lats.append(float(el_lat))
                lons.append(float(el_lon))
        if not lats:
            return None
        return sum(lats) / len(lats), sum(lons) / len(lons)
    except Exception:
        return None


def get_poi_types_metadata() -> list[dict]:
    """Return all registered POI types as a list (for frontend dropdowns)."""
    return [
        {"key": k, "label": v["label"], "icon": v["icon"], "color": v["color"]}
        for k, v in POI_TYPES.items()
    ]
