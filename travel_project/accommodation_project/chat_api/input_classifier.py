"""
3-class input classifier for chat accommodation search.

Classifies user text into:
  hotel_name  — searching a specific hotel by name (e.g. "Khách sạn Mường Thanh")
  address     — a specific street address (e.g. "123 Nguyễn Huệ, Quận 1")
  landmark    — a POI / area to search near (e.g. "gần Nhà Thờ Đức Bà")

Priority chain (first match wins):
  1. DB fuzzy match ≥ HOTEL_NAME_MIN_SCORE  →  hotel_name
  2. Vietnamese address regex               →  address
  3. Default                                →  landmark (geocode downstream)
"""
from __future__ import annotations

import re
from typing import Any

from .normalizers import normalize_key

# ── tuning knobs ─────────────────────────────────────────────────────────────
HOTEL_NAME_MIN_SCORE = 88.0   # rapidfuzz WRatio threshold (raised from 85 to avoid generic "hotel" token matches like "rex hotel" → "bao minh hotel")
HOTEL_NAME_MIN_CHARS = 3      # ignore queries shorter than this

# Các từ chung bị bỏ qua khi so sánh tên khách sạn (không phải phần riêng biệt)
_STRIP_BEFORE_MATCH: frozenset[str] = frozenset({
    "khach san", "khách sạn", "ks", "hotel", "homestay", "hostel",
    "resort", "villa", "can ho", "căn hộ", "apartment", "nha nghi",
})

# ── accommodation keyword set ─────────────────────────────────────────────────
_ACC_KEYWORDS: frozenset[str] = frozenset({
    "khach san", "khách sạn", "ks", "hotel", "hotels",
    "homestay", "homstay", "home stay",
    "hostel", "nha tro", "nhà trọ", "phong tro",
    "resort", "villa", "motel",
    "can ho", "căn hộ", "apartment", "studio",
})

# ── Vietnamese address patterns ───────────────────────────────────────────────
# Ordered from most-specific to least-specific
_ADDRESS_PATTERNS: list[str] = [
    # "[số]/[số][chữ] đường/phố/hẻm/ngõ/ngách [tên]"
    # e.g. "220 Đường Nguyễn..." | "12/3 Hẻm Nguyễn..." | "120/5A Hẻm Lê..."
    r"(?:số\s+)?\d{1,5}(?:/\d+[A-Za-z]?)?\s+(?:đường|phố|hẻm|ngõ|ngách)\s+\w[\w\s]{1,50}",
    # "hẻm/ngõ/ngách [số]/[số] [tên]" — loại đường đứng trước, không có số nhà
    # e.g. "hẻm 76/27 Phan Tây Hồ" | "ngõ 100 Trần Hưng Đạo"
    r"(?:hẻm|ngõ|ngách)\s+\d{1,5}(?:/\d+[A-Za-z]?)?\s+\w[\w\s]{1,50}",
    # "[số]/[số+chữ] [tên], quận/phường" — số có slash, không có từ khóa đường
    # e.g. "120/5A Nguyễn Thị Minh Khai, Quận 3"
    r"\d{1,5}/\d+[A-Za-z]?\s+\w[\w\s]{2,40},\s*(?:quận|phường|q\.|p\.)\s*\w",
    # "[số+chữ] [tên], [quận/phường/thành phố]" — số nhà có suffix chữ cái
    # e.g. "118C Bùi Thị Xuân, Bến Thành, Hồ Chí Minh"
    r"\d{1,5}[A-Za-z]\s+\w[\w\s]{2,40},\s*\w[\w\s]{1,30},\s*\w",
    # "[số] [tên] đường/phố/hẻm/ngõ" — tên trước, loại đường sau
    r"(?:số\s+)?\d{1,5}\s*/?\s*\d*[A-Za-z]?\s+[\w\s]{2,40}(?:đường|phố|phường|quận|huyện|hẻm|ngõ|ngách)[\w\s,/.]{0,40}",
    # địa chỉ đầy đủ có phường/xã + quận/huyện
    r"(?:đường|phố)\s+\w[\w\s]{1,30},\s*(?:phường|xã|p\.|x\.)\s*\w[\w\s]{0,20},\s*(?:quận|huyện|q\.|h\.)",
    # "đường X, phường/quận Y ..."
    r"(?:đường|phố)\s+\w[\w\s]{1,30},\s*(?:phường|quận|p\.|q\.)[\w\s,/.]{0,30}",
    # "[số] [tên] Street/Road/Lane/Alley — tiếng Anh
    r"\d{1,5}(?:/\d+[A-Za-z]?)?\s+\w[\w\s]{1,40}(?:street|road|lane|alley|avenue|blvd|st\.)",
    # "[số/số+chữ] [tên đường], Quận/Phường N" — số nhà + tên đường + quận không có từ khóa đường
    # e.g. "90 Nguyễn Thị Minh Khai, Quận 3" | "127 Pasteur, Quận 3" | "86/10 Nguyễn Thông, Quận 3"
    r"\d{1,5}(?:/\d+[A-Za-z]?)?[A-Za-z]?\s+\w[\w\s]{4,50},\s*(?:quận|phường|q\.|p\.)\s*\d",
    # "P.1, Q.3"  or  "Phường 1, Quận 3"
    r"(?:p\.|phường|phuong)\s*\d+\s*[,\s]+(?:q\.|quan|quận)\s*\d+",
    # "Quận 1, TP.HCM" – district + city
    r"(?:quận|quan|q\.?)\s*\d{1,2}\s*,\s*(?:tp\.?\s*hcm|hồ chí minh|tp\.?\s*hồ chí minh)",
    # địa chỉ có mã bưu chính 5-6 chữ số
    r"\d{1,5}(?:/\d+[A-Za-z]?)?\s+(?:đường|phố|hẻm|ngõ)\s+\w[\w\s,]{5,80},\s*(?:việt nam|vietnam|\d{5,6})",
]
_ADDRESS_RE: list[re.Pattern] = [
    re.compile(p, re.IGNORECASE | re.UNICODE) for p in _ADDRESS_PATTERNS
]

