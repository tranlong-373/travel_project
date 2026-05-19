from __future__ import annotations

import difflib
import re
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Iterable

from .constants import PRIORITY_MAP, SPECIAL_REQUIREMENT_MAP
from .location_phrase_cleaner import (
    GENERIC_POI_NOUN_PATTERN,
    clean_location_candidate_phrase,
    has_concrete_place_noun,
    strip_location_tails,
)
from .location_gazetteer import load_supported_locations
from .normalizers import normalize_key
from .semantic_locations import detect_semantic_location
from .text_normalizer import normalize_user_text


COUNT_TOKEN = (
    r"\d+|mot|một|hai|ba|bon|bốn|tu|tư|nam|năm|sau|sáu|bay|bảy|tam|tám|chin|chín|"
    r"muoi|mười|one|two|three|four|five|six|seven|eight|nine|ten"
)
MONEY_UNITS_PATTERN = r"k|nghin|ngan|thousand|tr|trieu|m|cu|million|mil|mio"

TYPE_ALIASES: tuple[tuple[str, str], ...] = (
    ("khách sạn", "hotel"),
    ("khach san", "hotel"),
    ("ks", "hotel"),
    ("hotel", "hotel"),
    ("nhà nghỉ", "hotel"),
    ("nha nghi", "hotel"),
    ("motel", "hotel"),
    ("homestay", "homestay"),
    ("home stay", "homestay"),
    ("homstay", "homestay"),
    ("hómtay", "homestay"),
    ("hom tay", "homestay"),
    ("homtay", "homestay"),
    ("honestay", "homestay"),
    ("homes tay", "homestay"),
    ("hómstay", "homestay"),
    ("homestate", "homestay"),
    ("hostel", "hostel"),
    ("nhà trọ", "hostel"),
    ("nha tro", "hostel"),
    ("phòng trọ", "hostel"),
    ("phong tro", "hostel"),
    ("ở trọ", "hostel"),
    ("o tro", "hostel"),
    ("trọ", "hostel"),
    ("tro", "hostel"),
    ("dorm", "hostel"),
    ("căn hộ", "apartment"),
    ("can ho", "apartment"),
    ("căn ho", "apartment"),
    ("can hộ", "apartment"),
    ("apartment", "apartment"),
    ("studio", "apartment"),
    ("chung cư", "apartment"),
    ("chung cu", "apartment"),
    ("serviced apartment", "apartment"),
)

AMENITY_ALIASES: tuple[tuple[str, str], ...] = (
    ("parking", "parking"),
    ("có parking", "parking"),
    ("co parking", "parking"),
    ("đậu xe", "parking"),
    ("dau xe", "parking"),
    ("có đậu xe", "parking"),
    ("co dau xe", "parking"),
    ("đậu xxe", "parking"),
    ("dau xxe", "parking"),
    ("có đậu xxe", "parking"),
    ("co dau xxe", "parking"),
    ("chổ đậu xe", "parking"),
    ("chỗ đậu xe", "parking"),
    ("cho dau xe", "parking"),
    ("chỗ để xe", "parking"),
    ("cho de xe", "parking"),
    ("đỗ xe", "parking"),
    ("do xe", "parking"),
    ("bãi đỗ xe", "parking"),
    ("bai do xe", "parking"),
    ("gửi xe", "parking"),
    ("gui xe", "parking"),
    ("gara", "parking"),
    ("garage", "parking"),
    ("bếp", "kitchen"),
    ("bep", "kitchen"),
    ("có bếp", "kitchen"),
    ("co bep", "kitchen"),
    ("nhà bếp", "kitchen"),
    ("nha bep", "kitchen"),
    ("kitchen", "kitchen"),
    ("cook", "kitchen"),
    ("nấu ăn", "kitchen"),
    ("nau an", "kitchen"),
    ("wifi", "wifi"),
    ("wi-fi", "wifi"),
    ("có wifi", "wifi"),
    ("co wifi", "wifi"),
    ("internet", "wifi"),
    ("mạng", "wifi"),
    ("mang", "wifi"),
    ("hồ bơi", "pool"),
    ("ho boi", "pool"),
    ("có hồ bơi", "pool"),
    ("co ho boi", "pool"),
    ("bể bơi", "pool"),
    ("be boi", "pool"),
    ("có bể bơi", "pool"),
    ("co be boi", "pool"),
    ("swimming pool", "pool"),
    ("pool", "pool"),
    ("điều hòa", "air_conditioner"),
    ("dieu hoa", "air_conditioner"),
    ("có điều hòa", "air_conditioner"),
    ("co dieu hoa", "air_conditioner"),
    ("máy lạnh", "air_conditioner"),
    ("may lanh", "air_conditioner"),
    ("có máy lạnh", "air_conditioner"),
    ("co may lanh", "air_conditioner"),
    ("aircon", "air_conditioner"),
    ("ac", "air_conditioner"),
    ("máy giặt", "washing_machine"),
    ("may giat", "washing_machine"),
    ("có máy giặt", "washing_machine"),
    ("co may giat", "washing_machine"),
    ("giặt đồ", "washing_machine"),
    ("giat do", "washing_machine"),
    ("washing machine", "washing_machine"),
    ("laundry", "washing_machine"),
)

