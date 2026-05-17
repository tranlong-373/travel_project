from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from functools import lru_cache
from typing import Any

from .normalizers import normalize_key
from .place_geocoder import (
    rejected_geocoder_payload,
    resolve_place_reference,
    should_geocode_place_phrase,
    validate_geocoded_place,
)
from .slot_pipeline import is_ambiguous_location_phrase, is_blocked_location_phrase


class FilterStrength(str, Enum):
    HARD = "hard"
    SOFT = "soft"
    PREFERENCE = "preference"
    NONE = "none"


class FilterPriority(str, Enum):
    MUST_HAVE = "must_have"
    IMPORTANT = "important"
    NICE_TO_HAVE = "nice_to_have"


@dataclass(frozen=True)
class FilterNode:
    key: str
    value: Any
    operator: str
    strength: FilterStrength = FilterStrength.SOFT
    confidence: float = 1.0
    priority: FilterPriority = FilterPriority.IMPORTANT
    source: str = "deterministic"
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "value": self.value,
            "operator": self.operator,
            "strength": self.strength.value,
            "confidence": round(float(self.confidence), 3),
            "priority": self.priority.value,
            "source": self.source,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class LocationReference:
    canonical_name: str
    aliases: tuple[str, ...]
    kind: str
    lat: float
    lon: float
    default_radius_km: float
    canonical_area: str | None = None


@dataclass(frozen=True)
class FilterTree:
    location: dict[str, Any]
    filters: tuple[FilterNode, ...]
    available_slots: tuple[str, ...]
    missing_slots: tuple[str, ...]
    partial_intent: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "location": dict(self.location),
            "filters": [node.to_dict() for node in self.filters],
            "available_slots": list(self.available_slots),
            "missing_slots": list(self.missing_slots),
            "partial_intent": self.partial_intent,
            "usable_filter_count": self.usable_filter_count,
        }

    @property
    def usable_filter_count(self) -> int:
        mode = self.location.get("mode")
        has_coordinates = self.location.get("anchor_lat") is not None and self.location.get("anchor_lon") is not None
        location_count = 1 if mode == "area" or (mode in {"near_anchor", "near_user", "city_center"} and has_coordinates) else 0
        return len(self.filters) + location_count


ANYWHERE_PATTERNS = (
    r"\bo dau cung duoc\b",
    r"\bdi dau cung duoc\b",
    r"\bkhu nao cung duoc\b",
    r"\bcho nao cung duoc\b",
    r"\bkhong quan trong vi tri\b",
    r"\bvi tri khong quan trong\b",
    r"\bkhong can khu vuc\b",
    r"\banywhere\b",
    r"\bwherever\b",
    r"\bdoesn t matter where\b",
    r"\bdoesnt matter where\b",
    r"\bno location preference\b",
)
NEAR_CUE_PATTERN = re.compile(
    r"\b(?:gan|quanh|xung quanh|canh|ke|sat|near|around|close to|nearby)\b"
)
NEAR_CUE_RAW_PATTERN = re.compile(
    r"\b(?:gần|gan|quanh|xung quanh|cạnh|canh|kề|ke|sát|sat|near|around|close to|nearby)\b",
    re.IGNORECASE,
)
NEAR_USER_PATTERNS = (
    r"\bgan vi tri hien tai\b",
    r"\bquanh vi tri hien tai\b",
    r"\bgan toi\b",
    r"\bnear me\b",
    r"\baround me\b",
    r"\bcurrent location\b",
    r"\bmy location\b",
)
DISTRICT_CUE_PATTERN = re.compile(r"\b(?:quan|q\.?|district|dist)\s*(\d{1,2})\b")
PEOPLE_CONTEXT_PATTERN = re.compile(
    r"\b(?:cho|for)?\s*(\d{1,2})\s*(?:nguoi|ng|khach|guest|guests|people|pax|adults?|persons?)\b"
)


