from __future__ import annotations

import re

from .constants import (
    AMENITY_MAP,
    AREA_ALIASES,
    LANDMARK_ALIASES,
    NEGATION_CUES,
    NUMBER_WORDS,
    PRIORITY_MAP,
    SPECIAL_REQUIREMENT_MAP,
    TYPE_PATTERNS,
    UNSUPPORTED_TYPE_PATTERNS,
)
from .normalizers import normalize_key

MONEY_UNITS = r"k|nghin|ngan|thousand|tr|trieu|m|cu|million|mil|mio"
COUNT_TOKEN = r"\d+|mot|một|hai|ba|bon|bốn|tu|tư|nam|năm|sau|sáu|bay|bảy|tam|tám|chin|chín|muoi|mười|one|two|three|four|five|six|seven|eight|nine|ten"


def _word_to_int(token: str) -> int | None:
    token = normalize_key(token)
    if token.isdigit():
        return int(token)
    return NUMBER_WORDS.get(token)


def _append_unique(values: list[str], value: str) -> None:
    if value not in values:
        values.append(value)


def find_area_candidates(text: str) -> list[str]:
    norm = normalize_key(text)
    candidates: list[str] = []

    for raw, canonical in LANDMARK_ALIASES.items():
        raw_n = normalize_key(raw)
        if re.search(rf"(?<!\w){re.escape(raw_n)}(?!\w)", norm):
            _append_unique(candidates, canonical)

    district_patterns = [
        r"\b(?:quan|q)\s*(\d{1,2})\b",
        r"\b(?:district|dist)\s*(\d{1,2})\b",
    ]
    for pattern in district_patterns:
        for m in re.finditer(pattern, norm):
            _append_unique(candidates, f"quận {m.group(1)} tp hcm")

    for canonical, aliases in AREA_ALIASES.items():
        for alias in aliases:
            alias_n = normalize_key(alias)
            if re.search(rf"(?<!\w){re.escape(alias_n)}(?!\w)", norm):
                _append_unique(candidates, canonical)
                break

    return candidates


def _money_to_vnd(num_str: str, unit: str) -> int:
    x = float(num_str.replace(",", "."))
    unit = normalize_key(unit)

    if unit in {"k", "nghin", "ngan", "thousand"}:
        return int(x * 1_000)

    if unit in {"tr", "trieu", "m", "cu", "million", "mil", "mio"}:
        return int(x * 1_000_000)

    return int(x)


def extract_budget(text: str) -> int | None:
    norm = normalize_key(text)

    m = re.search(
        rf"(?<!\d)(\d+(?:[.,]\d+)?)\s*({MONEY_UNITS})\s*(?:-|den|toi|~)\s*(\d+(?:[.,]\d+)?)\s*({MONEY_UNITS})?",
        norm,
    )
    if m:
        left = _money_to_vnd(m.group(1), m.group(2))
        unit2 = m.group(4) or m.group(2)
        right = _money_to_vnd(m.group(3), unit2)
        return max(left, right)

    m = re.search(r"(?<!\d)(\d+)\s*(tr|trieu|m|cu|million|mil|mio)\s*(\d{1,2})(?!\d)", norm)
    if m:
        left = int(m.group(1)) * 1_000_000
        right = m.group(3)
        extra = int(right) * (100_000 if len(right) == 1 else 10_000)
        return left + extra

    m = re.search(rf"(?<!\d)(\d+(?:[.,]\d+)?)\s*({MONEY_UNITS})(?!\w)", norm)
    if m:
        return _money_to_vnd(m.group(1), m.group(2))

    m = re.search(r"(?<!\d)(\d{6,9})(?!\d)", norm)
    if m:
        return int(m.group(1))

    return None


def extract_guest_count(text: str) -> int | None:
    norm = normalize_key(text)

    m = re.search(
        rf"(?<!\d)({COUNT_TOKEN})\s*adults?\s*(?:and|&|voi|va)?\s*({COUNT_TOKEN})\s*(?:kid|kids|child|children)",
        norm,
    )
    if m:
        adult_count = _word_to_int(m.group(1))
        child_count = _word_to_int(m.group(2))
        if adult_count is not None and child_count is not None:
            return adult_count + child_count

    m = re.search(rf"(?<!\d)({COUNT_TOKEN})\s*adults?\b", norm)
    if m:
        return _word_to_int(m.group(1))

    m = re.search(
        rf"(?<!\d)({COUNT_TOKEN})\s*(nguoi|ng|dua|khach|guest|guests|people|pax|person|persons)\b",
        norm,
    )
    if m:
        return _word_to_int(m.group(1))

    m = re.search(
        rf"\b(?:for|cho)\s+({COUNT_TOKEN})(?!\s*(?:ngay|hom|dem|days?|nights?|weeks?|tuan|trieu|million|m|tr|k)\b)",
        norm,
    )
    if m:
        return _word_to_int(m.group(1))

    if re.search(r"\b(mot minh|1 minh|solo|alone|just me|by myself)\b", norm):
        return 1

    if any(
        x in norm
        for x in [
            "cap doi",
            "cặp đôi",
            "nguoi yeu",
            "người yêu",
            "ban gai",
            "bạn gái",
            "ban trai",
            "bạn trai",
            "vo chong",
            "vợ chồng",
            "me and my girlfriend",
            "me and my boyfriend",
            "my girlfriend and i",
            "my boyfriend and i",
            "for me and my girlfriend",
            "for me and my boyfriend",
            "with my girlfriend",
            "with my boyfriend",
            "minh voi ban gai",
            "mình với bạn gái",
            "minh va ban gai",
            "minh voi ban trai",
            "mình với bạn trai",
            "minh va ban trai",
            "toi va ban gai",
            "toi voi ban gai",
            "toi va ban trai",
            "toi voi ban trai",
            "minh voi me",
            "mình với mẹ",
            "minh voi bo",
            "mình với bố",
            "minh voi ba",
            "mình với ba",
            "minh voi ma",
            "mình với má",
            "voi sep",
            "với sếp",
            "couple",
            "parents",
            "my parents",
            "bo me minh",
            "bố mẹ mình",
            "ba me minh",
            "ba mẹ mình",
            "ba ma minh",
            "ba má mình",
        ]
    ):
        return 2

    return None


