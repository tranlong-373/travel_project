from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Any
from urllib.parse import urlencode

from django.urls import reverse

from accommodations.models import Accommodation
from OpenStreetMap_API.constants import POI_TYPES

from .models import PlaceReference
from .normalizers import normalize_common_typos, normalize_key

try:
    from rapidfuzz import fuzz
except Exception:  # pragma: no cover - rapidfuzz is optional in local tools.
    fuzz = None


MAX_SUGGESTIONS = 8
MIN_QUERY_LENGTH = 2
SUGGESTION_CACHE_SECONDS = 300
ACCOMMODATION_CONFIDENCE = 84
ACCOMMODATION_MARGIN = 6

TYPE_LABELS = {
    "hotel": "Khách sạn",
    "homestay": "Homestay",
    "hostel": "Hostel",
    "apartment": "Căn hộ",
}
TYPE_ALIASES = {
    "hotel": ("khach san", "khách sạn", "ks", "hotel"),
    "homestay": ("homestay", "home stay", "homstay", "homestate", "honestay"),
    "hostel": ("hostel", "nha tro", "nhà trọ", "tro", "trọ"),
    "apartment": ("can ho", "căn hộ", "chung cu", "chung cư", "apartment", "studio", "serviced apartment"),
}
POI_ALIASES = {
    "restaurant": ("nha hang", "nhà hàng", "quan an", "quán ăn", "restaurant", "food"),
    "cafe": ("cafe", "ca phe", "cà phê", "coffee", "quan ca phe", "quán cà phê", "highlands"),
    "hospital": ("benh vien", "bệnh viện", "hospital", "clinic", "phong kham", "phòng khám"),
    "pharmacy": ("nha thuoc", "nhà thuốc", "hieu thuoc", "hiệu thuốc", "pharmacy"),
    "supermarket": ("sieu thi", "siêu thị", "supermarket", "mart", "circle k", "mini mart"),
    "atm": ("atm", "cay atm", "cây atm", "rut tien", "rút tiền"),
    "tourist_attraction": ("diem du lich", "điểm du lịch", "bao tang", "bảo tàng", "tourist", "attraction"),
    "bar": ("bar", "quan bar", "quán bar", "pub"),
    "park": ("cong vien", "công viên", "park"),
    "bank": ("ngan hang", "ngân hàng", "bank"),
    "gas_station": ("tram xang", "trạm xăng", "cay xang", "cây xăng", "gas station"),
}
STOPWORDS = {
    "tim",
    "kiem",
    "goi",
    "y",
    "cho",
    "o",
    "gan",
    "quanh",
    "xung",
    "canh",
    "ke",
    "sat",
    "near",
    "around",
    "minh",
    "toi",
    "tui",
    "em",
    "anh",
    "chi",
    "muon",
    "can",
    "thue",
    "dat",
    "book",
    "booking",
}


@dataclass(frozen=True)
class SuggestionItem:
    kind: str
    title: str
    subtitle: str
    payload: dict[str, Any]
    aliases: tuple[str, ...] = ()
    priority: int = 0
    popularity: float = 0.0
    object_id: int | None = None
    lat: float | None = None
    lon: float | None = None
    url: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


_CORPUS_CACHE: dict[str, Any] = {"expires_at": 0.0, "items": ()}


def clear_suggestion_cache() -> None:
    _CORPUS_CACHE["expires_at"] = 0.0
    _CORPUS_CACHE["items"] = ()


def suggest_places(query: str | None, *, limit: int = MAX_SUGGESTIONS) -> list[dict[str, Any]]:
    query_key = _normalize(query)
    if not _is_searchable_query(query_key):
        return []

    scored: list[tuple[float, float, SuggestionItem, str]] = []
    query_tokens = _meaningful_tokens(query_key)
    for item in _suggestion_corpus():
        text_score, matched_alias = _best_text_score(query_key, query_tokens, item)
        if text_score < _minimum_score(query_key):
            continue
        rank = text_score + item.priority + min(item.popularity, 8.0)
        scored.append((rank, text_score, item, matched_alias))

    scored.sort(key=lambda row: (row[0], row[1], row[2].priority, row[2].popularity), reverse=True)

    output: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for rank, text_score, item, matched_alias in scored:
        identity = (item.kind, str(item.object_id or item.title))
        if identity in seen:
            continue
        seen.add(identity)
        output.append(_serialize_item(item, rank, text_score, matched_alias))
        if len(output) >= limit:
            break
    return output