LOCAL_LOCATION_REFERENCES: tuple[LocationReference, ...] = (
    LocationReference(
        "Nhà thờ Đức Bà",
        ("nhà thờ đức bà", "nha tho duc ba", "notre dame", "notre-dame", "saigon notre dame"),
        "landmark",
        10.7798,
        106.6990,
        2.5,
        "TP HCM",
    ),
    LocationReference(
        "Suối Tiên",
        ("suối tiên", "suoi tien", "khu du lịch suối tiên", "khu du lich suoi tien"),
        "attraction",
        10.8700,
        106.8031,
        8.0,
        "TP HCM",
    ),
    LocationReference(
        "Bến Thành",
        ("bến thành", "ben thanh", "chợ bến thành", "cho ben thanh"),
        "landmark",
        10.7724,
        106.6980,
        2.5,
        "TP HCM",
    ),
    LocationReference(
        "Landmark 81",
        ("landmark 81", "vinhomes landmark 81"),
        "landmark",
        10.7950,
        106.7219,
        2.5,
        "TP HCM",
    ),
    LocationReference(
        "Tân Sơn Nhất",
        (
            "tân sơn nhất",
            "tan son nhat",
            "sân bay tân sơn nhất",
            "san bay tan son nhat",
            "tan son nhat airport",
        ),
        "airport",
        10.8188,
        106.6519,
        5.0,
        "TP HCM",
    ),
    LocationReference(
        "Chợ Rẫy",
        ("chợ rẫy", "cho ray", "bệnh viện chợ rẫy", "benh vien cho ray"),
        "landmark",
        10.7554,
        106.6580,
        2.5,
        "TP HCM",
    ),
    LocationReference(
        "Thảo Điền",
        ("thảo điền", "thao dien"),
        "district",
        10.8020,
        106.7317,
        3.0,
        "TP HCM",
    ),
    LocationReference(
        "Thủ Đức",
        ("thủ đức", "thu duc", "thuduc", "tp thủ đức", "tp thu duc", "thành phố thủ đức", "thanh pho thu duc"),
        "district",
        10.8494,
        106.7537,
        8.0,
        "Thủ Đức",
    ),
    LocationReference(
        "Quận 2",
        ("quận 2", "quan 2", "q2", "q 2", "district 2"),
        "district",
        10.7873,
        106.7498,
        6.0,
        "Quận 2",
    ),
    LocationReference(
        "Quận 3",
        ("quận 3", "quan 3", "q3", "q 3", "district 3"),
        "district",
        10.7847,
        106.6844,
        4.0,
        "Quận 3",
    ),
    LocationReference(
        "TP HCM",
        ("tp hcm", "tphcm", "hcm", "ho chi minh", "sài gòn", "sai gon", "saigon"),
        "city",
        10.7769,
        106.7009,
        15.0,
        "TP HCM",
    ),
    LocationReference(
        "Hà Nội",
        ("hà nội", "ha noi", "hanoi"),
        "city",
        21.0285,
        105.8542,
        15.0,
        "Hà Nội",
    ),
)


def has_explicit_anywhere(text: str | None) -> bool:
    norm = normalize_key(text or "")
    return any(re.search(pattern, norm) for pattern in ANYWHERE_PATTERNS)


def should_ignore_numeric_location_match(text: str | None, canonical_area: str | None) -> bool:
    if not text or not canonical_area:
        return False

    area_key = normalize_key(canonical_area)
    match = re.fullmatch(r"quan\s+(\d{1,2})", area_key)
    if not match:
        return False

    district_number = match.group(1)
    norm = normalize_key(text)
    explicit_district_numbers = {m.group(1).lstrip("0") for m in DISTRICT_CUE_PATTERN.finditer(norm)}
    if district_number in explicit_district_numbers:
        return False

    people_numbers = {m.group(1).lstrip("0") for m in PEOPLE_CONTEXT_PATTERN.finditer(norm)}
    return district_number in people_numbers


def build_filter_tree(
    *,
    text: str,
    slots: dict[str, Any] | None,
    location_result: dict[str, Any] | None = None,
) -> FilterTree:
    slots = slots or {}
    location_result = location_result or {}
    location = build_location_branch(text=text, slots=slots, location_result=location_result)
    filters = tuple(_build_filter_nodes(slots))
    available_slots = tuple(_available_slots(location, filters))
    missing_slots = tuple(_missing_filter_slots(location, slots))
    partial_intent = bool(available_slots and missing_slots)
    return FilterTree(
        location=location,
        filters=filters,
        available_slots=available_slots,
        missing_slots=missing_slots,
        partial_intent=partial_intent,
    )


