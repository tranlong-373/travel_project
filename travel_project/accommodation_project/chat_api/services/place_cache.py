from __future__ import annotations

from typing import Any

from django.utils import timezone

from ..geocoder.validator import validate_geocode_candidate
from .place_reference import generate_place_aliases, normalize_place_text, reference_to_payload


MIN_CACHE_CONFIDENCE = 0.75


def get_cached_place(query: str | None) -> dict[str, Any] | None:
    key = normalize_place_text(query)
    if not key:
        return None
    try:
        from ..models import PlaceReference

        reference = (
            PlaceReference.objects.filter(normalized_query=key).first()
            or PlaceReference.objects.filter(normalized_name=key).first()
        )
        if reference is None:
            try:
                reference = PlaceReference.objects.filter(aliases__contains=[key]).first()
            except Exception:
                reference = None
        if reference is None:
            reference = next(
                (
                    item
                    for item in PlaceReference.objects.all()
                    if key in {normalize_place_text(alias) for alias in (item.aliases or [])}
                ),
                None,
            )
        if reference is None:
            return None
        reference.last_used_at = timezone.now()
        reference.save(update_fields=["last_used_at", "updated_at"])
        payload = reference_to_payload(reference, source="cache")
        payload["cache_hit"] = True
        return payload
    except Exception:
        return None


def save_place_cache(query: str | None, candidate: dict[str, Any] | None) -> dict[str, Any] | None:
    candidate = candidate or {}
    confidence = _float(candidate.get("confidence"))
    if confidence < MIN_CACHE_CONFIDENCE:
        return None
    validation = validate_geocode_candidate(candidate, query=query)
    if not validation.accepted:
        return None

    normalized_query = normalize_place_text(query)
    canonical_name = (
        candidate.get("canonical_name")
        or candidate.get("name")
        or str(candidate.get("display_name") or "").split(",")[0].strip()
        or query
    )
    normalized_name = normalize_place_text(canonical_name)
    lat = _float(candidate.get("lat") if candidate.get("lat") is not None else candidate.get("latitude"))
    lon = _float(candidate.get("lon") if candidate.get("lon") is not None else candidate.get("longitude"))
    if not normalized_name or lat is None or lon is None:
        return None

    aliases = set(generate_place_aliases(query))
    aliases.update(generate_place_aliases(canonical_name))
    raw_aliases = candidate.get("aliases") or []
    if isinstance(raw_aliases, (list, tuple, set)):
        aliases.update(normalize_place_text(alias) for alias in raw_aliases)
    aliases = {alias for alias in aliases if alias}

    address = candidate.get("address") or {}
    if not isinstance(address, dict):
        address = {}

    try:
        from ..models import PlaceReference

        existing = PlaceReference.objects.filter(normalized_name=normalized_name).first()
        now = timezone.now()
        defaults = {
            "query_text": str(query or candidate.get("query") or "")[:300],
            "normalized_query": normalized_query,
            "canonical_name": str(canonical_name)[:200],
            "aliases": sorted(aliases),
            "kind": str(candidate.get("kind") or candidate.get("place_type") or "geocoded")[:50],
            "latitude": lat,
            "longitude": lon,
            "default_radius_km": float(candidate.get("default_radius_km") or 2.5),
            "district": str(candidate.get("district") or _address_value(address, "city_district", "district", "suburb"))[:120],
            "city": str(candidate.get("city") or _address_value(address, "city", "municipality", "state"))[:120],
            "country": str(candidate.get("country") or _address_value(address, "country"))[:120],
            "provider": str(candidate.get("provider") or "unknown")[:50],
            "source": str(candidate.get("source") or candidate.get("provider") or "cache")[:50],
            "confidence": confidence,
            "provider_place_id": str(candidate.get("provider_place_id") or "")[:120],
            "query": str(candidate.get("query") or candidate.get("query_used") or query or "")[:300],
            "display_name": str(candidate.get("display_name") or canonical_name)[:500],
            "address": address,
            "raw_payload": candidate.get("raw_payload") or candidate.get("raw") or {},
            "last_used_at": now,
        }
        if existing and float(existing.confidence or 0.0) > confidence:
            merged_aliases = sorted({*(existing.aliases or []), *aliases})
            existing.aliases = merged_aliases
            existing.query_text = existing.query_text or defaults["query_text"]
            existing.normalized_query = existing.normalized_query or normalized_query
            existing.last_used_at = now
            existing.save(update_fields=["aliases", "query_text", "normalized_query", "last_used_at", "updated_at"])
            return reference_to_payload(existing, source="cache")

        reference, _created = PlaceReference.objects.update_or_create(
            normalized_name=normalized_name,
            defaults=defaults,
        )
        return reference_to_payload(reference, source="cache")
    except Exception:
        return None


def _address_value(address: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = address.get(key)
        if value:
            return str(value)
    return ""


def _float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