def best_submit_resolution(text: str | None) -> dict[str, Any] | None:
    suggestions = suggest_places(text, limit=5)
    if not suggestions:
        return None
    top = suggestions[0]
    second_score = suggestions[1]["score"] if len(suggestions) > 1 else 0
    if (
        top["kind"] == "accommodation"
        and top["score"] >= ACCOMMODATION_CONFIDENCE
        and (
            top["score"] - second_score >= ACCOMMODATION_MARGIN
            or not _has_strong_place_competitor(top, suggestions[1:])
        )
    ):
        return {"type": "accommodation", "suggestion": top, "suggestions": suggestions}

    for suggestion in suggestions:
        if _is_poi_category_clarification(text, suggestion, suggestions):
            return {"type": "poi_category_clarification", "suggestion": suggestion, "suggestions": suggestions}

    return None


def selected_accommodation_result(suggestion: dict[str, Any]) -> dict[str, Any]:
    payload = suggestion.get("payload") or {}
    accommodation_type = payload.get("accommodation_type")
    area = payload.get("area")
    destination = payload.get("destination") or suggestion.get("title")
    url = _accommodation_search_url(str(destination or ""))
    slots = {
        "area": area,
        "budget": None,
        "guest_count": None,
        "preferred_type": accommodation_type,
        "accommodation_type": accommodation_type,
        "accommodation_types": [accommodation_type] if accommodation_type else [],
        "required_amenities": [],
        "priorities": [],
        "special_requirements": [],
        "trip_days": None,
        "room_count": None,
        "rating": None,
        "check_in": None,
        "check_out": None,
        "location_phrase": destination,
        "location_mode": "area" if area else "unknown",
    }
    return {
        "schema_version": "2.0",
        "intent": "recommend_accommodation",
        "conversation_intent": "recommend_accommodation",
        "slots": slots,
        "raw_text": destination,
        "parser_mode": "smart_suggestion_accommodation",
        "location_status": "ok" if area else "unresolved",
        "location_candidates": [],
        "canonical_area": area,
        "location_confidence": 1.0,
        "location_source": "smart_suggestion_accommodation",
        "location_mode": slots["location_mode"],
        "location_phrase": destination,
        "matched_text": destination,
        "accommodation_type": accommodation_type,
        "accommodation_types": slots["accommodation_types"],
        "ready_for_recommendation": True,
        "can_show_recommendations": True,
        "recommendation_level": "partial",
        "missing_slots": [],
        "suggested_questions": [],
        "follow_up_question": None,
        "awaiting_confirmation": False,
        "confirmation_required": False,
        "confirmation_heading": "Tìm thấy chỗ ở",
        "polite_bot_message": f"Mình tìm thấy {destination}. Bạn có thể mở danh sách đang lọc theo tên này.",
        "bot_message": f"Mình tìm thấy {destination}. Bạn có thể mở danh sách đang lọc theo tên này.",
        "confirm_table": [
            {
                "key": "selected_accommodation",
                "label": "Chỗ ở",
                "value": destination,
                "display_value": suggestion.get("subtitle") or destination,
            }
        ],
        "recommendation_url": url,
        "recommendation_action": {
            "visible": True,
            "enabled": True,
            "eligible": True,
            "requires_submit": False,
            "pref_id": None,
            "url": url,
            "reason": "selected_accommodation",
        },
        "smart_suggestion": suggestion,
        "usable_filters": ["accommodation_name"],
    }


def poi_category_clarification_result(text: str | None, suggestion: dict[str, Any]) -> dict[str, Any]:
    title = suggestion.get("title") or "địa điểm"
    payload = suggestion.get("payload") or {}
    return {
        "schema_version": "2.0",
        "intent": "recommend_accommodation",
        "conversation_intent": "recommend_accommodation",
        "slots": {
            "area": None,
            "budget": None,
            "guest_count": None,
            "preferred_type": payload.get("accommodation_type"),
            "accommodation_type": payload.get("accommodation_type"),
            "accommodation_types": [payload["accommodation_type"]] if payload.get("accommodation_type") else [],
            "required_amenities": [],
            "priorities": [],
            "special_requirements": [],
            "trip_days": None,
            "room_count": None,
            "rating": None,
            "check_in": None,
            "check_out": None,
            "location_phrase": title,
            "location_mode": "unknown",
        },
        "raw_text": text or "",
        "parser_mode": "smart_suggestion_poi_category",
        "location_status": "unresolved",
        "location_candidates": [],
        "canonical_area": None,
        "location_confidence": 0.0,
        "location_source": "poi_category_needs_anchor",
        "matched_text": title,
        "ready_for_recommendation": False,
        "can_show_recommendations": False,
        "recommendation_level": "none",
        "missing_slots": ["location"],
        "suggested_questions": [f"Bạn muốn tìm chỗ ở gần {title} ở khu vực hoặc địa điểm nào?"],
        "follow_up_question": f"Bạn muốn tìm chỗ ở gần {title} ở khu vực hoặc địa điểm nào?",
        "awaiting_confirmation": True,
        "confirmation_required": True,
        "polite_bot_message": f"Mình hiểu bạn quan tâm {title}. Bạn nhập thêm khu vực hoặc tên địa điểm cụ thể giúp mình nhé.",
        "bot_message": f"Mình hiểu bạn quan tâm {title}. Bạn nhập thêm khu vực hoặc tên địa điểm cụ thể giúp mình nhé.",
        "recommendation_action": {
            "visible": True,
            "enabled": False,
            "eligible": False,
            "requires_submit": False,
            "pref_id": None,
            "url": None,
            "reason": "poi_category_needs_anchor",
        },
        "smart_suggestion": suggestion,
        "usable_filters": [],
    }


