from __future__ import annotations

import os
import re
from dataclasses import asdict, dataclass
from typing import Any

from ..geocoder.providers.base import GeocoderQuery
from ..geocoder.providers.nominatim import HCM_VIEWBOX, NominatimProvider
from ..geocoder.scorer import score_geocode_candidate
from ..geocoder.validator import geocode_category, rejected_geocoder_payload, validate_geocode_candidate
from ..location_phrase_cleaner import clean_location_candidate_phrase, cleaned_location_variants
from ..location_gazetteer import generate_location_aliases, load_supported_locations
from ..normalizers import normalize_key
from .place_cache import get_cached_place, save_place_cache
from .place_reference import alias_expansions, find_place_reference, fuzzy_search_place_reference, semantic_search_place_reference


DEFAULT_COUNTRY_HINT = "Việt Nam"
DEFAULT_CITY_HINTS = (
    "Hồ Chí Minh, Việt Nam",
    "Thành phố Hồ Chí Minh, Việt Nam",
    "TP Hồ Chí Minh, Việt Nam",
    "Ho Chi Minh City, Vietnam",
)
DEFAULT_OSM_URL = "https://nominatim.openstreetmap.org/search"
DEFAULT_USER_AGENT = "travel_project_dev_contact_email"
OSM_SAME_PLACE_CLUSTER_KM = 1.0
TRANSIT_PLACE_PREFIXES = (
    "ga ",
    "metro station ",
    "station ",
    "tram ",
)
TRANSIT_PLACE_CATEGORIES = {
    "bus_stop",
    "ferry_terminal",
    "platform",
    "public_transport",
    "station",
    "stop",
    "subway_entrance",
    "tram_stop",
}
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
    rejected_candidates: tuple[dict[str, Any], ...] = ()
    location_candidates: tuple[dict[str, Any], ...] = ()
    score_breakdown: dict[str, Any] | None = None
    result_margin: float | None = None

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
    intent = _geocoder_intent_for_phrase(phrase)
    if _cache_enabled():
        cached = get_cached_place_reference(phrase)
        if cached and validate_geocode_candidate(cached, query=phrase, intent=intent).accepted:
            return _result_from_cache(cached, queries)

    reference = find_place_reference(phrase)
    if reference and validate_geocode_candidate(reference, query=phrase, intent=intent).accepted:
        return _result_from_cache({**reference, "source": reference.get("source") or "place_reference"}, queries)

    semantic = semantic_search_place_reference(phrase)
    if semantic and validate_geocode_candidate(semantic, query=phrase, intent=intent).accepted:
        return _result_from_cache({**semantic, "source": "semantic", "provider": "semantic"}, queries)

    fuzzy = fuzzy_search_place_reference(phrase)
    if fuzzy and validate_geocode_candidate(fuzzy, query=phrase, intent=intent).accepted:
        return _result_from_cache({**fuzzy, "source": "fuzzy", "provider": fuzzy.get("provider") or "fuzzy"}, queries)

    result = _geocode_with_configured_providers(phrase, queries, intent=intent)
    if not result.success:
        result = _geocode_with_osm(phrase, queries, intent=intent)

    if result.success and _cache_enabled():
        save_place_reference(result)
    return result


def clean_location_phrase(value: str | None) -> str:
    return clean_location_candidate_phrase(value)


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
    phrase_variants = cleaned_location_variants(phrase) or [phrase]
    for variant in phrase_variants:
        if city_hint:
            _append_unique(queries, f"{variant}, {city_hint}")
        for hint in DEFAULT_CITY_HINTS:
            _append_unique(queries, f"{variant}, {hint}")

        norm = normalize_key(variant)
        if "cu chi" in norm or "dia dao" in norm:
            _append_unique(queries, f"{variant}, Củ Chi, Hồ Chí Minh, Việt Nam")

        for alias in _english_aliases(norm):
            _append_unique(queries, alias)

    return queries


def get_cached_place_reference(location_phrase: str | None) -> dict[str, Any] | None:
    return get_cached_place(location_phrase)


def save_place_reference(result: GeocodeResult | dict[str, Any]) -> None:
    payload = result.to_dict() if isinstance(result, GeocodeResult) else dict(result)
    query = payload.get("query_text") or payload.get("normalized_name") or payload.get("query_used") or payload.get("query")
    save_place_cache(query, payload)