def build_location_branch(
    *,
    text: str,
    slots: dict[str, Any] | None,
    location_result: dict[str, Any] | None,
) -> dict[str, Any]:
    slots = slots or {}
    location_result = location_result or {}
    debug_metadata = location_result.get("debug_metadata") or {}
    location_text = debug_metadata.get("remaining_text_for_location") or text or ""
    norm = normalize_key(location_text)
    user_location = slots.get("user_location") or location_result.get("user_location")

    branch = _empty_location_branch()
    if debug_metadata.get("geocoder_reason"):
        branch["geocoder_reason"] = debug_metadata["geocoder_reason"]
    if has_explicit_anywhere(text):
        branch.update(
            {
                "mode": "anywhere",
                "explicit_anywhere": True,
                "strength": FilterStrength.NONE.value,
                "location_display_label": "Ở đâu cũng được",
                "location_source": "deterministic_anywhere",
                "confidence": 0.98,
                "geocoder_called": False,
                "geocoder_reason": "explicit_anywhere",
                "area_match": False,
            }
        )
        return branch

    if slots.get("location_mode") == "anywhere" or location_result.get("location_mode") == "anywhere":
        branch.update(
            {
                "mode": "anywhere",
                "explicit_anywhere": True,
                "strength": FilterStrength.NONE.value,
                "location_display_label": "Ở đâu cũng được",
                "location_source": location_result.get("location_source") or "context_anywhere",
                "confidence": float(location_result.get("location_confidence") or 0.98),
                "geocoder_reason": "explicit_anywhere",
            }
        )
        return branch

    if slots.get("location_mode") == "city_center" or location_result.get("location_mode") == "city_center":
        branch.update(
            {
                "mode": "city_center",
                "location_phrase": location_result.get("location_phrase") or slots.get("location_phrase") or "trung tâm thành phố",
                "canonical_area": location_result.get("canonical_area") or slots.get("area"),
                "anchor_name": location_result.get("anchor_name") or location_result.get("location_display_label") or "trung tâm thành phố",
                "anchor_kind": "city_center",
                "anchor_lat": _float_or_none(location_result.get("anchor_lat")),
                "anchor_lon": _float_or_none(location_result.get("anchor_lon")),
                "anchor_radius_km": _float_or_none(location_result.get("anchor_radius_km")) or 4.0,
                "location_display_label": location_result.get("location_display_label") or "trung tâm thành phố",
                "location_source": location_result.get("location_source") or "semantic_city_center",
                "provider": location_result.get("provider") or "semantic",
                "confidence": float(location_result.get("location_confidence") or 0.93),
                "geocoder_called": False,
                "geocoder_reason": location_result.get("geocoder_reason") or "abstract_city_center_location",
                "unresolved_location": bool(location_result.get("needs_city_clarification")),
                "needs_city_clarification": bool(location_result.get("needs_city_clarification")),
                "ambiguous_location": bool(location_result.get("ambiguous_location")),
                "ambiguous_location_question": location_result.get("ambiguous_location_question"),
                "rejected_geocoder_results": location_result.get("rejected_geocoder_results") or [],
            }
        )
        return branch

    if user_location:
        branch.update(
            {
                "mode": "near_user",
                "anchor_name": "Vị trí hiện tại",
                "anchor_kind": "user_location",
                "anchor_lat": _float_or_none(user_location.get("lat")),
                "anchor_lon": _float_or_none(user_location.get("lon")),
                "anchor_radius_km": _float_or_none(user_location.get("radius_km") or user_location.get("radius")) or 10.0,
                "location_display_label": "Gần vị trí hiện tại",
                "location_source": "browser_geolocation",
                "confidence": 1.0,
            }
        )
        return branch

    if any(re.search(pattern, norm) for pattern in NEAR_USER_PATTERNS):
        branch.update(
            {
                "mode": "near_user",
                "anchor_name": "Vị trí hiện tại",
                "anchor_kind": "user_location",
                "anchor_radius_km": 10.0,
                "location_display_label": "Gần vị trí hiện tại",
                "location_source": "deterministic_near_user",
                "confidence": 0.9,
            }
        )
        return branch

    if location_result.get("location_status") == "ambiguous" or location_result.get("ambiguous_location"):
        branch.update(
            {
                "mode": "unknown",
                "location_source": location_result.get("location_source", "deterministic"),
                "location_phrase": location_result.get("matched_text"),
                "ambiguous_location": bool(location_result.get("ambiguous_location", True)),
                "ambiguous_location_question": location_result.get("ambiguous_location_question"),
                "geocoder_called": False,
                "geocoder_reason": location_result.get("geocoder_reason") or "ambiguous_location",
            }
        )
        return branch

    has_near_cue = bool(NEAR_CUE_PATTERN.search(norm))
    anchor_phrase = _extract_near_anchor_phrase(location_text or "") if has_near_cue else None
    local_reference = resolve_local_location_reference(anchor_phrase or location_text)
    if has_near_cue and local_reference:
        branch = _branch_from_reference(local_reference, near=True, location_phrase=anchor_phrase)
        return branch

    if has_near_cue:
        unresolved_anchor = anchor_phrase
        should_try_geocoder = (
            bool(unresolved_anchor)
            and not is_blocked_location_phrase(unresolved_anchor)
            and not is_ambiguous_location_phrase(unresolved_anchor)
            and should_geocode_place_phrase(unresolved_anchor)
        )
        geocoded = geocode_anchor(unresolved_anchor) if unresolved_anchor and should_try_geocoder else None
        geocoded = _validated_geocoded_anchor(branch, geocoded, unresolved_anchor)
        if geocoded and geocoded.get("lat") is not None and geocoded.get("lon") is not None:
            anchor_name = geocoded.get("name") or geocoded.get("display_name") or unresolved_anchor
            branch.update(
                {
                    "mode": "near_anchor",
                    "location_phrase": unresolved_anchor,
                    "anchor_name": anchor_name,
                    "anchor_kind": geocoded.get("kind") or "geocoded",
                    "anchor_lat": geocoded.get("lat"),
                    "anchor_lon": geocoded.get("lon"),
                    "anchor_radius_km": geocoded.get("default_radius_km") or 5.0,
                    "location_display_label": f"gần {anchor_name}",
                    "location_source": geocoded.get("source") or "osm_geocoder",
                    "provider": geocoded.get("provider"),
                    "map_area": geocoded.get("map_area"),
                    "map_display_name": geocoded.get("display_name"),
                    "map_address": geocoded.get("address") or {},
                    "geocode_query": geocoded.get("query"),
                    "geocoder_queries": geocoded.get("geocoder_queries") or [],
                    "resolved_place": _resolved_place_payload(geocoded, anchor_name),
                    "unresolved_location": False,
                    "confidence": geocoded.get("confidence") or 0.85,
                    "geocoder_called": _external_geocoder_called(geocoded),
                    "geocoder_reason": "strong_near_anchor_or_place_phrase",
                }
            )
            return branch
        if unresolved_anchor and should_try_geocoder:
            branch.update(
                {
                    "mode": "near_anchor",
                    "location_phrase": unresolved_anchor,
                    "anchor_name": unresolved_anchor,
                    "anchor_kind": "unresolved",
                    "anchor_radius_km": 5.0,
                    "location_display_label": unresolved_anchor,
                    "location_source": "unresolved_near_anchor",
                    "unresolved_location": True,
                    "confidence": 0.35,
                    "geocoder_called": True,
                    "geocoder_reason": "strong_near_anchor_or_place_phrase",
                }
            )
            return branch

    text_reference = resolve_local_location_reference(location_text)
    if (
        text_reference
        and text_reference.kind not in {"district", "city"}
        and _should_treat_reference_as_anchor(location_text, slots, location_result, text_reference)
    ):
        branch = _branch_from_reference(
            text_reference,
            near=True,
            location_phrase=_location_phrase_for_reference(location_text, text_reference),
        )
        return branch

    if _looks_like_place_follow_up(location_text, slots, location_result):
        follow_up_phrase = _extract_standalone_place_phrase(location_text)
        local_reference = resolve_local_location_reference(follow_up_phrase)
        if local_reference and local_reference.kind not in {"district", "city"}:
            branch = _branch_from_reference(local_reference, near=True, location_phrase=follow_up_phrase)
            return branch
        if (
            follow_up_phrase
            and not is_blocked_location_phrase(follow_up_phrase)
            and not is_ambiguous_location_phrase(follow_up_phrase)
            and should_geocode_place_phrase(follow_up_phrase)
        ):
            geocoded = geocode_anchor(follow_up_phrase)
            geocoded = _validated_geocoded_anchor(branch, geocoded, follow_up_phrase)
            if geocoded and geocoded.get("lat") is not None and geocoded.get("lon") is not None:
                anchor_name = geocoded.get("name") or geocoded.get("display_name") or follow_up_phrase
                branch.update(
                    {
                        "mode": "near_anchor",
                        "location_phrase": follow_up_phrase,
                        "anchor_name": anchor_name,
                        "anchor_kind": geocoded.get("kind") or "geocoded",
                        "anchor_lat": geocoded.get("lat"),
                        "anchor_lon": geocoded.get("lon"),
                        "anchor_radius_km": geocoded.get("default_radius_km") or 5.0,
                        "location_display_label": f"gần {anchor_name}",
                        "location_source": geocoded.get("source") or "osm_geocoder",
                        "provider": geocoded.get("provider"),
                        "map_area": geocoded.get("map_area"),
                        "map_display_name": geocoded.get("display_name"),
                        "map_address": geocoded.get("address") or {},
                        "geocode_query": geocoded.get("query"),
                        "geocoder_queries": geocoded.get("geocoder_queries") or [],
                        "resolved_place": _resolved_place_payload(geocoded, anchor_name),
                        "unresolved_location": False,
                        "confidence": geocoded.get("confidence") or 0.8,
                        "geocoder_called": _external_geocoder_called(geocoded),
                        "geocoder_reason": "strong_near_anchor_or_place_phrase",
                    }
                )
                return branch
            branch.update(
                {
                    "mode": "near_anchor",
                    "location_phrase": follow_up_phrase,
                    "anchor_name": follow_up_phrase,
                    "anchor_kind": "unresolved",
                    "anchor_radius_km": 5.0,
                    "location_display_label": follow_up_phrase,
                    "location_source": "unresolved_near_anchor",
                    "unresolved_location": True,
                    "confidence": 0.35,
                    "geocoder_called": True,
                    "geocoder_reason": "strong_near_anchor_or_place_phrase",
                }
            )
            return branch

    location_status = location_result.get("location_status") or "unresolved"
    canonical_area = location_result.get("canonical_area") or slots.get("area")
    pending_phrase = slots.get("location_phrase") or (
        location_result.get("location_phrase") if location_result.get("location_mode") == "near_anchor" else None
    )
    if (
        (slots.get("location_mode") == "near_anchor" or location_result.get("location_mode") == "near_anchor")
        and pending_phrase
        and not canonical_area
    ):
        geocoded = (
            geocode_anchor(str(pending_phrase))
            if not is_ambiguous_location_phrase(str(pending_phrase)) and should_geocode_place_phrase(str(pending_phrase))
            else None
        )
        geocoded = _validated_geocoded_anchor(branch, geocoded, str(pending_phrase))
        if geocoded and geocoded.get("lat") is not None and geocoded.get("lon") is not None:
            anchor_name = geocoded.get("name") or geocoded.get("display_name") or pending_phrase
            branch.update(
                {
                    "mode": "near_anchor",
                    "location_phrase": pending_phrase,
                    "anchor_name": anchor_name,
                    "anchor_kind": geocoded.get("kind") or "geocoded",
                    "anchor_lat": geocoded.get("lat"),
                    "anchor_lon": geocoded.get("lon"),
                    "anchor_radius_km": geocoded.get("default_radius_km") or 5.0,
                    "location_display_label": f"gần {anchor_name}",
                    "location_source": geocoded.get("source") or "osm_geocoder",
                    "provider": geocoded.get("provider"),
                    "map_area": geocoded.get("map_area"),
                    "map_display_name": geocoded.get("display_name"),
                    "map_address": geocoded.get("address") or {},
                    "geocode_query": geocoded.get("query"),
                    "geocoder_queries": geocoded.get("geocoder_queries") or [],
                    "resolved_place": _resolved_place_payload(geocoded, anchor_name),
                    "unresolved_location": False,
                    "confidence": geocoded.get("confidence") or 0.8,
                    "geocoder_called": _external_geocoder_called(geocoded),
                    "geocoder_reason": "context_pending_near_anchor",
                }
            )
            return branch
        branch.update(
            {
                "mode": "near_anchor",
                "location_phrase": pending_phrase,
                "anchor_name": pending_phrase,
                "anchor_kind": "unresolved",
                "anchor_radius_km": 5.0,
                "location_display_label": str(pending_phrase),
                "location_source": "unresolved_near_anchor",
                "unresolved_location": True,
                "confidence": 0.35,
                "geocoder_called": bool(should_geocode_place_phrase(str(pending_phrase))),
                "geocoder_reason": "context_pending_near_anchor",
            }
        )
        return branch

    if location_status == "multiple_choice":
        branch.update({"mode": "multiple_choice", "location_source": location_result.get("location_source", "deterministic")})
        return branch
    if location_status == "conflict":
        branch.update({"mode": "conflict", "location_source": location_result.get("location_source", "deterministic")})
        return branch
    if location_status == "unsupported":
        branch.update({"mode": "unsupported", "location_source": location_result.get("location_source", "deterministic")})
        return branch
    if location_status == "ambiguous":
        branch.update(
            {
                "mode": "unknown",
                "location_source": location_result.get("location_source", "deterministic"),
                "location_phrase": location_result.get("matched_text"),
                "ambiguous_location": bool(location_result.get("ambiguous_location")),
                "ambiguous_location_question": location_result.get("ambiguous_location_question"),
                "geocoder_called": False,
                "geocoder_reason": location_result.get("geocoder_reason") or "ambiguous_location",
            }
        )
        return branch

    if canonical_area:
        reference = resolve_local_location_reference(str(canonical_area))
        if reference and reference.kind in {"district", "city"}:
            branch.update(_branch_from_reference(reference, near=False, location_phrase=canonical_area))
            branch["mode"] = "area"
            branch["anchor_name"] = None
            branch["anchor_kind"] = None
            branch["anchor_lat"] = None
            branch["anchor_lon"] = None
            branch["anchor_radius_km"] = None
            branch["location_display_label"] = reference.canonical_area or reference.canonical_name
            return branch

        branch.update(
            {
                "mode": "area",
                "location_phrase": canonical_area,
                "canonical_area": canonical_area,
                "location_display_label": canonical_area,
                "location_source": location_result.get("location_source", "deterministic"),
                "confidence": float(location_result.get("location_confidence") or 0.9),
                "geocoder_called": False,
                "geocoder_reason": "clear_area_match",
                "area_match": True,
            }
        )
        return branch

    return branch