# ── stopwords that indicate "search near X", not a hotel name ─────────────────
_NEAR_CUES: frozenset[str] = frozenset({
    "gan", "gần", "quanh", "xung quanh", "canh", "cạnh", "sat", "sát",
    "near", "around", "close to", "next to",
    "khu vuc", "khu vực",
})

# ── signals that indicate a search query, not a hotel name lookup ─────────────
_SEARCH_QUERY_RE = re.compile(
    r"\b\d+\s*(?:k|tr|trieu|m|million|ngan|nghin)\b"   # budget: "500k", "1tr"
    r"|\bq\.?\s*\d{1,2}\b|\bquan\s+\d{1,2}\b"          # district: "q10", "quan 3"
    r"|\bnao\s*(?:khong|ko|k\b)?"                        # interrogative: "nào", "nào không"
    r"|\bco\s+\w+\s+nao\b"                               # "có ... nào"
    r"|\bduoi\s+\d|\btren\s+\d|\bkhoang\s+\d",          # "dưới 500k", "khoảng 800k"
    re.IGNORECASE,
)


# ── public API ────────────────────────────────────────────────────────────────

def classify_input_type(
    text: str,
    *,
    context_slots: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Classify a chat query into hotel_name, address, or landmark.

    Returns a dict:
        type            : "hotel_name" | "address" | "landmark"
        confidence      : float 0–1
        reason          : str  (debug)
        hotel_match     : dict | None   (when type == "hotel_name")
        address_phrase  : str | None    (when type == "address")
    """
    if not text or not text.strip():
        return _result("landmark", 0.3, "empty_input")

    norm = normalize_key(text)

    # ── 1. Hotel name: only attempt when query carries an accommodation keyword,
    #       no "near" preposition, and no search-query signals (budget/district/interrogative)
    if not _has_near_cue(norm) and _has_accommodation_keyword(norm) and not _SEARCH_QUERY_RE.search(norm):
        match = _fuzzy_hotel_match(norm)
        if match:
            return _result(
                "hotel_name",
                match["score"] / 100.0,
                "db_fuzzy_match",
                hotel_match=match,
            )

    # ── 2. Specific address ────────────────────────────────────────────────────
    phrase = _detect_address(text)
    if phrase:
        return _result("address", 0.90, "address_pattern", address_phrase=phrase)

    # ── 3. Default: treat as landmark / POI (geocode downstream) ──────────────
    return _result("landmark", 0.72, "default_landmark")


# ── helpers ───────────────────────────────────────────────────────────────────

def _result(
    kind: str,
    confidence: float,
    reason: str,
    *,
    hotel_match: dict[str, Any] | None = None,
    address_phrase: str | None = None,
) -> dict[str, Any]:
    return {
        "type": kind,
        "confidence": round(confidence, 4),
        "reason": reason,
        "hotel_match": hotel_match,
        "address_phrase": address_phrase,
    }


def _has_near_cue(norm: str) -> bool:
    """Return True if the text starts with or contains a 'near X' preposition."""
    for cue in _NEAR_CUES:
        if norm.startswith(cue + " ") or f" {cue} " in norm:
            return True
    return False


def _has_accommodation_keyword(norm: str) -> bool:
    return any(kw in norm for kw in _ACC_KEYWORDS)


def _detect_address(text: str) -> str | None:
    """Return the matched address fragment or None."""
    for pattern in _ADDRESS_RE:
        m = pattern.search(text)
        if m:
            return m.group(0).strip()
    return None


_STRIP_PHRASE_PATTERN = re.compile(
    r"\b(?:" + "|".join(
        re.escape(phrase) for phrase in sorted(_STRIP_BEFORE_MATCH, key=len, reverse=True)
    ) + r")\b",
    re.IGNORECASE,
)


def _strip_generic_words(norm: str) -> str:
    """Remove generic accommodation words/phrases so fuzzy matching focuses on the distinctive name.

    Strips both single tokens ("hotel", "homestay") and multi-word phrases
    ("khach san", "can ho"). Previously only single tokens worked, which
    caused queries like "Khách sạn Mường Thanh" to retain "khach san" and
    fail to match accommodations named "Muong Thanh Luxury Saigon Hotel".
    """
    result = _STRIP_PHRASE_PATTERN.sub(" ", norm)
    result = re.sub(r"\s+", " ", result).strip()
    return result if result else norm


def _fuzzy_hotel_match(norm: str) -> dict[str, Any] | None:
    """
    Fuzzy-match norm against all accommodation names in the DB.
    Returns the best match dict if score ≥ HOTEL_NAME_MIN_SCORE, else None.
    """
    if len(norm.replace(" ", "")) < HOTEL_NAME_MIN_CHARS:
        return None

    core_query = _strip_generic_words(norm)

    try:
        from accommodations.models import Accommodation

        try:
            from rapidfuzz import fuzz
            _use_rf = True
        except ImportError:
            from difflib import SequenceMatcher
            _use_rf = False

        accommodations = list(
            Accommodation.objects.only("id", "name", "accommodation_type", "area")
        )
        if not accommodations:
            return None

        best_score = 0.0
        best_acc = None

        for acc in accommodations:
            acc_norm = normalize_key(acc.name or "")
            if not acc_norm:
                continue

            core_acc = _strip_generic_words(acc_norm)

            # Skip accommodations with too-short core names (e.g. "X").
            # partial_ratio gives spurious high scores when one side is < 3 chars.
            if len(core_acc.replace(" ", "")) < 3:
                continue

            if _use_rf:
                score = max(
                    fuzz.WRatio(core_query, core_acc),
                    fuzz.partial_ratio(core_query, core_acc) * 0.90,
                    fuzz.token_set_ratio(core_query, core_acc) * 0.95,
                )
            else:
                score = SequenceMatcher(None, core_query, core_acc).ratio() * 100

            if score > best_score:
                best_score = score
                best_acc = acc

        if best_score >= HOTEL_NAME_MIN_SCORE and best_acc is not None:
            return {
                "score": round(best_score, 1),
                "accommodation_id": best_acc.id,
                "name": best_acc.name,
                "area": best_acc.area,
                "accommodation_type": best_acc.accommodation_type,
            }
    except Exception:
        pass

    return None