GENERIC_LODGING_PHRASES: tuple[str, ...] = (
    "chỗ ở",
    "chổ ở",
    "cho o",
    "nơi ở",
    "noi o",
    "nhà ở",
    "nha o",
    "tìm nhà",
    "tim nha",
    "kiếm nhà",
    "kiem nha",
    "nhà hay",
    "nha hay",
    "nhà hoặc",
    "nha hoac",
    "tìm phòng",
    "tim phong",
    "phòng ở",
    "phong o",
    "nơi nghỉ",
    "noi nghi",
    "chỗ nghỉ",
    "cho nghi",
    "lưu trú",
    "luu tru",
)

GENERIC_SINGLE_LOCATION_TOKENS: frozenset[str] = frozenset(
    {
        "nha",
        "cho o",
        "cho",
        "noi o",
        "phong",
        "phong o",
        "khach san",
        "homestay",
        "hostel",
        "can ho",
        "bep",
        "wifi",
        "parking",
        "ho boi",
        "san bay",
        "airport",
        "dai hoc",
        "may giat",
        "dieu hoa",
        "may lanh",
        "do",
        "do nhe",
        "day",
        "day nhe",
        "day a",
        "day nha",
        "kia",
        "gan do",
        "gan day",
    }
)

AMBIGUOUS_LOCATION_PHRASES: frozenset[str] = frozenset(
    {
        "dai hoc",
        "truong hoc",
        "san bay",
        "airport",
        "nha",
        "bep",
        "lang",
        "lang dai hoc",
        "dai hoc bach khoa",
    }
)

AMBIGUOUS_LOCATION_QUESTIONS = {
    "dai hoc": "Bạn muốn tìm gần trường đại học nào hoặc ở thành phố nào?",
    "truong hoc": "Bạn muốn tìm gần trường học nào hoặc ở thành phố nào?",
    "san bay": "Bạn muốn tìm gần sân bay nào?",
    "airport": "Bạn muốn tìm gần sân bay nào?",
    "lang dai hoc": "Bạn muốn Làng Đại học ở TP.HCM/Thủ Đức hay khu vực nào khác?",
    "dai hoc bach khoa": "Bạn muốn Đại học Bách Khoa TP.HCM hay Hà Nội?",
}

AMENITY_TRIGGERS = (
    "co",
    "can",
    "muon",
    "yeu cau",
    "co them",
    "phai co",
)

LOCATION_CUE_PATTERN = re.compile(
    r"\b(?:gần|gan|quanh|xung quanh|ở gần|o gan|cạnh|canh|kề|ke|sát|sat|tại|tai|ở|o|khu vực|khu vuc|"
    r"quanh khu|gần khu|gan khu|gần địa điểm|gan dia diem|cách|cach|near|around|close to|in|at)\b",
    re.IGNORECASE,
)

LOCATION_TAIL_SPLIT_PATTERN = re.compile(
    r"\b(?:dưới|duoi|tối đa|toi da|tầm|tam|for|không cần|khong can|cần|can|"
    r"cho\s+(?:nhóm|nhom|group|\d+|một|mot|hai|ba|bốn|bon|năm|nam|sáu|sau|bảy|bay|tám|tam|chín|chin|mười|muoi)|"
    r"budget|giá|gia|"
    r"với|voi|có thêm|co them|phải có|phai co|yêu cầu|yeu cau|"
    r"trong\s+\d+(?:[.,]\d+)?\s*(?:km|kilomet|kilometer|kilometre|cây)|"
    r"trong\s+\d+(?:[.,]\d+)?\s*cay|"
    r"bán kính|ban kinh|phạm vi|pham vi|"
    r"có\s+(?:parking|wifi|bếp|hồ|chỗ|bãi|máy)|co\s+(?:parking|wifi|bep|ho|cho|bai|may))\b",
    re.IGNORECASE,
)
RADIUS_UNIT_PATTERN = r"km|kilomet|kilometer|kilometre|kilometers|kilometres|cây|cay"

