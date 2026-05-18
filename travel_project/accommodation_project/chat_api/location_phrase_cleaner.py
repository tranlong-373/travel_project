from __future__ import annotations

import re

from .normalizers import normalize_key


# Generic place-category words, not concrete place names. They help the parser
# avoid treating phrases like "buu dien trung tam..." as abstract city-center intent.
GENERIC_POI_NOUNS: tuple[str, ...] = (
    "trung tam thuong mai",
    "pho di bo",
    "post office",
    "buu dien",
    "cong vien",
    "bao tang",
    "nha hat",
    "nha tho",
    "ben xe",
    "ben",
    "ham",
    "noc ham",
    "san bay",
    "khu do thi",
    "khu di tich",
    "khu du lich",
    "lang du lich",
    "dia dao",
    "mall",
    "plaza",
    "market",
    "theatre",
    "museum",
    "park",
    "airport",
    "station",
    "hospital",
    "benh vien",
    "truong",
    "dai hoc",
    "chua",
    "pagoda",
    "toa nha",
    "tower",
)

GENERIC_POI_NOUN_PATTERN = re.compile(
    r"\b(?:"
    + "|".join(re.escape(term) for term in sorted(GENERIC_POI_NOUNS, key=len, reverse=True))
    + r")\b"
)

ACTION_FILLER_PREFIX_PATTERN = re.compile(
    r"^(?:"
    r"tôi|toi|mình|minh|tui|em|anh|chị|chi|bạn|ban|"
    r"tôi\s+muốn|toi\s+muon|mình\s+muốn|minh\s+muon|tôi\s+cần|toi\s+can|mình\s+cần|minh\s+can|"
    r"muốn|muon|cần|can|tìm|tim|kiếm|kiem|tìm\s+kiếm|tim\s+kiem|thuê|thue|đặt|dat|book|booking|reserve|"
    r"cho\s+tôi|cho\s+toi|cho\s+mình|cho\s+minh|giúp\s+tôi|giup\s+toi|giúp\s+mình|giup\s+minh|gợi\s+ý|goi\s+y|"
    r"want|need|find|search|rent|please"
    r")\s+",
    re.IGNORECASE,
)

LOCATION_CUE_PREFIX_PATTERN = re.compile(
    r"^(?:"
    r"gần|gan|quanh|xung\s+quanh|ở\s+gần|o\s+gan|cạnh|canh|kề|ke|sát|sat|tại|tai|ở|o|khu\s+vực|khu\s+vuc|"
    r"gần\s+khu|gan\s+khu|quanh\s+khu|gần\s+địa\s+điểm|gan\s+dia\s+diem|cách|cach|near|around|close\s+to|in|at"
    r")\s+",
    re.IGNORECASE,
)

LOCATION_LEADING_PREFIX_PATTERN = re.compile(
    r"^(?:khu\s+vực|khu\s+vuc|địa\s+điểm|dia\s+diem|place)\s+",
    re.IGNORECASE,
)

TRAILING_FILLER_PATTERN = re.compile(
    r"\s+(?:giúp\s+tôi|giup\s+toi|giúp\s+mình|giup\s+minh|nhé|nhe|nha|ạ|a|đi|di|please)$",
    re.IGNORECASE,
)

LOCATION_TAIL_SPLIT_PATTERN = re.compile(
    r"\b(?:dưới|duoi|tối\s+đa|toi\s+da|tầm|tam|for|không\s+cần|khong\s+can|cần|can|"
    r"cho\s+(?:nhóm|nhom|group|\d+|một|mot|hai|ba|bốn|bon|năm|nam|sáu|sau|bảy|bay|tám|tam|chín|chin|mười|muoi)|"
    r"budget|giá|gia|với|voi|"
    r"có\s+thêm|co\s+them|phải\s+có|phai\s+co|yêu\s+cầu|yeu\s+cau|"
    r"có\s+(?:parking|wifi|bếp|bep|hồ|ho|chỗ|cho|bãi|bai|máy|may)|co\s+(?:parking|wifi|bep|ho|cho|bai|may)|"
    r"trong\s+\d+(?:[.,]\d+)?\s*(?:km|kilomet|kilometer|kilometre|cây|cay)|"
    r"bán\s+kính|ban\s+kinh|phạm\s+vi|pham\s+vi)\b",
    re.IGNORECASE,
)

RADIUS_PATTERN = re.compile(
    r"\b(?:(?:trong|ban\s+kinh|pham\s+vi)\s*)?\d+(?:[.,]\d+)?\s*"
    r"(?:km|kilomet|kilometer|kilometre|kilometers|kilometres|cây|cay)\b",
    re.IGNORECASE,
)


def clean_location_candidate_phrase(value: str | None, *, strip_leading_cues: bool = True) -> str:
    text = " ".join(str(value or "").replace("\n", " ").split())
    text = text.strip(" ,.;:-")
    if not text:
        return ""

    text = _strip_leading_noise(text, strip_leading_cues=strip_leading_cues)
    text = _strip_location_tail(text)
    text = _strip_leading_noise(text, strip_leading_cues=strip_leading_cues)
    text = _strip_location_tail(text)
    text = TRAILING_FILLER_PATTERN.sub("", text)
    text = re.sub(r"\s+", " ", text).strip(" ,.;:-")
    return text


def cleaned_location_variants(value: str | None) -> list[str]:
    variants: list[str] = []
    for strip_cues in (False, True):
        cleaned = clean_location_candidate_phrase(value, strip_leading_cues=strip_cues)
        _append_unique(variants, cleaned)

    key = normalize_key(value or "")
    if key and key not in variants:
        _append_unique(variants, key)
    return variants


def has_concrete_place_noun(value: str | None) -> bool:
    raw = str(value or "").lower()
    if re.search(r"\bchợ\b", raw):
        return True
    norm = normalize_key(raw)
    if re.search(r"\bcho\s+(?!nao|nào|toi|tôi|minh|mình|nhom|nhóm|nguoi|người|ng|de|để|o|ở|co|có)\w+", norm):
        return True
    return bool(GENERIC_POI_NOUN_PATTERN.search(norm))


def strip_location_tails(value: str | None) -> str:
    return _strip_location_tail(" ".join(str(value or "").split()))


def _strip_location_tail(value: str) -> str:
    text = LOCATION_TAIL_SPLIT_PATTERN.split(value, maxsplit=1)[0]
    text = RADIUS_PATTERN.sub(" ", text)
    return re.sub(r"\s+", " ", text).strip(" ,.;:-")


def _strip_leading_noise(value: str, *, strip_leading_cues: bool) -> str:
    text = value
    previous = None
    while previous != text:
        previous = text
        text = ACTION_FILLER_PREFIX_PATTERN.sub("", text).strip()
        text = LOCATION_LEADING_PREFIX_PATTERN.sub("", text).strip()
        if strip_leading_cues:
            text = LOCATION_CUE_PREFIX_PATTERN.sub("", text).strip()
    return text


def _append_unique(values: list[str], value: str | None) -> None:
    cleaned = re.sub(r"\s+", " ", str(value or "")).strip()
    if cleaned and cleaned not in values:
        values.append(cleaned)
