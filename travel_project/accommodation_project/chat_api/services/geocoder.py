from __future__ import annotations

import os
import re
from dataclasses import asdict, dataclass
from typing import Any

import requests

from ..location_gazetteer import generate_location_aliases, load_supported_locations
from ..normalizers import normalize_key


DEFAULT_COUNTRY_HINT = "Việt Nam"
DEFAULT_CITY_HINTS = (
    "Hồ Chí Minh, Việt Nam",
    "TP Hồ Chí Minh, Việt Nam",
    "Ho Chi Minh City, Vietnam",
)
DEFAULT_OSM_URL = "https://nominatim.openstreetmap.org/search"
DEFAULT_USER_AGENT = "travel_project_dev_contact_email"
CONTEXT_STOPWORDS = {
    "ho",
    "chi",
    "minh",
    "hcm",
    "tphcm",
    "tp",
    "city",
    "viet",
    "nam",
    "vietnam",
}
PLACE_STOPWORDS = {
    "gan",
    "quanh",
    "xung",
    "canh",
    "ke",
    "sat",
    "near",
    "around",
    "close",
    "to",
    "khu",
    "dia",
    "di",
    "du",
    "lich",
    "pho",
    "phuong",
    "duong",
    "street",
    "road",
    "place",
    "landmark",
    *CONTEXT_STOPWORDS,
}


@dataclass(frozen=True)
class GeocodeResult:
    success: bool
    query_used: str | None = None
    display_name: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    place_type: str | None = None
    confidence: float = 0.0
    provider: str = "osm"
    raw_payload: Any = None
    canonical_name: str | None = None
    normalized_name: str | None = None
    aliases: tuple[str, ...] = ()
    default_radius_km: float = 2.5
    source: str = "none"
    provider_place_id: str = ""
    address: dict[str, Any] | None = None
    map_area: str | None = None
    geocoder_queries: tuple[str, ...] = ()
    unresolved_reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["lat"] = self.latitude
        payload["lon"] = self.longitude
        payload["kind"] = self.place_type
        return payload


def geocode_place(
    location_phrase: str | None,
    city_hint: str | None = None,
    country_hint: str = DEFAULT_COUNTRY_HINT,
) -> GeocodeResult:
    phrase = clean_location_phrase(location_phrase)
    if not phrase:
        return GeocodeResult(
            success=False,
            provider=_provider(),
            unresolved_reason="empty_location_phrase",
        )

    queries = tuple(build_geocode_queries(phrase, city_hint=city_hint, country_hint=country_hint))
    if _cache_enabled():
        cached = get_cached_place_reference(phrase)
        if cached:
            return _result_from_cache(cached, queries)

    provider = _provider()
    if provider == "osm":
        result = _geocode_with_osm(phrase, queries)
    else:
        result = GeocodeResult(
            success=False,
            provider=provider,
            geocoder_queries=queries,
            unresolved_reason=f"unsupported_provider:{provider}",
        )

    if result.success and _cache_enabled():
        save_place_reference(result)
    return result


def clean_location_phrase(value: str | None) -> str:
    text = " ".join(str(value or "").replace("\n", " ").split())
    text = re.sub(r"^[,.;:\-\s]+|[,.;:\-\s]+$", "", text)
    text = re.sub(r"\b(?:khu vuc|khu vực|dia diem|địa điểm)\s+", "", text, flags=re.IGNORECASE)
    return text.strip()


def build_geocode_queries(
    location_phrase: str,
    *,
    city_hint: str | None = None,
    country_hint: str = DEFAULT_COUNTRY_HINT,
) -> list[str]:
    phrase = clean_location_phrase(location_phrase)
    if not phrase:
        return []

    queries: list[str] = []
    _append_unique(queries, f"{phrase}, {country_hint}")
    if city_hint:
        _append_unique(queries, f"{phrase}, {city_hint}")
    for hint in DEFAULT_CITY_HINTS:
        _append_unique(queries, f"{phrase}, {hint}")

    norm = normalize_key(phrase)
    if "cu chi" in norm or "dia dao" in norm:
        _append_unique(queries, f"{phrase}, Củ Chi, Hồ Chí Minh, Việt Nam")

    for alias in _english_aliases(norm):
        _append_unique(queries, alias)

    return queries


