from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Any
from urllib.parse import urlencode

from django.urls import reverse

from accommodations.models import Accommodation

from .models import PlaceReference
from .suggestion_catalog import (
    catalog_entries,
    catalog_label,
    catalog_search_stopwords,
    clear_suggestion_catalog_cache,
    compact_text,
    detect_nearby_poi,
    normalize_text,
    tokens,
)

try:
    from rapidfuzz import fuzz
except Exception:  # pragma: no cover - rapidfuzz is optional in local tools.
    fuzz = None


DEFAULT_LIMIT = 8
MIN_QUERY_LENGTH = 2
SUGGESTION_CACHE_SECONDS = 300


@dataclass(frozen=True)
class SuggestionCandidate:
    kind: str
    item_type: str
    label: str
    subtitle: str
    payload: dict[str, Any]
    aliases: tuple[str, ...] = ()
    source: str = "catalog"
    priority: int = 0
    popularity: float = 0.0
    object_id: int | None = None
    lat: float | None = None
    lon: float | None = None
    url: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


class SuggestionService:
    _cache: dict[str, Any] = {"expires_at": 0.0, "items": ()}

    @classmethod
    def suggest(cls, query: str | None, *, context: str = "chat", limit: int = DEFAULT_LIMIT) -> list[dict[str, Any]]:
        query_key = normalize_text(query)
        if not cls._is_searchable_query(query_key):
            return []

        scored: list[tuple[float, float, SuggestionCandidate, str]] = []
        query_tokens = tokens(query_key) - catalog_search_stopwords()
        forced_poi = detect_nearby_poi(query)
        if forced_poi:
            candidate = cls._poi_catalog_candidate(forced_poi, forced=True)
            scored.append((130.0, 100.0, candidate, forced_poi.get("matched_alias") or candidate.label))

        for item in cls._corpus():
            text_score, matched_alias = cls._best_text_score(query_key, query_tokens, item)
            if text_score < cls._minimum_score(query_key):
                continue
            rank = text_score + item.priority + min(item.popularity, 8.0) + cls._context_boost(context, item)
            scored.append((rank, text_score, item, matched_alias))

        scored.sort(key=lambda row: (row[0], row[1], row[2].priority, row[2].popularity), reverse=True)
        output: list[dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()
        for rank, text_score, item, matched_alias in scored:
            if normalize_text(item.label) == "smart suggestion":
                continue
            identity = (item.kind, str(item.object_id or item.payload.get("key") or item.label))
            if identity in seen:
                continue
            seen.add(identity)
            output.append(cls._serialize_item(item, rank, text_score, matched_alias))
            if len(output) >= limit:
                break
        return output

    @classmethod
    def clear_cache(cls) -> None:
        cls._cache["expires_at"] = 0.0
        cls._cache["items"] = ()
        clear_suggestion_catalog_cache()

    @classmethod
    def accommodation_by_id(cls, accommodation_id: Any) -> dict[str, Any] | None:
        try:
            accommodation = Accommodation.objects.get(pk=accommodation_id)
        except (Accommodation.DoesNotExist, ValueError, TypeError):
            return None
        candidate = cls._accommodation_candidate(accommodation)
        return cls._serialize_item(candidate, 100.0, 100.0, accommodation.name)

    @classmethod
    def _corpus(cls) -> tuple[SuggestionCandidate, ...]:
        now = time.monotonic()
        if cls._cache["expires_at"] > now:
            return cls._cache["items"]

        items: list[SuggestionCandidate] = []
        for entry in catalog_entries("locations"):
            items.append(cls._location_catalog_candidate(entry))
        for entry in catalog_entries("amenities"):
            items.append(cls._amenity_catalog_candidate(entry))
        for entry in catalog_entries("poi_keywords"):
            items.append(cls._poi_catalog_candidate(entry))
        for entry in catalog_entries("accommodation_types"):
            items.append(cls._accommodation_type_candidate(entry))

        accommodations = []
        try:
            accommodations = list(
                Accommodation.objects.only(
                    "id",
                    "name",
                    "accommodation_type",
                    "area",
                    "address",
                    "rating",
                    "review_count",
                    "latitude",
                    "longitude",
                )
            )
        except Exception:
            accommodations = []
        for accommodation in accommodations:
            items.append(cls._accommodation_candidate(accommodation))

        known_catalog_areas = {normalize_text(item.label) for item in items if item.item_type == "location"}
        for area in sorted({item.area for item in accommodations if item.area}):
            if normalize_text(area) not in known_catalog_areas:
                items.append(cls._area_candidate(area, source="accommodation_area"))

        try:
            for reference in PlaceReference.objects.all()[:200]:
                items.append(cls._cached_place_candidate(reference))
        except Exception:
            pass

        cls._cache["items"] = tuple(items)
        cls._cache["expires_at"] = now + SUGGESTION_CACHE_SECONDS
        return cls._cache["items"]

    @staticmethod
    def _location_catalog_candidate(entry: dict[str, Any]) -> SuggestionCandidate:
        label = str(entry.get("name") or "")
        parent = str(entry.get("parent") or "")
        aliases = tuple({label, entry.get("key") or "", *(entry.get("aliases") or [])})
        return SuggestionCandidate(
            kind="area",
            item_type="location",
            label=label,
            subtitle=parent or "Khu vực",
            payload={
                "key": entry.get("key"),
                "name": label,
                "area": label,
                "parent": parent or None,
                "location_mode": "area",
                "location_type": entry.get("type") or "location",
            },
            aliases=tuple(alias for alias in aliases if alias),
            source="catalog",
            priority=28,
        )

    @staticmethod
    def _area_candidate(area: str, *, source: str = "catalog") -> SuggestionCandidate:
        aliases = {area}
        norm = normalize_text(area)
        compact = norm.replace(" ", "")
        aliases.add(norm)
        aliases.add(compact)
        match = re.search(r"(?:quan|quận)\s*(\d+)", norm)
        if match:
            number = match.group(1)
            aliases.update({f"q{number}", f"q.{number}", f"quan {number}", f"quận {number}"})
        return SuggestionCandidate(
            kind="area",
            item_type="location",
            label=area,
            subtitle="Khu vực",
            payload={"area": area, "name": area, "location_mode": "area"},
            aliases=tuple(aliases),
            source=source,
            priority=22,
        )

    @staticmethod
    def _amenity_catalog_candidate(entry: dict[str, Any]) -> SuggestionCandidate:
        key = str(entry.get("key") or "")
        label = str(entry.get("name") or key)
        return SuggestionCandidate(
            kind="amenity",
            item_type="amenity",
            label=label,
            subtitle="Tiện nghi",
            payload={
                "key": key,
                "name": label,
                "amenity_key": key,
                "required_amenities": [key] if key else [],
            },
            aliases=tuple({label, key, *(entry.get("aliases") or [])}),
            source="catalog",
            priority=34,
        )

    @staticmethod
    def _poi_catalog_candidate(entry: dict[str, Any], *, forced: bool = False) -> SuggestionCandidate:
        key = str(entry.get("key") or "")
        label = str(entry.get("name") or key)
        return SuggestionCandidate(
            kind="poi_category",
            item_type="poi",
            label=label,
            subtitle="Loại địa điểm",
            payload={
                "key": key,
                "name": label,
                "poi_type": key,
                "poi_category": key,
                "nearby_place": label,
                "smart_kind": "poi_category",
            },
            aliases=tuple({label, key, *(entry.get("aliases") or [])}),
            source="catalog",
            priority=30 if forced else 18,
        )

    @staticmethod
    def _accommodation_type_candidate(entry: dict[str, Any]) -> SuggestionCandidate:
        key = str(entry.get("key") or "")
        label = str(entry.get("name") or key)
        return SuggestionCandidate(
            kind="accommodation_type",
            item_type="accommodation_type",
            label=label,
            subtitle="Loại chỗ ở",
            payload={"preferred_type": key, "accommodation_type": key, "accommodation_types": [key]},
            aliases=tuple({label, key, *(entry.get("aliases") or [])}),
            source="catalog",
            priority=12,
        )

    @staticmethod
    def _accommodation_candidate(accommodation: Accommodation) -> SuggestionCandidate:
        type_label = catalog_label("accommodation_type", accommodation.accommodation_type)
        subtitle = " · ".join(part for part in ("Chỗ ở", type_label, accommodation.area) if part)
        # NOTE: Do NOT include accommodation.address as an alias. Vietnamese addresses
        # contain common street/district tokens ("văn", "thị", "minh", "khai", "trần"...)
        # that cause rapidfuzz.partial_ratio to give spurious 80-90+ scores for
        # unrelated queries like "CGV Sư Vạn Hạnh" → "khách sạn ở Hoàng Văn Thụ".
        aliases = (
            accommodation.name,
            f"{accommodation.name} {type_label}",
            f"{type_label} {accommodation.name}",
            f"{accommodation.name} {accommodation.area}",
        )
        popularity = min(float(accommodation.review_count or 0) / 250, 5.0) + float(accommodation.rating or 0) / 2
        return SuggestionCandidate(
            kind="accommodation",
            item_type="accommodation",
            label=accommodation.name,
            subtitle=subtitle,
            payload={
                "selected_accommodation_id": accommodation.id,
                "destination": accommodation.name,
                "accommodation_type": accommodation.accommodation_type,
                "area": accommodation.area,
            },
            aliases=tuple(alias for alias in aliases if alias),
            source="db",
            priority=16,
            popularity=popularity,
            object_id=accommodation.id,
            lat=accommodation.latitude,
            lon=accommodation.longitude,
            url=f"{reverse('accommodation_detail', kwargs={'pk': accommodation.id})}",
        )

    @staticmethod
    def _cached_place_candidate(reference: PlaceReference) -> SuggestionCandidate:
        aliases = [reference.canonical_name, reference.display_name, reference.query_text, *(reference.aliases or [])]
        return SuggestionCandidate(
            kind="cached_poi",
            item_type="poi",
            label=reference.canonical_name,
            subtitle=reference.kind or "Địa điểm",
            payload={
                "selected_place": {
                    "name": reference.canonical_name,
                    "display_name": reference.display_name or reference.canonical_name,
                    "lat": reference.latitude,
                    "lon": reference.longitude,
                    "radius_km": reference.default_radius_km,
                    "kind": reference.kind,
                }
            },
            aliases=tuple(alias for alias in aliases if alias),
            source="place_cache",
            priority=20,
            popularity=float(reference.confidence or 0.0) * 4,
            object_id=reference.id,
            lat=reference.latitude,
            lon=reference.longitude,
        )

    @classmethod
    def _best_text_score(
        cls,
        query_key: str,
        query_tokens: set[str],
        item: SuggestionCandidate,
    ) -> tuple[float, str]:
        best_score = 0.0
        best_alias = item.label
        for alias in (item.label, *item.aliases):
            alias_key = normalize_text(alias)
            if not alias_key:
                continue
            score = cls._text_score(query_key, query_tokens, alias_key)
            if score > best_score:
                best_score = score
                best_alias = str(alias)
        return best_score, best_alias

    @staticmethod
    def _text_score(query_key: str, query_tokens: set[str], alias_key: str) -> float:
        if query_key == alias_key:
            return 100.0
        query_compact = compact_text(query_key)
        alias_compact = compact_text(alias_key)
        if query_compact and query_compact == alias_compact:
            return 98.0
        if alias_key.startswith(query_key):
            return 94.0
        if len(query_compact) >= 2 and alias_compact.startswith(query_compact):
            return 91.0
        if query_key.startswith(alias_key) and len(alias_key) >= 3:
            return 88.0
        if len(alias_key) >= 3 and alias_key in query_key:
            return 86.0
        if query_key in alias_key:
            return 82.0
        if len(query_compact) >= 4 and query_compact in alias_compact:
            return 80.0

        alias_tokens = tokens(alias_key)
        if query_tokens and alias_tokens:
            if alias_tokens.issubset(query_tokens):
                return 86.0
            coverage = len(query_tokens & alias_tokens) / len(query_tokens)
            if coverage >= 0.67:
                return 70.0 + coverage * 10

        if fuzz is not None and len(query_key) >= 3:
            return max(
                fuzz.WRatio(query_key, alias_key),
                fuzz.partial_ratio(query_key, alias_key) * 0.92,
            )

        if len(query_key) >= 3:
            return max(
                SequenceMatcher(None, query_key, alias_key).ratio() * 100,
                _partial_similarity(query_key, alias_key) * 92,
            )
        return 0.0

    @staticmethod
    def _serialize_item(
        item: SuggestionCandidate,
        rank: float,
        text_score: float,
        matched_alias: str,
    ) -> dict[str, Any]:
        score_percent = int(max(0, min(100, round(text_score))))
        score = round(score_percent / 100, 4)
        payload = dict(item.payload)
        output = {
            "id": f"{item.item_type}:{_slug(item.payload.get('key') or item.object_id or item.label)}",
            "label": item.label,
            "title": item.label,
            "subtitle": item.subtitle,
            "type": item.item_type,
            "kind": item.kind,
            "source": item.source,
            "score": score,
            "score_percent": score_percent,
            "text_score": round(text_score, 2),
            "matched_alias": matched_alias,
            "payload": payload,
        }
        if item.object_id is not None:
            output["object_id"] = item.object_id
        if item.lat is not None and item.lon is not None:
            output["lat"] = item.lat
            output["lon"] = item.lon
        if item.url:
            output["url"] = item.url
        output.update(item.extra)
        output["payload"]["smart_suggestion"] = {
            key: value
            for key, value in output.items()
            if key != "payload"
        }
        return output

    @staticmethod
    def _is_searchable_query(query_key: str) -> bool:
        if len(query_key.replace(" ", "")) >= MIN_QUERY_LENGTH:
            return True
        return bool(re.fullmatch(r"q\d+", query_key.replace(" ", "")))

    @staticmethod
    def _minimum_score(query_key: str) -> float:
        return 72.0 if len(query_key.replace(" ", "")) <= 3 else 62.0

    @staticmethod
    def _context_boost(context: str, item: SuggestionCandidate) -> float:
        context = (context or "chat").strip().lower()
        if context in {"home", "destination"} and item.item_type == "location":
            return 3.0
        if context in {"find_recommendation", "recommendation"} and item.item_type == "amenity":
            return 2.0
        return 0.0


def clear_suggestion_service_cache() -> None:
    SuggestionService.clear_cache()


def display_amenity_label(value: Any) -> str:
    return catalog_label("amenity", value)


def _partial_similarity(left: str, right: str) -> float:
    shorter, longer = (left, right) if len(left) <= len(right) else (right, left)
    if not shorter or not longer:
        return 0.0
    if shorter in longer:
        return 1.0
    window = len(shorter)
    best = 0.0
    for start in range(0, max(len(longer) - window + 1, 1)):
        sample = longer[start:start + window]
        best = max(best, SequenceMatcher(None, shorter, sample).ratio())
    return best


def _slug(value: Any) -> str:
    text = normalize_text(value)
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-") or "suggestion"


def accommodation_search_url(destination: str) -> str:
    return f"{reverse('accommodation_list')}?{urlencode({'destination': destination})}"