def resolve_local_location_reference(text: str | None) -> LocationReference | None:
    norm = normalize_key(text or "")
    if not norm:
        return None

    dynamic_reference = _find_dynamic_place_reference(text)
    if dynamic_reference:
        lat = _float_or_none(dynamic_reference.get("lat"))
        lon = _float_or_none(dynamic_reference.get("lon"))
        if lat is not None and lon is not None:
            return LocationReference(
                canonical_name=dynamic_reference.get("canonical_name") or dynamic_reference.get("name") or str(text),
                aliases=tuple(dynamic_reference.get("aliases") or ()),
                kind=dynamic_reference.get("kind") or dynamic_reference.get("place_type") or "geocoded",
                lat=lat,
                lon=lon,
                default_radius_km=float(dynamic_reference.get("default_radius_km") or 5.0),
                canonical_area=dynamic_reference.get("district") if dynamic_reference.get("kind") == "district" else None,
            )

    for alias_key, reference in _reference_alias_index():
        if re.search(rf"(?<!\w){re.escape(alias_key)}(?!\w)", norm):
            return reference
    return None


def _find_dynamic_place_reference(text: str | None) -> dict[str, Any] | None:
    try:
        from importlib import import_module

        return import_module("chat_api.services.place_reference").find_place_reference(text)
    except Exception:
        return None