DISTRICT_WORD_PATTERN = (
    r"muoi\s+(?:mot|hai)|eleven|twelve|"
    r"mot|hai|ba|bon|tu|nam|sau|bay|tam|chin|muoi|"
    r"one|two|three|four|five|six|seven|eight|nine|ten"
)

# Pattern nhận diện địa chỉ cụ thể cần geocode (không dùng alias matching).
# Bao gồm: "[số]/[số] đường..." | "hẻm [số]/[số] [tên]" | "[số] ... street"
_STREET_ADDRESS_RE = re.compile(
    r"^(?:"
    r"(?:so\s+)?\d{1,5}(?:/\d+[a-z]?)?\s+(?:duong|pho|hem|ngo|ngach|alley|street)\s+\w"
    r"|(?:hem|ngo|ngach)\s+\d{1,5}(?:/\d+[a-z]?)?\s+\w"
    r"|\d{1,5}/\d+[a-z]?\s+\w[\w\s]{2,40},\s*(?:quan|phuong|q\.|p\.)"
    r"|\d{1,5}[a-z]\s+\w[\w\s]{2,40},\s*\w[\w\s]{1,30},\s*\w"
    r"|\d{1,5}(?:/\d+[a-z]?)?\s+\w[\w\s]{1,40}(?:street|road|lane|alley)"
    r"|\d{1,5}(?:/\d+[a-z]?)?[a-z]?\s+\w[\w\s]{4,50},\s*(?:quan|phuong|q\.|p\.)\s*\d"
    r")",
    re.IGNORECASE,
)

STRONG_PLACE_PATTERNS = (
    r"\bsan bay\b",
    r"\bdinh doc lap\b",
    r"\bdam sen\b",
    r"\bsuoi tien\b",
    r"\bsnow town\b",
    r"\bbinh quoi\b",
    r"\bvan thanh\b",
    r"\bvam sat\b",
    r"\bcan gio\b",
    r"\bcu chi\b",
    r"\bsuoi\b",
    r"\bnha tho\b",
    r"\bpho di bo\b",
    r"\bdia dao\b",
    r"\bkhu di tich\b",
    r"\bbao tang\b",
    r"\bcong vien\b",
    r"\bnha hat\b",
    r"\bben\b",
    r"\bham\b",
    r"\bnoc ham\b",
    r"\bmall\b",
    r"\btrung tam thuong mai\b",
    r"\bkhu do thi\b",
    r"\bkhu du lich\b",
    r"\blang du lich\b",
    r"\bnong trang\b",
    r"\bmot thoang viet nam\b",
    r"\blandmark\b",
    r"\bben thanh\b",
    r"\bcho ray\b",
    r"\bpho co\b",
    r"\bairport\b",
)

POI_NOUN_PATTERN = GENERIC_POI_NOUN_PATTERN

ANYWHERE_INTENT_PATTERN = re.compile(
    r"\b(?:o dau cung duoc|di dau cung duoc|khu nao cung duoc|cho nao cung duoc|anywhere|wherever)\b"
)