def get_cached_place_reference(location_phrase: str | None) -> dict[str, Any] | None:
    key = _normalized_place_name(location_phrase)
    if not key:
        return None

    try:
        from ..models import PlaceReference

        reference = PlaceReference.objects.filter(normalized_name=key).first()
        if reference is None:
            try:
                reference = PlaceReference.objects.filter(aliases__contains=[key]).first()
            except Exception:
                reference = next(
                    (
                        item
                        for item in PlaceReference.objects.all()
                        if key in {normalize_key(alias) for alias in (item.aliases or [])}
                    ),
                    None,
                )
    except Exception:
        return None

    if reference is None:
        return None
    return _reference_to_payload(reference)


def save_place_reference(result: GeocodeResult | dict[str, Any]) -> None:
    payload = result.to_dict() if isinstance(result, GeocodeResult) else dict(result)
    key = payload.get("normalized_name") or _normalized_place_name(payload.get("canonical_name"))
    lat = _float_or_none(payload.get("latitude") or payload.get("lat"))
    lon = _float_or_none(payload.get("longitude") or payload.get("lon"))
    if not key or lat is None or lon is None:
        return

    aliases = payload.get("aliases") or []
    if not isinstance(aliases, (list, tuple)):
        aliases = []

    try:
        from ..models import PlaceReference

        PlaceReference.objects.update_or_create(
            normalized_name=key,
            defaults={
                "canonical_name": payload.get("canonical_name") or payload.get("display_name") or key,
                "aliases": sorted({normalize_key(alias) for alias in aliases if normalize_key(alias)}),
                "kind": payload.get("place_type") or payload.get("kind") or "geocoded",
                "latitude": lat,
                "longitude": lon,
                "default_radius_km": float(payload.get("default_radius_km") or 2.5),
                "provider": payload.get("provider") or "osm",
                "source": payload.get("source") or payload.get("provider") or "osm",
                "confidence": float(payload.get("confidence") or 0.0),
                "provider_place_id": payload.get("provider_place_id") or "",
                "query": payload.get("query_used") or payload.get("query") or "",
                "display_name": payload.get("display_name") or "",
                "address": payload.get("address") or {},
                "raw_payload": payload.get("raw_payload") or {},
            },
        )
    except Exception:
        return


def _geocode_with_osm(phrase: str, queries: tuple[str, ...]) -> GeocodeResult:
    best: tuple[float, str, dict[str, Any]] | None = None
    raw_attempts: list[dict[str, Any]] = []

    for query in queries:
        try:
            rows = _fetch_osm(query)
        except Exception as exc:
            raw_attempts.append({"query": query, "error": str(exc)})
            continue
        raw_attempts.append({"query": query, "results": rows or []})
        for item in rows or []:
            score = _score_candidate(phrase, query, item)
            if score <= 0:
                continue
            if best is None or score > best[0]:
                best = (score, query, item)
        if best and best[0] >= 0.82:
            break

    if best is None:
        return GeocodeResult(
            success=False,
            provider="osm",
            raw_payload=raw_attempts,
            geocoder_queries=queries,
            unresolved_reason="no_geocoder_match",
        )

    score, query, item = best
    lat = _float_or_none(item.get("lat"))
    lon = _float_or_none(item.get("lon"))
    if lat is None or lon is None:
        return GeocodeResult(
            success=False,
            provider="osm",
            raw_payload=item,
            geocoder_queries=queries,
            unresolved_reason="missing_coordinates",
        )

    address = item.get("address") or {}
    place_type = item.get("type") or item.get("class") or "geocoded"
    canonical_name = _canonical_name(phrase, item)
    normalized_name = _normalized_place_name(phrase)
    aliases = _aliases_for_cache(phrase, canonical_name)

    return GeocodeResult(
        success=True,
        query_used=query,
        display_name=item.get("display_name") or canonical_name,
        latitude=lat,
        longitude=lon,
        place_type=place_type,
        confidence=round(min(score, 0.99), 3),
        provider="osm",
        raw_payload=item,
        canonical_name=canonical_name,
        normalized_name=normalized_name,
        aliases=aliases,
        default_radius_km=_default_radius_km(place_type, canonical_name, address),
        source="osm",
        provider_place_id=str(item.get("place_id") or item.get("osm_id") or ""),
        address=address,
        map_area=_area_from_address(address),
        geocoder_queries=queries,
    )