@lru_cache(maxsize=1)
def _reference_alias_index() -> tuple[tuple[str, LocationReference], ...]:
    pairs: list[tuple[str, LocationReference]] = []
    for reference in LOCAL_LOCATION_REFERENCES:
        for alias in (reference.canonical_name, *reference.aliases):
            alias_key = normalize_key(alias)
            if alias_key:
                pairs.append((alias_key, reference))
    pairs.sort(key=lambda item: len(item[0]), reverse=True)
    return tuple(pairs)


@lru_cache(maxsize=128)
def geocode_anchor(anchor_name: str | None) -> dict[str, Any] | None:
    if not anchor_name:
        return None

    try:
        result = resolve_place_reference(anchor_name)
    except Exception:
        return None
    if not result:
        return None
    return {
        "name": result.get("name") or anchor_name,
        "lat": result.get("lat"),
        "lon": result.get("lon"),
        "display_name": result.get("display_name") or anchor_name,
        "kind": result.get("kind") or "geocoded",
        "default_radius_km": result.get("default_radius_km") or 5.0,
        "source": result.get("source") or "osm_geocoder",
        "provider": result.get("provider"),
        "confidence": result.get("confidence"),
        "map_area": result.get("map_area"),
        "address": result.get("address") or {},
        "query": result.get("query"),
        "geocoder_queries": result.get("geocoder_queries") or [],
    }