def suggestion_from_payload(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    payload = payload or {}
    selected = payload.get("smart_suggestion") if isinstance(payload.get("smart_suggestion"), dict) else None
    if selected:
        selected = dict(selected)
        merged_payload = {key: value for key, value in payload.items() if key != "smart_suggestion"}
        selected["payload"] = {**(selected.get("payload") or {}), **merged_payload}
        return selected
    if payload.get("selected_accommodation_id"):
        try:
            accommodation = Accommodation.objects.get(pk=payload["selected_accommodation_id"])
        except (Accommodation.DoesNotExist, ValueError, TypeError):
            return None
        return _serialize_item(_accommodation_item(accommodation), 100.0, 100.0, accommodation.name)
    return None


def _suggestion_corpus() -> tuple[SuggestionItem, ...]:
    now = time.monotonic()
    if _CORPUS_CACHE["expires_at"] > now:
        return _CORPUS_CACHE["items"]

    items: list[SuggestionItem] = []
    accommodations = Accommodation.objects.only(
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
    for accommodation in accommodations:
        items.append(_accommodation_item(accommodation))

    areas = sorted({item.area for item in accommodations if item.area})
    for area in areas:
        items.append(_area_item(area))

    for key, label in TYPE_LABELS.items():
        items.append(_accommodation_type_item(key, label))

    for key, meta in POI_TYPES.items():
        items.append(_poi_category_item(key, meta))

    try:
        for reference in PlaceReference.objects.all()[:200]:
            items.append(_cached_place_item(reference))
    except Exception:
        pass

    _CORPUS_CACHE["items"] = tuple(items)
    _CORPUS_CACHE["expires_at"] = now + SUGGESTION_CACHE_SECONDS
    return _CORPUS_CACHE["items"]


def _accommodation_item(accommodation: Accommodation) -> SuggestionItem:
    label = TYPE_LABELS.get(accommodation.accommodation_type, accommodation.accommodation_type)
    subtitle = " · ".join(part for part in ("Chỗ ở", label, accommodation.area) if part)
    aliases = (
        accommodation.name,
        accommodation.address,
        f"{accommodation.name} {label}",
        f"{label} {accommodation.name}",
        f"{accommodation.name} {accommodation.area}",
    )
    popularity = min(float(accommodation.review_count or 0) / 250, 5.0) + float(accommodation.rating or 0) / 2
    return SuggestionItem(
        kind="accommodation",
        title=accommodation.name,
        subtitle=subtitle,
        payload={
            "selected_accommodation_id": accommodation.id,
            "destination": accommodation.name,
            "accommodation_type": accommodation.accommodation_type,
            "area": accommodation.area,
        },
        aliases=tuple(alias for alias in aliases if alias),
        priority=16,
        popularity=popularity,
        object_id=accommodation.id,
        lat=accommodation.latitude,
        lon=accommodation.longitude,
        url=reverse("accommodation_detail", kwargs={"pk": accommodation.id}),
    )


def _area_item(area: str) -> SuggestionItem:
    aliases = {area}
    norm = _normalize(area)
    compact = norm.replace(" ", "")
    aliases.add(norm)
    aliases.add(compact)
    match = re.search(r"(?:quan|quận)\s*(\d+)", norm)
    if match:
        number = match.group(1)
        aliases.update({f"q{number}", f"q.{number}", f"quan {number}", f"quận {number}"})
    return SuggestionItem(
        kind="area",
        title=area,
        subtitle="Khu vực",
        payload={"area": area, "location_mode": "area"},
        aliases=tuple(aliases),
        priority=12,
    )


def _accommodation_type_item(key: str, label: str) -> SuggestionItem:
    return SuggestionItem(
        kind="accommodation_type",
        title=label,
        subtitle="Loại chỗ ở",
        payload={"preferred_type": key, "accommodation_type": key, "accommodation_types": [key]},
        aliases=tuple({label, key, *TYPE_ALIASES.get(key, ())}),
        priority=9,
    )


def _poi_category_item(key: str, meta: dict[str, Any]) -> SuggestionItem:
    label = str(meta.get("label") or key)
    return SuggestionItem(
        kind="poi_category",
        title=label,
        subtitle="Loại địa điểm",
        payload={"poi_type": key, "poi_category": key, "smart_kind": "poi_category"},
        aliases=tuple({label, key, *POI_ALIASES.get(key, ())}),
        priority=7,
    )


def _cached_place_item(reference: PlaceReference) -> SuggestionItem:
    aliases = [reference.canonical_name, reference.display_name, reference.query_text, *(reference.aliases or [])]
    return SuggestionItem(
        kind="cached_poi",
        title=reference.canonical_name,
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
        priority=10,
        popularity=float(reference.confidence or 0.0) * 4,
        object_id=reference.id,
        lat=reference.latitude,
        lon=reference.longitude,
    )


def _best_text_score(query_key: str, query_tokens: set[str], item: SuggestionItem) -> tuple[float, str]:
    best_score = 0.0
    best_alias = item.title
    for alias in (item.title, *item.aliases):
        alias_key = _normalize(alias)
        if not alias_key:
            continue
        score = _text_score(query_key, query_tokens, alias_key)
        if score > best_score:
            best_score = score
            best_alias = alias
    return best_score, best_alias


def _text_score(query_key: str, query_tokens: set[str], alias_key: str) -> float:
    if query_key == alias_key:
        return 100.0
    if alias_key.startswith(query_key):
        return 94.0
    if query_key.startswith(alias_key) and len(alias_key) >= 3:
        return 88.0
    if query_key in alias_key:
        return 82.0
    if len(alias_key) >= 3 and alias_key in query_key:
        return 86.0
    query_compact = query_key.replace(" ", "")
    alias_compact = alias_key.replace(" ", "")
    if query_compact and query_compact == alias_compact:
        return 98.0
    if len(query_compact) >= 2 and alias_compact.startswith(query_compact):
        return 91.0
    if len(query_compact) >= 4 and query_compact in alias_compact:
        return 80.0

    alias_tokens = _tokens(alias_key)
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


def _serialize_item(item: SuggestionItem, rank: float, text_score: float, matched_alias: str) -> dict[str, Any]:
    payload = dict(item.payload)
    payload.setdefault("smart_suggestion", None)
    output = {
        "kind": item.kind,
        "title": item.title,
        "subtitle": item.subtitle,
        "score": int(min(99, round(rank))),
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
        if key not in {"payload"}
    }
    return output


def _is_poi_category_clarification(text: str | None, top: dict[str, Any], suggestions: list[dict[str, Any]]) -> bool:
    if top.get("kind") != "poi_category" or top.get("score", 0) < 80:
        return False
    if any(item.get("kind") in {"area", "cached_poi", "accommodation"} and item.get("score", 0) >= 82 for item in suggestions[1:]):
        return False
    query_tokens = _tokens(_normalize(text))
    category_tokens = set()
    poi_type = (top.get("payload") or {}).get("poi_type")
    for alias in POI_ALIASES.get(str(poi_type), ()):
        category_tokens.update(_tokens(_normalize(alias)))
    category_tokens.update(_tokens(_normalize(top.get("title"))))
    type_tokens = set()
    for aliases in TYPE_ALIASES.values():
        for alias in aliases:
            type_tokens.update(_tokens(_normalize(alias)))
    meaningful = query_tokens - category_tokens - type_tokens - STOPWORDS
    return not meaningful


def _has_strong_place_competitor(top: dict[str, Any], competitors: list[dict[str, Any]]) -> bool:
    competing_kinds = {"accommodation", "area", "cached_poi"}
    top_score = int(top.get("score") or 0)
    return any(
        item.get("kind") in competing_kinds
        and int(item.get("score") or 0) >= top_score - ACCOMMODATION_MARGIN
        for item in competitors
    )


def _is_searchable_query(query_key: str) -> bool:
    if len(query_key.replace(" ", "")) >= MIN_QUERY_LENGTH:
        return True
    return bool(re.fullmatch(r"q\d+", query_key.replace(" ", "")))


def _minimum_score(query_key: str) -> float:
    return 72.0 if len(query_key.replace(" ", "")) <= 3 else 62.0


def _normalize(value: Any) -> str:
    text = normalize_common_typos("" if value is None else str(value))
    text = normalize_key(text)
    text = re.sub(r"[^\w\s.]", " ", text, flags=re.UNICODE)
    return re.sub(r"\s+", " ", text).strip()


def _tokens(value: str) -> set[str]:
    return {token for token in re.split(r"\s+", value) if token}


def _meaningful_tokens(value: str) -> set[str]:
    return _tokens(value) - STOPWORDS


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


def _accommodation_search_url(destination: str) -> str:
    return f"{reverse('accommodation_list')}?{urlencode({'destination': destination})}"