def _fetch_osm(query: str) -> list[dict[str, Any]]:
    url = os.getenv("OSM_NOMINATIM_URL", DEFAULT_OSM_URL)
    timeout = _timeout_seconds()
    headers = {"User-Agent": os.getenv("GEOCODER_USER_AGENT", DEFAULT_USER_AGENT)}
    response = requests.get(
        url,
        params={
            "q": query,
            "format": "json",
            "limit": 5,
            "addressdetails": 1,
        },
        headers=headers,
        timeout=timeout,
    )
    response.raise_for_status()
    data = response.json()
    return data if isinstance(data, list) else []


def _score_candidate(phrase: str, query: str, item: dict[str, Any]) -> float:
    haystack_parts = [item.get("display_name") or ""]
    address = item.get("address") or {}
    if isinstance(address, dict):
        haystack_parts.extend(str(value) for value in address.values() if value)
    haystack = normalize_key(" ".join(haystack_parts))

    phrase_tokens = _meaningful_tokens(phrase)
    query_tokens = _meaningful_tokens(_strip_context_from_query(query))
    token_sets = [tokens for tokens in (phrase_tokens, query_tokens) if tokens]
    if not token_sets:
        return 0.0

    ratios = []
    for tokens in token_sets:
        matched = sum(1 for token in tokens if token in haystack)
        ratios.append(matched / len(tokens))
    ratio = max(ratios)
    if ratio < 0.34:
        return 0.0

    try:
        importance = float(item.get("importance") or 0.0)
    except (TypeError, ValueError):
        importance = 0.0

    class_bonus = 0.08 if item.get("class") in {"tourism", "historic", "amenity", "leisure"} else 0.0
    return min(0.99, ratio * 0.76 + min(max(importance, 0.0), 1.0) * 0.16 + class_bonus)


def _english_aliases(norm_phrase: str) -> list[str]:
    aliases: list[str] = []
    compact = re.sub(r"\s+", " ", norm_phrase)
    if "cu chi" in compact or "dia dao" in compact:
        aliases.extend(
            [
                "Cu Chi Tunnels, Ho Chi Minh City, Vietnam",
                "Cu Chi Tunnel Historical Site, Ho Chi Minh City, Vietnam",
            ]
        )
    if "dinh doc lap" in compact or "doc lap" in compact:
        aliases.extend(
            [
                "Reunification Palace, Ho Chi Minh City, Vietnam",
                "Independence Palace, Ho Chi Minh City, Vietnam",
            ]
        )
    if "nguyen hue" in compact:
        aliases.extend(
            [
                "Nguyen Hue Walking Street, Ho Chi Minh City, Vietnam",
                "Nguyen Hue Street, District 1, Ho Chi Minh City, Vietnam",
            ]
        )
    return aliases


def _aliases_for_cache(phrase: str, canonical_name: str) -> tuple[str, ...]:
    aliases = {
        _normalized_place_name(phrase),
        _normalized_place_name(canonical_name),
        *generate_location_aliases(phrase),
        *generate_location_aliases(canonical_name),
    }
    aliases.update(normalize_key(alias) for alias in _english_aliases(normalize_key(phrase)))
    return tuple(sorted(alias for alias in aliases if alias))


def _reference_to_payload(reference) -> dict[str, Any]:
    address = reference.address or {}
    return {
        "canonical_name": reference.canonical_name,
        "normalized_name": reference.normalized_name,
        "aliases": list(reference.aliases or []),
        "place_type": reference.kind,
        "kind": reference.kind,
        "latitude": reference.latitude,
        "longitude": reference.longitude,
        "lat": reference.latitude,
        "lon": reference.longitude,
        "default_radius_km": reference.default_radius_km,
        "provider": reference.provider,
        "source": "cache",
        "provider_place_id": reference.provider_place_id,
        "query_used": reference.query,
        "query": reference.query,
        "display_name": reference.display_name or reference.canonical_name,
        "address": address,
        "raw_payload": reference.raw_payload or {},
        "confidence": reference.confidence,
        "map_area": _area_from_address(address),
    }