def soft_filter_summary(tree: dict[str, Any] | FilterTree | None) -> str:
    if isinstance(tree, FilterTree):
        tree_dict = tree.to_dict()
    else:
        tree_dict = tree or {}

    parts: list[str] = []
    location = tree_dict.get("location") or {}
    mode = location.get("mode")
    if mode == "anywhere":
        parts.append("không giới hạn khu vực")
    elif mode == "area" and location.get("canonical_area"):
        parts.append(f"khu vực {location['canonical_area']}")
    elif mode == "city_center" and location.get("location_display_label"):
        parts.append(str(location["location_display_label"]))
    elif mode in {"near_anchor", "near_user"} and location.get("location_display_label"):
        parts.append(str(location["location_display_label"]))

    for node in tree_dict.get("filters") or []:
        key = node.get("key")
        value = node.get("value")
        if key == "budget_max":
            min_value = _filter_value(tree_dict, "budget_min")
            if min_value:
                parts.append(f"ngân sách {_format_vnd(min_value)} - {_format_vnd(value)}/đêm")
            else:
                parts.append(f"ngân sách tối đa {_format_vnd(value)}/đêm")
        elif key == "budget_min":
            if not _filter_value(tree_dict, "budget_max"):
                parts.append(f"ngân sách từ {_format_vnd(value)}/đêm")
        elif key == "guest_count":
            parts.append(f"{value} khách")
        elif key in {"accommodation_type", "accommodation_types"}:
            values = value if isinstance(value, list) else [value]
            parts.append("loại " + " hoặc ".join(map(str, values)))
        elif key == "amenities" and value:
            parts.append("tiện nghi " + ", ".join(map(str, value)))
        elif key == "rating":
            parts.append(f"đánh giá từ {value}")

    return "; ".join(parts)


def _filter_value(tree_dict: dict[str, Any], key: str) -> Any:
    for node in tree_dict.get("filters") or []:
        if isinstance(node, dict) and node.get("key") == key:
            return node.get("value")
    return None


def _format_vnd(value: Any) -> str:
    try:
        return f"{int(value):,}".replace(",", ".") + "đ"
    except (TypeError, ValueError):
        return str(value)


def _empty_location_branch() -> dict[str, Any]:
    return {
        "mode": "unknown",
        "explicit_anywhere": False,
        "strength": FilterStrength.SOFT.value,
        "location_phrase": None,
        "canonical_area": None,
        "anchor_name": None,
        "anchor_kind": None,
        "anchor_lat": None,
        "anchor_lon": None,
        "anchor_radius_km": None,
        "location_display_label": None,
        "location_source": "none",
        "provider": None,
        "map_area": None,
        "map_display_name": None,
        "map_address": {},
        "geocode_query": None,
        "geocoder_queries": [],
        "resolved_place": None,
        "unresolved_location": False,
        "needs_city_clarification": False,
        "ambiguous_location": False,
        "ambiguous_location_question": None,
        "rejected_geocoder_results": [],
        "confidence": 0.0,
        "geocoder_called": False,
        "geocoder_reason": "no_location_intent",
        "area_match": False,
    }


def _branch_from_reference(
    reference: LocationReference,
    *,
    near: bool,
    location_phrase: str | None = None,
) -> dict[str, Any]:
    if near:
        return {
            "mode": "near_anchor",
            "explicit_anywhere": False,
            "strength": FilterStrength.SOFT.value,
            "location_phrase": location_phrase or reference.canonical_name,
            "canonical_area": reference.canonical_area if reference.kind == "district" else None,
            "anchor_name": reference.canonical_name,
            "anchor_kind": reference.kind,
            "anchor_lat": reference.lat,
            "anchor_lon": reference.lon,
            "anchor_radius_km": reference.default_radius_km,
            "location_display_label": f"gần {reference.canonical_name}",
            "location_source": "local_reference",
            "provider": "local",
            "map_area": None,
            "map_display_name": None,
            "map_address": {},
            "geocode_query": None,
            "geocoder_queries": [],
            "resolved_place": {
                "canonical_name": reference.canonical_name,
                "display_name": reference.canonical_name,
                "latitude": reference.lat,
                "longitude": reference.lon,
                "place_type": reference.kind,
                "provider": "local",
                "source": "local_reference",
            },
            "unresolved_location": False,
            "confidence": 0.95,
            "geocoder_called": False,
            "geocoder_reason": "local_reference",
            "area_match": reference.kind == "district",
        }
    return {
        "mode": "area",
        "explicit_anywhere": False,
        "strength": FilterStrength.SOFT.value,
        "location_phrase": location_phrase or reference.canonical_area or reference.canonical_name,
        "canonical_area": reference.canonical_area or reference.canonical_name,
        "anchor_name": None,
        "anchor_kind": None,
        "anchor_lat": None,
        "anchor_lon": None,
        "anchor_radius_km": None,
        "location_display_label": reference.canonical_area or reference.canonical_name,
        "location_source": "local_reference",
        "provider": "local",
        "map_area": None,
        "map_display_name": None,
        "map_address": {},
        "geocode_query": None,
        "geocoder_queries": [],
        "resolved_place": None,
        "unresolved_location": False,
        "confidence": 0.95,
        "geocoder_called": False,
        "geocoder_reason": "clear_area_match",
        "area_match": True,
    }