def _geocode_with_configured_providers(phrase: str, queries: tuple[str, ...], *, intent: str) -> GeocodeResult:
    raw_attempts: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for provider_name, search in _provider_searches():
        try:
            rows = search(phrase)
        except Exception as exc:
            raw_attempts.append({"provider": provider_name, "query": phrase, "error": str(exc)})
            continue
        raw_attempts.append({"provider": provider_name, "query": phrase, "results": rows or []})
        if not rows:
            continue
        result = _result_from_provider_candidates(
            phrase,
            rows,
            provider=provider_name,
            queries=queries,
            rejected=rejected,
            intent=intent,
        )
        if result.success:
            return result
        rejected.extend(result.rejected_candidates)
    return GeocodeResult(
        success=False,
        provider="provider_chain",
        raw_payload=raw_attempts,
        geocoder_queries=queries,
        unresolved_reason="no_provider_match",
        rejected_candidates=tuple(rejected[:10]),
    )


def _geocode_with_osm(phrase: str, queries: tuple[str, ...], *, intent: str | None = None) -> GeocodeResult:
    scored: list[tuple[float, str, dict[str, Any], dict[str, Any]]] = []
    raw_attempts: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    intent = intent or _geocoder_intent_for_phrase(phrase)

    for query in queries:
        try:
            rows = _fetch_osm(query)
        except Exception as exc:
            raw_attempts.append({"query": query, "error": str(exc)})
            continue
        raw_attempts.append({"query": query, "results": rows or []})
        for item in rows or []:
            validation = validate_geocode_candidate(item, query=phrase, intent=intent)
            score_payload = score_geocode_candidate(phrase, item, validation=validation)
            score = score_payload.total
            if not validation.accepted:
                rejected.append(
                    rejected_geocoder_payload(
                        item,
                        reason=validation.reason,
                        validation=validation,
                        score=score,
                    )
                )
                continue
            if score < 0.70:
                rejected.append(
                    rejected_geocoder_payload(
                        item,
                        reason="low_score",
                        validation=validation,
                        score=score,
                    )
                )
                continue
            scored.append((score, query, item, score_payload.to_dict()))
        scored = _dedupe_osm_scored_candidates(scored)
        if scored and scored[0][0] >= 0.82 and _top_margin(scored) >= 0.08:
            break

    if not scored:
        return GeocodeResult(
            success=False,
            provider="osm",
            raw_payload=raw_attempts,
            geocoder_queries=queries,
            unresolved_reason="no_geocoder_match",
            rejected_candidates=tuple(rejected[:10]),
        )

    scored = _dedupe_osm_scored_candidates(scored)
    margin = _top_margin(scored)
    top_validation = validate_geocode_candidate(
        scored[0][2],
        query=phrase,
        intent=intent,
        top_score=scored[0][0],
        runner_up_score=scored[1][0] if len(scored) > 1 else None,
    )
    if len(scored) > 1 and (margin < 0.08 or not top_validation.accepted):
        return GeocodeResult(
            success=False,
            provider="osm",
            raw_payload=raw_attempts,
            geocoder_queries=queries,
            unresolved_reason="ambiguous_geocoder_match" if margin < 0.08 else top_validation.reason,
            rejected_candidates=tuple(
                [
                    *rejected[:8],
                    rejected_geocoder_payload(scored[0][2], reason=top_validation.reason, validation=top_validation, score=scored[0][0]),
                    rejected_geocoder_payload(scored[1][2], reason="top1_top2_margin_too_small", score=scored[1][0])
                    if len(scored) > 1
                    else {},
                ]
            ),
            location_candidates=tuple(_location_candidate_payload(candidate, index + 1) for index, candidate in enumerate(scored[:5])),
            result_margin=round(margin, 3) if margin is not None else None,
        )

    score, query, item, score_breakdown = scored[0]
    lat = _float_or_none(item.get("lat"))
    lon = _float_or_none(item.get("lon"))
    if lat is None or lon is None:
        return GeocodeResult(
            success=False,
            provider="osm",
            raw_payload=item,
            geocoder_queries=queries,
            unresolved_reason="missing_coordinates",
            rejected_candidates=tuple(rejected[:10]),
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
        rejected_candidates=tuple(rejected[:10]),
        score_breakdown=score_breakdown,
        result_margin=round(margin, 3) if margin is not None else None,
    )