LOCATION_FILLER_PATTERN = re.compile(
    r"\b(?:toi|minh|tui|em|anh|chi|ban|muon|can|tim|kiem|tim kiem|thue|dat|book|booking|"
    r"reserve|co|va|cho minh|cho toi|giup toi|goi y|goi|y|di|doi|thanh|nhe|nha|giup|"
    r"please|want|need|find|search|rent|reserve)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class SlotSpan:
    start: int
    end: int
    text: str
    type: str
    value: Any
    priority: int

    def to_debug(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "type": self.type,
            "value": self.value,
        }


def build_slot_parse_context(text: str | None) -> dict[str, Any]:
    normalized = normalize_user_text(text or "")
    spans = _select_non_overlapping_spans(_collect_protected_spans(normalized))
    remaining = _remove_spans(normalized["normalized_text"], spans)
    detected_location = detect_location_intent(remaining)
    semantic_location = detect_semantic_location(normalized["normalized_text"])
    location_intent = (
        semantic_location
        if _should_prefer_semantic_location(semantic_location, detected_location, remaining)
        else detected_location
    )

    accommodation_types = _ordered_values(spans, "accommodation_type")
    amenities = _ordered_values(spans, "amenity")
    radius_values = [span.value for span in spans if span.type == "search_radius_km"]

    return {
        "raw_text": normalized["raw_text"],
        "normalized_text": normalized["normalized_text"],
        "no_accent_text": normalized["no_accent_text"],
        "protected_spans": [span.to_debug() for span in spans],
        "remaining_text_for_location": remaining,
        "accommodation_types": accommodation_types,
        "required_amenities": amenities,
        "search_radius_km": radius_values[0] if radius_values else None,
        "location_candidate": location_intent.get("candidate"),
        "location_candidate_confidence": location_intent.get("confidence", 0.0),
        "location_intent": location_intent,
        "should_resolve_location": bool(location_intent.get("should_resolve")),
        "geocoder_reason": location_intent.get("reason"),
    }


def find_accommodation_type_spans(text: str | None) -> list[SlotSpan]:
    normalized = normalize_user_text(text or "")
    spans = _find_alias_spans(normalized, TYPE_ALIASES, "accommodation_type", priority=10)
    spans.extend(_find_homestay_typo_spans(normalized))
    return _select_non_overlapping_spans(spans)


def find_amenity_spans(text: str | None) -> list[SlotSpan]:
    normalized = normalize_user_text(text or "")
    spans = _find_alias_spans(normalized, AMENITY_ALIASES, "amenity", priority=20)
    return _select_non_overlapping_spans(spans)


def is_amenity_only_query(text: str | None) -> bool:
    normalized = normalize_user_text(text or "")
    spans = _select_non_overlapping_spans(_find_alias_spans(normalized, AMENITY_ALIASES, "amenity", priority=20))
    if not spans:
        return False
    remaining = _remove_spans(normalized["normalized_text"], spans)
    remaining_key = normalize_key(remaining)
    remaining_key = LOCATION_FILLER_PATTERN.sub(" ", remaining_key)
    return not re.sub(r"\s+", " ", remaining_key).strip()


def detect_location_intent(remaining_text: str | None) -> dict[str, Any]:
    text = clean_location_candidate_phrase(remaining_text, strip_leading_cues=False)
    norm = normalize_key(text)
    if not norm:
        return _blocked_location_intent("blocked_by_protected_span")
    without_filler = LOCATION_FILLER_PATTERN.sub(" ", norm)
    stripped_without_filler = re.sub(r"\s+", " ", without_filler).strip()
    if not stripped_without_filler:
        return _blocked_location_intent("blocked_by_protected_span")
    if ANYWHERE_INTENT_PATTERN.search(norm):
        return _blocked_location_intent("explicit_anywhere")

    # Địa chỉ cụ thể dạng "[số] đường/phố/hẻm [tên]" → geocode thẳng,
    # không cần alias matching (tránh nhầm tên đường với tên phường/quận).
    if _STREET_ADDRESS_RE.match(stripped_without_filler):
        return {
            "should_resolve": True,
            "candidate": text,
            "resolve_text": text,
            "confidence": 0.95,
            "reason": "street_address_phrase",
            "mode_hint": "near_anchor",
            "is_address": True,
        }

    ambiguous = ambiguous_location_intent(text)
    if ambiguous:
        return ambiguous

    if stripped_without_filler in _blocked_phrase_keys():
        return _blocked_location_intent("blocked_by_protected_span")

    if is_blocked_location_phrase(text):
        return _blocked_location_intent("blocked_by_generic_slot_phrase")

    cue_prefix, cue, cue_candidate = _location_cue_parts(text)
    if cue_candidate:
        ambiguous = ambiguous_location_intent(cue_candidate)
        if ambiguous:
            return ambiguous
        if is_blocked_location_phrase(cue_candidate):
            return _blocked_location_intent("blocked_by_protected_span")
        if cue in {"o", "tai", "in", "at", "khu vuc"}:
            resolve_text = text if cue_prefix and _is_strong_place_phrase(cue_prefix) else cue_candidate
            if _has_poi_noun(cue_candidate):
                return {
                    "should_resolve": True,
                    "candidate": cue_candidate,
                    "resolve_text": resolve_text,
                    "confidence": 0.9,
                    "reason": "strong_near_anchor_or_place_phrase",
                    "mode_hint": "near_anchor",
                }
            return {
                "should_resolve": True,
                "candidate": cue_candidate,
                "resolve_text": resolve_text,
                "confidence": 0.9,
                "reason": "clear_area_match",
                "mode_hint": "area",
            }
        if _has_clear_area_hint(normalize_key(cue_candidate)) and not _has_poi_noun(cue_candidate):
            return {
                "should_resolve": True,
                "candidate": cue_candidate,
                "resolve_text": cue_candidate,
                "confidence": 0.9,
                "reason": "clear_area_match",
                "mode_hint": "area",
            }
        resolve_text = text if cue_prefix and _is_strong_place_phrase(cue_prefix) else cue_candidate
        return {
            "should_resolve": True,
            "candidate": cue_candidate,
            "resolve_text": resolve_text,
            "confidence": 0.9,
            "reason": "strong_near_anchor_or_place_phrase",
            "mode_hint": "near_anchor",
        }

    if _has_poi_noun(norm):
        standalone = _standalone_place_phrase(text)
        if standalone and _has_standalone_place_shape(standalone):
            return {
                "should_resolve": True,
                "candidate": standalone,
                "resolve_text": standalone,
                "confidence": 0.82,
                "reason": "strong_near_anchor_or_place_phrase",
                "mode_hint": "near_anchor",
            }

    if _has_clear_area_hint(norm):
        return {
            "should_resolve": True,
            "candidate": text,
            "resolve_text": text,
            "confidence": 0.9,
            "reason": "clear_area_match",
            "mode_hint": "area",
        }

    standalone = _standalone_place_phrase(text)
    if standalone and (_is_strong_place_phrase(standalone) or _has_standalone_place_shape(standalone)):
        return {
            "should_resolve": True,
            "candidate": standalone,
            "resolve_text": standalone,
            "confidence": 0.82 if _is_strong_place_phrase(standalone) else 0.72,
            "reason": "strong_near_anchor_or_place_phrase",
            "mode_hint": "near_anchor",
        }

    return _blocked_location_intent("no_location_intent")


def ambiguous_location_intent(text: str | None) -> dict[str, Any] | None:
    norm = normalize_key(text or "")
    norm = re.sub(r"[^\w\s]", " ", norm, flags=re.UNICODE)
    norm = re.sub(r"\s+", " ", norm).strip()
    if not norm:
        return None
    key = _ambiguous_location_key(norm)
    if not key:
        return None
    return {
        "should_resolve": False,
        "candidate": _display_ambiguous_candidate(key),
        "resolve_text": "",
        "confidence": 0.45,
        "reason": "ambiguous_location",
        "mode_hint": "unknown",
        "ambiguous_location": True,
        "ambiguous_location_question": AMBIGUOUS_LOCATION_QUESTIONS.get(
            key,
            "Bạn muốn tìm khu vực hoặc địa điểm nào rõ hơn không?",
        ),
        "suggested_places": _ambiguous_suggestions(key),
    }


def is_ambiguous_location_phrase(text: str | None) -> bool:
    norm = normalize_key(text or "")
    norm = re.sub(r"[^\w\s]", " ", norm, flags=re.UNICODE)
    norm = re.sub(r"\s+", " ", norm).strip()
    return bool(_ambiguous_location_key(norm))


def is_blocked_location_phrase(text: str | None) -> bool:
    norm = normalize_key(text or "")
    norm = re.sub(r"[^\w\s]", " ", norm)
    norm = re.sub(r"\s+", " ", norm).strip()
    if not norm:
        return True

    if norm in _blocked_phrase_keys():
        return True

    for trigger in AMENITY_TRIGGERS:
        if norm == trigger:
            return True
        if norm.startswith(f"{trigger} "):
            tail = norm[len(trigger) :].strip()
            if tail in _blocked_phrase_keys():
                return True

    return False


def _collect_protected_spans(normalized: dict[str, Any]) -> list[SlotSpan]:
    spans: list[SlotSpan] = []
    spans.extend(_find_budget_spans(normalized))
    spans.extend(_find_guest_count_spans(normalized))
    spans.extend(_find_trip_days_spans(normalized))
    spans.extend(_find_radius_spans(normalized))
    spans.extend(_find_alias_spans(normalized, TYPE_ALIASES, "accommodation_type", priority=10))
    spans.extend(_find_homestay_typo_spans(normalized))
    spans.extend(_find_alias_spans(normalized, AMENITY_ALIASES, "amenity", priority=20))
    spans.extend(_find_alias_spans(normalized, PRIORITY_MAP.items(), "priority", priority=60))
    spans.extend(_find_alias_spans(normalized, SPECIAL_REQUIREMENT_MAP.items(), "special_requirement", priority=70))
    spans.extend(_find_generic_lodging_spans(normalized))
    return spans


def _find_alias_spans(
    normalized: dict[str, Any],
    aliases: Iterable[tuple[str, str]],
    span_type: str,
    *,
    priority: int,
) -> list[SlotSpan]:
    haystack = normalized["no_accent_text"]
    display = normalized["normalized_text"]
    spans: list[SlotSpan] = []
    alias_items = sorted(
        ((_alias_key(alias), value) for alias, value in aliases),
        key=lambda item: len(item[0]),
        reverse=True,
    )
    for alias_key, value in alias_items:
        if not alias_key:
            continue
        for match in re.finditer(rf"(?<!\w){re.escape(alias_key)}(?!\w)", haystack):
            spans.append(
                SlotSpan(
                    start=match.start(),
                    end=match.end(),
                    text=display[match.start() : match.end()] or match.group(0),
                    type=span_type,
                    value=value,
                    priority=priority,
                )
            )
    return spans


def _find_homestay_typo_spans(normalized: dict[str, Any]) -> list[SlotSpan]:
    spans: list[SlotSpan] = []
    haystack = normalized["no_accent_text"]
    display = normalized["normalized_text"]
    for match in re.finditer(r"\b\w+\b", haystack):
        token = match.group(0)
        if not (5 <= len(token) <= 10):
            continue
        if token in {"homestay", "homstay", "homtay", "honestay", "homestate"}:
            continue
        score = difflib.SequenceMatcher(None, token, "homestay").ratio()
        if score < 0.76:
            continue
        spans.append(
            SlotSpan(
                start=match.start(),
                end=match.end(),
                text=display[match.start() : match.end()] or token,
                type="accommodation_type",
                value="homestay",
                priority=10,
            )
        )
    return spans


def _find_generic_lodging_spans(normalized: dict[str, Any]) -> list[SlotSpan]:
    spans = _find_alias_spans(
        normalized,
        ((phrase, "generic_lodging_phrase") for phrase in GENERIC_LODGING_PHRASES),
        "generic_lodging_phrase",
        priority=50,
    )
    norm = normalized["no_accent_text"].strip()
    if norm == "nha":
        spans.append(
            SlotSpan(
                start=0,
                end=len(norm),
                text=normalized["normalized_text"],
                type="generic_lodging_phrase",
                value="generic_lodging_phrase",
                priority=50,
            )
        )
    return spans


def _find_budget_spans(normalized: dict[str, Any]) -> list[SlotSpan]:
    patterns = (
        rf"(?<!\d)\d+(?:[.,]\d+)?\s*(?:-|den|toi|~)\s*\d+(?:[.,]\d+)?\s*(?:{MONEY_UNITS_PATTERN})(?!\w)",
        rf"(?<!\d)\d+(?:[.,]\d+)?\s*(?:{MONEY_UNITS_PATTERN})\s*(?:-|den|toi|~)\s*"
        rf"\d+(?:[.,]\d+)?\s*(?:{MONEY_UNITS_PATTERN})?(?!\w)",
        rf"(?<!\d)\d+\s*(?:tr|trieu|m|cu|million|mil|mio)\s*\d{{1,2}}(?!\d)",
        rf"(?<!\d)\d+(?:[.,]\d+)?\s*(?:{MONEY_UNITS_PATTERN})(?!\w)",
        r"(?<!\d)\d{6,9}(?!\d)",
    )
    return _regex_spans(normalized, patterns, "budget", "budget", priority=30)


def _find_guest_count_spans(normalized: dict[str, Any]) -> list[SlotSpan]:
    patterns = (
        rf"(?<!\d)(?:cho|for)?\s*(?:{COUNT_TOKEN})\s*(?:nguoi|ng|dua|khach|guest|guests|people|pax|person|persons)\b",
        rf"(?<!\d)(?:{COUNT_TOKEN})\s*adults?\b",
    )
    return _regex_spans(normalized, patterns, "guest_count", "guest_count", priority=40)


def _find_trip_days_spans(normalized: dict[str, Any]) -> list[SlotSpan]:
    patterns = (
        rf"(?<!\d)(?:{COUNT_TOKEN})\s*(?:ngay|ngày|dem|đêm|days?|nights?)\b",
    )
    return _regex_spans(normalized, patterns, "trip_days", "trip_days", priority=45)


def _find_radius_spans(normalized: dict[str, Any]) -> list[SlotSpan]:
    patterns = (
        rf"\b(?:trong|bán\s+kính|ban\s+kinh|phạm\s+vi|pham\s+vi)\s*(\d+(?:[.,]\d+)?)\s*(?:{RADIUS_UNIT_PATTERN})\b",
        rf"\b(\d+(?:[.,]\d+)?)\s*(?:{RADIUS_UNIT_PATTERN})\b",
    )
    haystack = normalized["no_accent_text"]
    display = normalized["normalized_text"]
    spans: list[SlotSpan] = []
    for pattern in patterns:
        for match in re.finditer(pattern, haystack, flags=re.IGNORECASE):
            value = _radius_value(match.group(1))
            if value is None:
                continue
            spans.append(
                SlotSpan(
                    start=match.start(),
                    end=match.end(),
                    text=display[match.start() : match.end()] or match.group(0),
                    type="search_radius_km",
                    value=value,
                    priority=35,
                )
            )
    return spans


def _regex_spans(
    normalized: dict[str, Any],
    patterns: Iterable[str],
    span_type: str,
    value: Any,
    *,
    priority: int,
) -> list[SlotSpan]:
    haystack = normalized["no_accent_text"]
    display = normalized["normalized_text"]
    spans: list[SlotSpan] = []
    for pattern in patterns:
        for match in re.finditer(pattern, haystack, flags=re.IGNORECASE):
            spans.append(
                SlotSpan(
                    start=match.start(),
                    end=match.end(),
                    text=display[match.start() : match.end()] or match.group(0),
                    type=span_type,
                    value=value,
                    priority=priority,
                )
            )
    return spans


def _select_non_overlapping_spans(spans: Iterable[SlotSpan]) -> list[SlotSpan]:
    selected: list[SlotSpan] = []
    for span in sorted(spans, key=lambda item: (item.priority, -(item.end - item.start), item.start)):
        if any(span.start < existing.end and span.end > existing.start for existing in selected):
            continue
        selected.append(span)
    return sorted(selected, key=lambda item: item.start)


def _remove_spans(text: str, spans: list[SlotSpan]) -> str:
    if not text or not spans:
        return " ".join((text or "").split())
    chars = list(text)
    for span in spans:
        for index in range(max(0, span.start), min(len(chars), span.end)):
            chars[index] = " "
    return re.sub(r"\s+", " ", "".join(chars)).strip()


def _ordered_values(spans: Iterable[SlotSpan], span_type: str) -> list[str]:
    values: list[str] = []
    for span in spans:
        if span.type != span_type:
            continue
        value = str(span.value)
        if value not in values:
            values.append(value)
    return values


def _location_cue_parts(text: str) -> tuple[str | None, str | None, str | None]:
    match = LOCATION_CUE_PATTERN.search(text or "")
    if not match:
        return None, None, None
    prefix = (text or "")[: match.start()].strip(" ,.;:")
    cue = normalize_key(match.group(0))
    tail = (text or "")[match.end() :].strip()
    tail = LOCATION_TAIL_SPLIT_PATTERN.split(tail, maxsplit=1)[0]
    tail = strip_location_tails(tail)
    tail = clean_location_candidate_phrase(tail)
    return prefix or None, cue or None, tail or None


def _standalone_place_phrase(text: str) -> str | None:
    cleaned = clean_location_candidate_phrase(text)
    if not cleaned:
        return None
    norm = normalize_key(cleaned)
    without_filler = LOCATION_FILLER_PATTERN.sub(" ", norm)
    without_filler = re.sub(r"\s+", " ", without_filler).strip()
    if not without_filler:
        return None
    token_count = len(re.findall(r"\w+", without_filler))
    if token_count < 2:
        return None
    return cleaned


def _has_standalone_place_shape(text: str) -> bool:
    norm = normalize_key(text)
    if is_blocked_location_phrase(norm):
        return False
    if _has_clear_area_hint(norm) and not _has_poi_noun(norm):
        return False
    tokens = re.findall(r"\w+", norm)
    if len(tokens) < 2:
        return False
    if any(
        token in {"khach", "san", "hotel", "homestay", "hostel", "can", "ho", "parking", "wifi", "ngay", "dem"}
        for token in tokens
    ):
        return False
    return True


def _has_poi_noun(text: str | None) -> bool:
    return has_concrete_place_noun(text)


def _should_prefer_semantic_location(
    semantic_location: dict[str, Any] | None,
    detected_location: dict[str, Any],
    remaining_text: str | None,
) -> bool:
    if not semantic_location:
        return False
    if not detected_location.get("should_resolve"):
        return True
    if semantic_location.get("mode_hint") == "city_center":
        phrase = detected_location.get("candidate") or detected_location.get("resolve_text") or remaining_text
        return not has_concrete_place_noun(phrase)
    return False


def _radius_value(value: str | None) -> float | None:
    try:
        radius = float(str(value or "").replace(",", "."))
    except (TypeError, ValueError):
        return None
    if 0.1 <= radius <= 50:
        return round(radius, 2)
    return None


def _has_clear_area_hint(norm: str) -> bool:
    if re.search(r"\b(?:quan|q\.?|district|dist)\s*(?:\d{1,2})(?!\d)\b", norm):
        return True
    if re.search(rf"\b(?:quan|q\.?|district|dist)\s+({DISTRICT_WORD_PATTERN})(?!\w)\b", norm):
        return True

    for alias in _clear_area_aliases():
        if re.search(rf"(?<!\w){re.escape(alias)}(?!\w)", norm):
            return True
    return False


def _is_strong_place_phrase(text: str) -> bool:
    norm = normalize_key(text)
    if is_blocked_location_phrase(norm):
        return False
    if len(re.findall(r"\w+", norm)) < 2:
        return False
    return any(re.search(pattern, norm) for pattern in STRONG_PLACE_PATTERNS)


def _blocked_location_intent(reason: str) -> dict[str, Any]:
    return {
        "should_resolve": False,
        "candidate": None,
        "resolve_text": "",
        "confidence": 0.0,
        "reason": reason,
        "mode_hint": "unknown",
        "location_intent": "none",
        "geocoder_called": False,
    }


def _ambiguous_location_key(norm: str) -> str | None:
    if norm in AMBIGUOUS_LOCATION_PHRASES:
        return norm
    if re.fullmatch(r"dai hoc(?:\s+(?:di|nhe|nha|a))?", norm):
        return "dai hoc"
    if re.fullmatch(r"truong hoc(?:\s+(?:di|nhe|nha|a))?", norm):
        return "truong hoc"
    if re.fullmatch(r"san bay(?:\s+(?:di|nhe|nha|a))?", norm):
        return "san bay"
    if re.fullmatch(r"airport(?:\s+(?:di|nhe|nha|a))?", norm):
        return "airport"
    if re.fullmatch(r"lang dai hoc(?:\s+(?:di|nhe|nha|a))?", norm):
        return "lang dai hoc"
    if re.fullmatch(r"dai hoc bach khoa(?:\s+(?:di|nhe|nha|a))?", norm):
        return "dai hoc bach khoa"
    return None


def _display_ambiguous_candidate(key: str) -> str:
    return {
        "dai hoc": "Đại học",
        "truong hoc": "Trường học",
        "san bay": "Sân bay",
        "airport": "Airport",
        "lang dai hoc": "Làng đại học",
        "dai hoc bach khoa": "Đại học Bách Khoa",
    }.get(key, key)


def _ambiguous_suggestions(key: str) -> list[dict[str, str]]:
    if key == "dai hoc bach khoa":
        return [
            {"label": "Đại học Bách Khoa TP.HCM", "value": "Đại học Bách Khoa TP.HCM"},
            {"label": "Đại học Bách Khoa Hà Nội", "value": "Đại học Bách Khoa Hà Nội"},
        ]
    if key == "lang dai hoc":
        return [
            {"label": "Làng Đại học Quốc gia TP.HCM", "value": "Làng Đại học Quốc gia TP.HCM"},
            {"label": "Thủ Đức / Dĩ An", "value": "Thủ Đức"},
        ]
    return []


@lru_cache(maxsize=1)
def _clear_area_aliases() -> tuple[str, ...]:
    aliases: set[str] = set()
    for location in load_supported_locations():
        for alias in [location.get("canonical_name") or "", *(location.get("aliases") or [])]:
            alias_key = normalize_key(alias)
            if not alias_key:
                continue
            compact = alias_key.replace(" ", "")
            if any(char.isdigit() for char in alias_key) or len(compact) >= 3:
                aliases.add(alias_key)
    return tuple(sorted(aliases, key=len, reverse=True))


@lru_cache(maxsize=1)
def _blocked_phrase_keys() -> frozenset[str]:
    keys: set[str] = set(GENERIC_SINGLE_LOCATION_TOKENS)
    for alias, _value in TYPE_ALIASES:
        keys.add(_alias_key(alias))
    for alias, _value in AMENITY_ALIASES:
        keys.add(_alias_key(alias))
    for phrase in GENERIC_LODGING_PHRASES:
        keys.add(_alias_key(phrase))
    return frozenset(key for key in keys if key)


def _alias_key(alias: str) -> str:
    return normalize_user_text(alias)["no_accent_text"]