def _build_filter_nodes(slots: dict[str, Any]) -> list[FilterNode]:
    nodes: list[FilterNode] = []
    budget_min = slots.get("budget_min")
    budget_max = slots.get("budget_max") or slots.get("budget")
    if budget_min:
        nodes.append(
            FilterNode(
                key="budget_min",
                value=int(budget_min),
                operator="gte",
                strength=FilterStrength.PREFERENCE,
                priority=FilterPriority.NICE_TO_HAVE,
                confidence=0.9,
                reason="user_min_budget",
            )
        )
    if budget_max:
        nodes.append(
            FilterNode(
                key="budget_max",
                value=int(budget_max),
                operator="lte",
                strength=FilterStrength.HARD,
                priority=FilterPriority.MUST_HAVE,
                confidence=0.95,
                reason="user_max_budget",
            )
        )
    if slots.get("guest_count"):
        nodes.append(
            FilterNode(
                key="guest_count",
                value=int(slots["guest_count"]),
                operator="gte_capacity",
                strength=FilterStrength.HARD,
                priority=FilterPriority.MUST_HAVE,
                confidence=0.95,
                reason="user_guest_count",
            )
        )
    accommodation_types = _slot_list(slots.get("accommodation_types"))
    if not accommodation_types and slots.get("preferred_type"):
        accommodation_types = [slots["preferred_type"]]
    if accommodation_types:
        nodes.append(
            FilterNode(
                key="accommodation_types",
                value=accommodation_types,
                operator="in",
                strength=FilterStrength.SOFT,
                priority=FilterPriority.IMPORTANT,
                confidence=0.85,
                reason="user_type_preference",
            )
        )
    elif slots.get("unsupported_preferred_type") or slots.get("raw_preferred_type"):
        preferred_type = slots.get("unsupported_preferred_type") or slots.get("raw_preferred_type")
        nodes.append(
            FilterNode(
                key="accommodation_type",
                value=preferred_type,
                operator="eq",
                strength=FilterStrength.SOFT,
                priority=FilterPriority.IMPORTANT,
                confidence=0.65,
                reason="user_unsupported_type_preference",
            )
        )
    amenities = slots.get("required_amenities") or []
    if amenities:
        nodes.append(
            FilterNode(
                key="amenities",
                value=list(amenities),
                operator="contains",
                strength=FilterStrength.SOFT,
                priority=FilterPriority.IMPORTANT,
                confidence=0.9,
                reason="user_required_amenities",
            )
        )
    if slots.get("priorities"):
        nodes.append(
            FilterNode(
                key="priorities",
                value=list(slots["priorities"]),
                operator="contains",
                strength=FilterStrength.PREFERENCE,
                priority=FilterPriority.NICE_TO_HAVE,
                confidence=0.8,
                reason="user_priorities",
            )
        )
    if slots.get("rating"):
        nodes.append(
            FilterNode(
                key="rating",
                value=float(slots["rating"]),
                operator="gte",
                strength=FilterStrength.SOFT,
                priority=FilterPriority.IMPORTANT,
                confidence=0.85,
                reason="user_min_rating",
            )
        )
    if slots.get("special_requirements"):
        nodes.append(
            FilterNode(
                key="special_requirements",
                value=list(slots["special_requirements"]),
                operator="contains",
                strength=FilterStrength.SOFT,
                priority=FilterPriority.IMPORTANT,
                confidence=0.8,
                reason="user_special_requirements",
            )
        )
    if slots.get("trip_days"):
        nodes.append(
            FilterNode(
                key="date",
                value={"trip_days": int(slots["trip_days"])},
                operator="eq",
                strength=FilterStrength.PREFERENCE,
                priority=FilterPriority.NICE_TO_HAVE,
                confidence=0.85,
                reason="user_trip_days",
            )
        )
    return nodes


def _available_slots(location: dict[str, Any], filters: tuple[FilterNode, ...]) -> list[str]:
    slots: list[str] = []
    if location.get("mode") != "unknown" or location.get("explicit_anywhere"):
        slots.append("location")
    for node in filters:
        if node.key not in slots:
            slots.append(node.key)
    return slots


def _missing_filter_slots(location: dict[str, Any], slots: dict[str, Any]) -> list[str]:
    missing: list[str] = []
    location_mode = location.get("mode")
    if location_mode in {"unknown", "unsupported"} and not location.get("explicit_anywhere"):
        missing.append("location")
    if not (slots.get("budget") or slots.get("budget_max") or slots.get("budget_min")):
        missing.append("budget")
    if not slots.get("guest_count"):
        missing.append("guest_count")
    if not slots.get("trip_days"):
        missing.append("dates")
    return missing


def _extract_near_anchor_phrase(text: str) -> str | None:
    match = NEAR_CUE_RAW_PATTERN.search(text or "")
    if not match:
        return None
    tail = (text or "")[match.end():].strip()
    tail = re.split(
        r"\b(?:dưới|duoi|tối đa|toi da|tầm|tam|cho|for|cần|can|budget|giá|gia|với|voi|"
        r"có thêm|co them|phải có|phai co|yêu cầu|yeu cau|"
        r"có\s+(?:parking|wifi|bếp|hồ|chỗ|bãi|máy)|co\s+(?:parking|wifi|bep|ho|cho|bai|may))\b",
        tail,
        maxsplit=1,
        flags=re.IGNORECASE,
    )[0]
    tail = re.sub(r"\s+", " ", tail).strip(" ,.;:")
    return tail or None


def _extract_standalone_place_phrase(text: str | None) -> str | None:
    value = re.sub(r"\s+", " ", str(text or "")).strip(" ,.;:")
    if not value:
        return None
    value = re.sub(r"^(?:ở|o|tại|tai|khu vực|khu vuc)\s+", "", value, flags=re.IGNORECASE)
    return value.strip(" ,.;:") or None