def _dedupe_osm_scored_candidates(
    scored: list[tuple[float, str, dict[str, Any], dict[str, Any]]],
) -> list[tuple[float, str, dict[str, Any], dict[str, Any]]]:
    unique: list[tuple[float, str, dict[str, Any], dict[str, Any]]] = []
    for candidate in scored:
        existing_index = next(
            (
                index
                for index, existing in enumerate(unique)
                if _osm_candidate_identity(candidate[2]) == _osm_candidate_identity(existing[2])
                or _is_same_osm_place_cluster(candidate[2], existing[2])
            ),
            None,
        )
        if existing_index is None:
            unique.append(candidate)
        elif _should_replace_equivalent_osm_candidate(unique[existing_index], candidate):
            unique[existing_index] = candidate
    return sorted(unique, key=lambda candidate: candidate[0], reverse=True)


def _should_replace_equivalent_osm_candidate(
    current: tuple[float, str, dict[str, Any], dict[str, Any]],
    challenger: tuple[float, str, dict[str, Any], dict[str, Any]],
) -> bool:
    current_score, challenger_score = current[0], challenger[0]
    current_priority = _osm_candidate_kind_priority(current[2])
    challenger_priority = _osm_candidate_kind_priority(challenger[2])
    if current_priority != challenger_priority and abs(challenger_score - current_score) < 0.08:
        return challenger_priority > current_priority
    return challenger_score > current_score


def _osm_candidate_kind_priority(item: dict[str, Any]) -> int:
    category = geocode_category(item)
    if category in TRANSIT_PLACE_CATEGORIES:
        return 0
    if category in {"highway", "road"}:
        return 1
    return 2


def _location_candidate_payload(
    candidate: tuple[float, str, dict[str, Any], dict[str, Any]],
    rank: int,
) -> dict[str, Any]:
    score, query, item, score_breakdown = candidate
    address = item.get("address") or {}
    name = _canonical_name("", item)
    display_name = item.get("display_name") or name
    place_type = item.get("type") or item.get("class") or "geocoded"
    lat = _float_or_none(item.get("lat"))
    lon = _float_or_none(item.get("lon"))
    selected_place = {
        "name": name,
        "display_name": display_name,
        "kind": place_type,
        "lat": lat,
        "lon": lon,
        "default_radius_km": _default_radius_km(place_type, name, address),
        "source": "osm",
        "provider": "osm",
        "provider_place_id": str(item.get("place_id") or item.get("osm_id") or ""),
        "query": query,
        "geocoder_queries": [query],
        "address": address,
        "map_area": _area_from_address(address),
        "confidence": round(min(score, 0.99), 3),
        "score_breakdown": score_breakdown,
    }
    return {
        "id": f"osm:{item.get('place_id') or item.get('osm_id') or rank}",
        "rank": rank,
        "name": name,
        "canonical_area": name,
        "kind": place_type,
        "address": _candidate_address_label(item),
        "display_name": display_name,
        "confidence": round(min(score, 0.99), 3),
        "source": "osm",
        "payload": {
            "location_mode": "near_anchor",
            "location_phrase": name,
            "area": None,
            "selected_place": selected_place,
        },
    }


def _candidate_address_label(item: dict[str, Any]) -> str:
    address = item.get("address") or {}
    if isinstance(address, dict):
        parts = [
            address.get("house_number"),
            address.get("road"),
            address.get("suburb") or address.get("city_district") or address.get("district"),
            address.get("city") or address.get("state"),
            address.get("country"),
        ]
        label = ", ".join(str(part) for part in parts if part)
        if label:
            return label
    display_parts = [part.strip() for part in str(item.get("display_name") or "").split(",")]
    return ", ".join(display_parts[1:]) if len(display_parts) > 1 else str(item.get("display_name") or "")