def _result_from_cache(payload: dict[str, Any], queries: tuple[str, ...]) -> GeocodeResult:
    return GeocodeResult(
        success=True,
        query_used=payload.get("query_used") or payload.get("query"),
        display_name=payload.get("display_name") or payload.get("canonical_name"),
        latitude=_float_or_none(payload.get("latitude") or payload.get("lat")),
        longitude=_float_or_none(payload.get("longitude") or payload.get("lon")),
        place_type=payload.get("place_type") or payload.get("kind"),
        confidence=float(payload.get("confidence") or 0.9),
        provider=payload.get("provider") or "osm",
        raw_payload=payload.get("raw_payload") or {},
        canonical_name=payload.get("canonical_name"),
        normalized_name=payload.get("normalized_name"),
        aliases=tuple(payload.get("aliases") or ()),
        default_radius_km=float(payload.get("default_radius_km") or 2.5),
        source="cache",
        provider_place_id=payload.get("provider_place_id") or "",
        address=payload.get("address") or {},
        map_area=payload.get("map_area"),
        geocoder_queries=queries,
    )


def _canonical_name(phrase: str, item: dict[str, Any]) -> str:
    display = str(item.get("display_name") or "").split(",")[0].strip()
    return display or phrase


def _default_radius_km(place_type: str | None, canonical_name: str | None, address: dict[str, Any]) -> float:
    type_key = normalize_key(place_type or "")
    name_key = normalize_key(canonical_name or "")
    address_key = normalize_key(" ".join(str(value) for value in (address or {}).values()))

    if "airport" in type_key or "aerodrome" in type_key or "san bay" in name_key:
        return 5.0
    if any(token in name_key or token in address_key for token in ("cu chi", "suoi tien")):
        return 8.0
    if type_key in {"administrative", "district", "suburb", "city", "town"}:
        return 8.0 if type_key != "city" else 15.0
    if type_key in {"road", "pedestrian", "residential", "footway"}:
        return 2.5
    if type_key in {"attraction", "museum", "monument", "yes"}:
        return 2.5
    return 2.5


def _area_from_address(address: dict[str, Any]) -> str | None:
    if not isinstance(address, dict):
        return None
    fields = ("city_district", "district", "borough", "suburb", "town", "city", "municipality", "state")
    for field in fields:
        value = address.get(field)
        area = _supported_area_from_text(str(value or ""))
        if area:
            return area
    return None


def _supported_area_from_text(value: str) -> str | None:
    key = normalize_key(value)
    if not key:
        return None
    for location in load_supported_locations():
        aliases = [location.get("canonical_name") or "", *(location.get("aliases") or [])]
        if any(normalize_key(alias) == key for alias in aliases):
            return location.get("canonical_name")
    return None


def _meaningful_tokens(text: str | None) -> list[str]:
    norm = normalize_key(text or "")
    tokens = re.findall(r"\w+", norm)
    output: list[str] = []
    for token in tokens:
        if token in PLACE_STOPWORDS:
            continue
        if token.isdigit() or len(token) > 2:
            output.append(token)
    return output


def _strip_context_from_query(query: str) -> str:
    text = re.split(r",", query, maxsplit=1)[0]
    return text.strip()


def _normalized_place_name(place_name: str | None) -> str:
    return normalize_key(clean_location_phrase(place_name))


def _append_unique(values: list[str], value: str) -> None:
    if value and value not in values:
        values.append(value)


def _provider() -> str:
    provider = os.getenv("GEOCODER_PROVIDER", "osm").strip().lower()
    if provider in {"osm", "nominatim", "osm_nominatim"}:
        return "osm"
    return provider or "osm"


def _cache_enabled() -> bool:
    return os.getenv("GEOCODER_CACHE_ENABLED", "true").strip().lower() not in {"0", "false", "no", "off"}


def _timeout_seconds() -> float:
    try:
        return float(os.getenv("GEOCODER_TIMEOUT_SECONDS", "8"))
    except (TypeError, ValueError):
        return 8.0


def _float_or_none(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