def _slot_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, (list, tuple, set)):
        return list(dict.fromkeys(str(item).strip() for item in value if str(item).strip()))
    return []


def _should_treat_reference_as_anchor(
    text: str | None,
    slots: dict[str, Any],
    location_result: dict[str, Any],
    reference: LocationReference,
) -> bool:
    norm = normalize_key(text or "")
    if not norm:
        return False
    if re.search(r"\b(?:dua don|don|shuttle|xe dua|xe don)\s+(?:san bay|airport)\b", norm):
        return False
    if norm in {normalize_key(reference.canonical_name), *[normalize_key(alias) for alias in reference.aliases]}:
        return True
    if _has_search_flow_signal(slots):
        return True
    if re.search(r"\b(?:tim|muon|can|cho o|phong|o|tai|gan|quanh|khu vuc)\b", norm):
        return True
    return location_result.get("location_status") in {None, "unresolved", "ambiguous"}


def _has_search_flow_signal(slots: dict[str, Any]) -> bool:
    return bool(
        slots.get("search_intent")
        or slots.get("preferred_type")
        or slots.get("accommodation_type")
        or slots.get("accommodation_types")
        or slots.get("budget")
        or slots.get("budget_max")
        or slots.get("guest_count")
        or slots.get("required_amenities")
        or slots.get("location_mode") in {"near_anchor", "area", "anywhere"}
    )


def _location_phrase_for_reference(text: str | None, reference: LocationReference) -> str:
    phrase = _extract_standalone_place_phrase(text)
    norm = normalize_key(phrase or "")
    if reference.canonical_name == "Tân Sơn Nhất" and ("san bay" in norm or norm == "tan son nhat"):
        return "Sân bay Tân Sơn Nhất"
    return phrase or reference.canonical_name


def _validated_geocoded_anchor(
    branch: dict[str, Any],
    geocoded: dict[str, Any] | None,
    phrase: str | None,
) -> dict[str, Any] | None:
    if not geocoded:
        return None
    intent = _geocoder_intent_for_phrase(phrase)
    if validate_geocoded_place(geocoded, intent=intent, query=phrase):
        return geocoded
    branch["rejected_geocoder_results"] = [
        *branch.get("rejected_geocoder_results", []),
        rejected_geocoder_payload(geocoded, reason=f"semantic_type_mismatch:{intent}"),
    ]
    return None


def _geocoder_intent_for_phrase(phrase: str | None) -> str:
    norm = normalize_key(phrase or "")
    if any(token in norm for token in ("trung tam", "downtown", "city center")):
        return "city_center"
    if "san bay" in norm or "airport" in norm:
        return "airport"
    if "dai hoc" in norm or "truong" in norm:
        return "university"
    return "landmark"


def _looks_like_place_follow_up(
    text: str | None,
    slots: dict[str, Any],
    location_result: dict[str, Any],
) -> bool:
    phrase = _extract_standalone_place_phrase(text)
    if not phrase:
        return False
    if location_result.get("location_status") not in {None, "unresolved", "unsupported", "ambiguous"}:
        return False
    norm = normalize_key(phrase)
    if is_blocked_location_phrase(norm):
        return False
    if is_ambiguous_location_phrase(norm):
        return False
    without_filler = re.sub(
        r"\b(?:toi|minh|tui|em|anh|chi|muon|can|tim|kiem|tin|find|search|want|need)\b",
        " ",
        norm,
    )
    if not re.sub(r"\s+", " ", without_filler).strip():
        return False
    if len(re.findall(r"\w+", norm)) < 2:
        return False
    if _is_generic_search_request_without_place(norm):
        return False
    if re.search(r"\b(?:duoi|tren|tam|trieu|nghin|ngan|nguoi|ngay|dem|wifi|ho boi|khach san|hotel|homestay|hostel|can ho|bep|parking|may giat|dieu hoa)\b", norm):
        return False
    has_active_flow = bool(
        slots.get("search_intent")
        or slots.get("preferred_type")
        or slots.get("accommodation_type")
        or slots.get("accommodation_types")
        or slots.get("budget")
        or slots.get("budget_max")
        or slots.get("guest_count")
        or slots.get("required_amenities")
    )
    return has_active_flow


def _is_generic_search_request_without_place(norm: str) -> bool:
    return bool(
        re.fullmatch(
            r"(?:toi|minh|tui|em|anh|chi)?\s*(?:muon|can|tim|kiem|tim kiem)?\s*(?:tim|kiem|tim kiem)?\s*(?:cho o|noi o|phong|phong o)",
            norm,
        )
    )


def _resolved_place_payload(geocoded: dict[str, Any], anchor_name: str) -> dict[str, Any]:
    return {
        "canonical_name": geocoded.get("name") or anchor_name,
        "display_name": geocoded.get("display_name") or anchor_name,
        "latitude": geocoded.get("lat"),
        "longitude": geocoded.get("lon"),
        "place_type": geocoded.get("kind"),
        "provider": geocoded.get("provider"),
        "source": geocoded.get("source"),
        "confidence": geocoded.get("confidence"),
    }


def _external_geocoder_called(geocoded: dict[str, Any]) -> bool:
    source = str(geocoded.get("source") or "").lower()
    provider = str(geocoded.get("provider") or "").lower()
    return source not in {"cache", "local_reference", "semantic"} and provider not in {"local", "semantic"}


def _float_or_none(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