def _osm_candidate_identity(item: dict[str, Any]) -> str:
    osm_type = item.get("osm_type")
    osm_id = item.get("osm_id")
    if osm_type and osm_id:
        return f"osm:{osm_type}:{osm_id}"

    lat = _float_or_none(item.get("lat"))
    lon = _float_or_none(item.get("lon"))
    if lat is not None and lon is not None:
        name = normalize_key(str(item.get("name") or str(item.get("display_name") or "").split(",")[0]))
        return f"geo:{name}:{round(lat, 5)}:{round(lon, 5)}"

    return f"place:{item.get('place_id') or id(item)}"


def _is_same_osm_place_cluster(left: dict[str, Any], right: dict[str, Any]) -> bool:
    left_names = set(_normalized_osm_place_head_variants(left))
    right_names = set(_normalized_osm_place_head_variants(right))
    if not left_names or not right_names:
        return False
    if left_names.isdisjoint(right_names) and not _osm_place_names_overlap(left_names, right_names):
        return False
    left_lat = _float_or_none(left.get("lat"))
    left_lon = _float_or_none(left.get("lon"))
    right_lat = _float_or_none(right.get("lat"))
    right_lon = _float_or_none(right.get("lon"))
    if None in {left_lat, left_lon, right_lat, right_lon}:
        return False
    return _approx_distance_km(left_lat, left_lon, right_lat, right_lon) <= OSM_SAME_PLACE_CLUSTER_KM


def _osm_place_names_overlap(left_names: set[str], right_names: set[str]) -> bool:
    for left in left_names:
        left_tokens = set(_meaningful_tokens(left))
        if not left_tokens:
            continue
        for right in right_names:
            right_tokens = set(_meaningful_tokens(right))
            if not right_tokens:
                continue
            overlap = len(left_tokens & right_tokens)
            smaller = min(len(left_tokens), len(right_tokens))
            if smaller and overlap / smaller >= 0.67:
                return True
    return False


def _normalized_osm_place_head(item: dict[str, Any]) -> str:
    head = item.get("name") or str(item.get("display_name") or "").split(",")[0]
    return normalize_key(str(head or ""))


def _normalized_osm_place_head_variants(item: dict[str, Any]) -> tuple[str, ...]:
    head = _normalized_osm_place_head(item)
    if not head:
        return ()
    variants = [head]
    for prefix in TRANSIT_PLACE_PREFIXES:
        if head.startswith(prefix):
            stripped = head[len(prefix) :].strip()
            if stripped:
                variants.append(stripped)
    return tuple(dict.fromkeys(variants))


def _approx_distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    lat_km = (float(lat1) - float(lat2)) * 111.0
    lon_km = (float(lon1) - float(lon2)) * 109.0
    return ((lat_km * lat_km) + (lon_km * lon_km)) ** 0.5


def _fetch_osm(query: str) -> list[dict[str, Any]]:
    return NominatimProvider().search(
        GeocoderQuery(
            text=query,
            viewbox=HCM_VIEWBOX,
            bounded=True,
            limit=5,
        )
    )


def _provider_searches():
    try:
        from ..geocoder.providers import geoapify

        yield "geoapify", geoapify.search_place
    except Exception:
        pass
    try:
        from ..geocoder.providers import foursquare

        yield "foursquare", foursquare.search_place
    except Exception:
        pass