def extract_trip_days(text: str) -> int | None:
    norm = normalize_key(text)
    values: list[int] = []

    patterns = [
        rf"(?<!\d)({COUNT_TOKEN})\s*(ngay|hom|dem|days?|nights?)\b",
        rf"(?<!\d)({COUNT_TOKEN})\s*(tuan|weeks?)\b",
    ]

    for p in patterns:
        for m in re.finditer(p, norm):
            v = _word_to_int(m.group(1))
            if v is None:
                continue
            if m.group(2) in {"tuan", "week", "weeks"}:
                values.append(v * 7)
            else:
                values.append(v)

    return max(values) if values else None


def find_type_candidates(text: str) -> list[str]:
    lower_text = text.lower()

    matches = []
    for pattern, mapped in TYPE_PATTERNS:
        for m in re.finditer(pattern, lower_text):
            matches.append((m.start(), mapped))

    if not matches:
        return []

    # Sắp theo vị trí xuất hiện trong câu
    matches.sort(key=lambda x: x[0])

    ordered_types = []
    for _, mapped in matches:
        if mapped not in ordered_types:
            ordered_types.append(mapped)

    return ordered_types


def find_unsupported_type_candidates(text: str) -> list[str]:
    lower_text = text.lower()
    found: list[str] = []
    for pattern, mapped in UNSUPPORTED_TYPE_PATTERNS:
        if re.search(pattern, lower_text) and mapped not in found:
            found.append(mapped)
    return found


def has_type_choice_connector(text: str) -> bool:
    norm = normalize_key(text)
    choice_connectors = [
        "hoac",
        "hay",
        "or",
        "either",
        "deu duoc",
        "cung duoc",
    ]
    return any(re.search(rf"(?<!\w){re.escape(conn)}(?!\w)", norm) for conn in choice_connectors)


def extract_preferred_type(text: str) -> str | None:
    ordered_types = find_type_candidates(text)
    if not ordered_types:
        return None

    # Nếu chỉ có 1 loại thì trả luôn
    if len(ordered_types) == 1:
        return ordered_types[0]

    # Nếu có nhiều loại + có dấu hiệu lựa chọn => không chốt loại nào
    if has_type_choice_connector(text):
        return None

    # Nếu nhiều loại nhưng không phải kiểu lựa chọn, lấy loại xuất hiện đầu tiên
    return ordered_types[0]


def _is_negated(norm_text: str, start: int) -> bool:
    window = norm_text[max(0, start - 32):start]
    for boundary in [",", ".", ";", " mien co ", " nhung ", " but ", " however "]:
        pos = window.rfind(boundary)
        if pos != -1:
            window = window[pos + len(boundary):]
    return any(normalize_key(neg) in window for neg in NEGATION_CUES)


def _extract_list_from_map(text: str, mapping: dict[str, str], allow_negation: bool) -> list[str]:
    norm = normalize_key(text)
    found: list[str] = []

    items = sorted(mapping.items(), key=lambda x: len(x[0]), reverse=True)

    for raw, mapped in items:
        raw_norm = normalize_key(raw)

        for m in re.finditer(rf"(?<!\w){re.escape(raw_norm)}(?!\w)", norm):
            if allow_negation and _is_negated(norm, m.start()):
                continue
            if mapped not in found:
                found.append(mapped)
            break

    return found


def extract_required_amenities(text: str) -> list[str]:
    return _extract_list_from_map(text, AMENITY_MAP, allow_negation=True)


def extract_priorities(text: str) -> list[str]:
    return _extract_list_from_map(text, PRIORITY_MAP, allow_negation=True)


def extract_special_requirements(text: str) -> list[str]:
    return _extract_list_from_map(text, SPECIAL_REQUIREMENT_MAP, allow_negation=False)