def _result_from_provider_candidates(
    phrase: str,
    rows: list[dict[str, Any]],
    *,
    provider: str,
    queries: tuple[str, ...],
    rejected: list[dict[str, Any]],
    intent: str,
) -> GeocodeResult:
    scored: list[tuple[float, dict[str, Any], dict[str, Any], dict[str, Any]]] = []
    for item in rows:
        validation = validate_geocode_candidate(item, query=phrase, intent=intent)
        score_payload = score_geocode_candidate(phrase, item, validation=validation)
        score = max(score_payload.total, min(float(item.get("confidence") or 0.0), 0.99))
        if not validation.accepted:
            rejected.append(rejected_geocoder_payload(item, reason=validation.reason, validation=validation, score=score))
            continue
        if score < 0.70:
            rejected.append(rejected_geocoder_payload(item, reason="low_score", validation=validation, score=score))
            continue
        scored.append((score, item, score_payload.to_dict(), validation.to_dict()))
    scored.sort(key=lambda candidate: candidate[0], reverse=True)
    if not scored:
        return GeocodeResult(success=False, provider=provider, geocoder_queries=queries, unresolved_reason="no_provider_match")
    margin = _top_margin_provider(scored)
    top_validation = validate_geocode_candidate(
        scored[0][1],
        query=phrase,
        intent=intent,
        top_score=scored[0][0],
        runner_up_score=scored[1][0] if len(scored) > 1 else None,
    )
    if not top_validation.accepted:
        return GeocodeResult(
            success=False,
            provider=provider,
            geocoder_queries=queries,
            unresolved_reason=top_validation.reason,
            rejected_candidates=(
                rejected_geocoder_payload(scored[0][1], reason=top_validation.reason, validation=top_validation, score=scored[0][0]),
            ),
        )
    score, item, score_breakdown, _validation_dict = scored[0]
    lat = _float_or_none(item.get("lat") if item.get("lat") is not None else item.get("latitude"))
    lon = _float_or_none(item.get("lon") if item.get("lon") is not None else item.get("lng"))
    if lat is None or lon is None:
        return GeocodeResult(success=False, provider=provider, geocoder_queries=queries, unresolved_reason="missing_coordinates")
    address = item.get("address") or {}
    place_type = item.get("kind") or item.get("place_type") or item.get("type") or "geocoded"
    canonical_name = item.get("canonical_name") or item.get("name") or str(item.get("display_name") or "").split(",")[0].strip() or phrase
    return GeocodeResult(
        success=True,
        query_used=phrase,
        display_name=item.get("display_name") or canonical_name,
        latitude=lat,
        longitude=lon,
        place_type=place_type,
        confidence=round(min(score, 0.99), 3),
        provider=provider,
        raw_payload=item.get("raw_payload") or item.get("raw") or item,
        canonical_name=canonical_name,
        normalized_name=_normalized_place_name(canonical_name),
        aliases=_aliases_for_cache(phrase, canonical_name),
        default_radius_km=_default_radius_km(place_type, canonical_name, address),
        source=provider,
        provider_place_id=str(item.get("provider_place_id") or ""),
        address=address,
        map_area=_area_from_address(address),
        geocoder_queries=queries,
        rejected_candidates=tuple(rejected[:10]),
        score_breakdown=score_breakdown,
        result_margin=round(margin, 3) if margin is not None else None,
    )


def _score_candidate(phrase: str, query: str, item: dict[str, Any]) -> float:
    validation = validate_geocode_candidate(item)
    if not validation.accepted:
        return 0.0
    return score_geocode_candidate(_strip_context_from_query(query) or phrase, item, validation=validation).total


def _top_margin(scored: list[tuple[float, str, dict[str, Any], dict[str, Any]]]) -> float:
    if not scored:
        return 0.0
    if len(scored) == 1:
        return 1.0
    return round(scored[0][0] - scored[1][0], 3)


def _top_margin_provider(scored: list[tuple[float, dict[str, Any], dict[str, Any], dict[str, Any]]]) -> float:
    if not scored:
        return 0.0
    if len(scored) == 1:
        return 1.0
    return round(scored[0][0] - scored[1][0], 3)


def _english_aliases(norm_phrase: str) -> list[str]:
    aliases = alias_expansions(norm_phrase)
    if "nguyen hue" in re.sub(r"\s+", " ", norm_phrase):
        aliases.extend(["nguyen hue walking street", "nguyen hue street"])
    return [f"{alias.title()}, Ho Chi Minh City, Vietnam" for alias in dict.fromkeys(aliases)]


def _aliases_for_cache(phrase: str, canonical_name: str) -> tuple[str, ...]:
    aliases = {
        _normalized_place_name(phrase),
        _normalized_place_name(canonical_name),
        *generate_location_aliases(phrase),
        *generate_location_aliases(canonical_name),
        *alias_expansions(phrase),
        *alias_expansions(canonical_name),
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


def _geocoder_intent_for_phrase(phrase: str | None) -> str:
    norm = normalize_key(phrase or "")
    if "san bay" in norm or "airport" in norm:
        return "airport"
    if "dai hoc" in norm or "truong" in norm:
        return "university"
    if any(token in norm for token in ("khach san", "hotel", "can ho", "homestay", "hostel")):
        return "lodging"
    if any(token in norm for token in ("cafe", "ca phe", "nha hang", "quan an", "restaurant")):
        return "food"
    return "landmark"


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
