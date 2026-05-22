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
# Tiered thresholds by query length — short queries (e.g. "ACB") need a higher
# score because false positives are easier; long queries can be looser.
HOTEL_NAME_MIN_SCORE_LONG = 78.0   # ≥ 10 chars
HOTEL_NAME_MIN_SCORE_MED = 82.0    # 5–9 chars
HOTEL_NAME_MIN_SCORE_SHORT = 88.0  # 3–4 chars (use Jaro-Winkler)
HOTEL_NAME_MIN_CHARS = 3           # ignore queries shorter than this

# Backward-compat alias (legacy callers / tests)
HOTEL_NAME_MIN_SCORE = HOTEL_NAME_MIN_SCORE_LONG

# Show TOP-N candidates when multiple results are similarly strong
TOP_N_CANDIDATES = 4
CANDIDATE_MARGIN = 8.0   # if 2nd-best within this margin → return as candidate list

# Words that are clearly landmarks/POI categories, NOT hotel names. If query
# starts with one of these, skip fuzzy hotel matching to avoid false positives
# like "Bệnh viện Ung bứu" matching some hotel name.
_LANDMARK_PREFIXES: frozenset[str] = frozenset({
    "benh vien", "bệnh viện",
    "truong", "trường", "dai hoc", "đại học",
    "chua", "chùa", "nha tho", "nhà thờ", "thanh duong", "thánh đường",
    "cong vien", "công viên",
    "san bay", "sân bay",
    "ben xe", "bến xe", "ga ", "ga tau", "ga tàu",
    "bao tang", "bảo tàng",
    "vien bao tang", "viện bảo tàng",
    "cho ", "chợ ", "cong vien", "công viên",
    "sieu thi", "siêu thị",
    "trung tam thuong mai", "trung tâm thương mại",
    "ngan hang", "ngân hàng",
    "atm",
    "tram xang", "trạm xăng",
    "cua hang tien loi", "cửa hàng tiện lợi",
    "tiem", "tiệm",
})

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
    # C1: full address with postal code (5-6 digits) after city
    # e.g. "14 Võ Văn Tần, Xuân Hòa, Hồ Chí Minh 70000, Vietnam, Quận 3"
    r"\d{1,5}(?:[/\-]\d+[A-Za-z]?)?\s+\w[\w\s]{2,60},\s*\w[\w\s]{1,40},\s*(?:hồ chí minh|ho chi minh|hà nội|ha noi|đà nẵng|da nang|tp\.?\s*\w+)[\s\w\.]*\s*\d{4,6}\b",
    # C1 variant: "Số/Number + name + ..., Quận/Phường, City"
    # e.g. "Số 50 Bùi Thị Xuân, Đakao, Quận 1" | "50 Lê Lợi, Bến Nghé, Q1"
    r"(?:số\s+)?\d{1,5}(?:[/\-]\d+[A-Za-z]?)?\s+\w[\w\s]{2,60},\s*\w[\w\s]{1,30},\s*(?:quận|phường|q\.|p\.)\s*\w",
    # C2: "Số N [Tên đường], Phường, Quận" — without explicit street keyword
    # e.g. "Số 50 Bùi Thị Xuân, Đakao, Quận 1"
    r"số\s+\d{1,5}(?:[/\-]\d+[A-Za-z]?)?\s+\w[\w\s]{2,60}(?:,\s*\w[\w\s]{0,30})*",
    # C1 variant: very flexible — number + street + ≥2 commas + city/country
    # Catches the case where postal code or "Vietnam" appears between commas
    r"\d{1,5}(?:[/\-]\d+[A-Za-z]?)?\s+\w[\w\s]{2,60}(?:,\s*\w[\w\s\d]{1,40}){2,}",
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
        type             : "hotel_name" | "address" | "landmark"
        confidence       : float 0–1
        reason           : str  (debug)
        hotel_match      : dict | None              (best fuzzy match)
        hotel_candidates : list[dict] | None        (top-N candidates when ambiguous)
        address_phrase   : str | None               (when type == "address")
    """
    if not text or not text.strip():
        return _result("landmark", 0.3, "empty_input")

    norm = normalize_key(text)

    # ── 1. Hotel name fuzzy matching ────────────────────────────────────────
    #    - Skip if query has "near" preposition (clearly a landmark search)
    #    - Skip if query starts with a landmark prefix (bệnh viện, sân bay, …)
    #    - Skip if query is *only* an accommodation keyword like "khách sạn"
    #    - Allow fuzzy even without keyword (so "Mường Thanh" matches),
    #      but require higher score to compensate
    if (
        not _has_near_cue(norm)
        and not _starts_with_landmark_prefix(norm)
        and not _SEARCH_QUERY_RE.search(norm)
    ):
        core = _strip_generic_words(norm).strip()
        # If after stripping generic words there's nothing left, user gave
        # only "khách sạn" with no specific name → skip fuzzy match.
        if len(core.replace(" ", "")) >= HOTEL_NAME_MIN_CHARS:
            has_keyword = _has_accommodation_keyword(norm)
            matches = _fuzzy_hotel_candidates(norm, allow_no_keyword=not has_keyword)
            if matches:
                top = matches[0]
                # Multi-candidate scenario: top scores are close → return candidates
                if len(matches) > 1 and (top["score"] - matches[1]["score"]) < CANDIDATE_MARGIN:
                    return _result(
                        "hotel_name",
                        top["score"] / 100.0,
                        "db_fuzzy_match_multi",
                        hotel_match=top,
                        hotel_candidates=matches[:TOP_N_CANDIDATES],
                    )
                # Clear single best match
                return _result(
                    "hotel_name",
                    top["score"] / 100.0,
                    "db_fuzzy_match",
                    hotel_match=top,
                )

    # ── 2. Specific address ────────────────────────────────────────────────────
    phrase = _detect_address(text)
    if phrase:
        return _result("address", 0.90, "address_pattern", address_phrase=phrase)

    # ── 3. Default: treat as landmark / POI (geocode downstream) ──────────────
    return _result("landmark", 0.72, "default_landmark")


def _starts_with_landmark_prefix(norm: str) -> bool:
    """Return True if the normalized text begins with a known landmark/POI category."""
    for prefix in _LANDMARK_PREFIXES:
        if norm.startswith(prefix.strip().lower() + " ") or norm == prefix.strip().lower():
            return True
    return False


# ── helpers ───────────────────────────────────────────────────────────────────

def _result(
    kind: str,
    confidence: float,
    reason: str,
    *,
    hotel_match: dict[str, Any] | None = None,
    hotel_candidates: list[dict[str, Any]] | None = None,
    address_phrase: str | None = None,
) -> dict[str, Any]:
    return {
        "type": kind,
        "confidence": round(confidence, 4),
        "hotel_candidates": hotel_candidates,
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

    NOTE: When stripping leaves nothing (query is *only* generic words like
    "khách sạn"), returns "" so the caller can detect that case and skip
    fuzzy matching — preventing false positives where a bare "khách sạn"
    matches arbitrary hotels by token overlap.
    """
    result = _STRIP_PHRASE_PATTERN.sub(" ", norm)
    result = re.sub(r"\s+", " ", result).strip()
    return result


def _min_score_for_length(core_query: str, *, allow_no_keyword: bool) -> float:
    """Pick the threshold based on query length. Stricter when no keyword."""
    length = len(core_query.replace(" ", ""))
    if length >= 10:
        base = HOTEL_NAME_MIN_SCORE_LONG
    elif length >= 5:
        base = HOTEL_NAME_MIN_SCORE_MED
    else:
        base = HOTEL_NAME_MIN_SCORE_SHORT
    # Without a "khách sạn/hotel" keyword, the query could be anything — add buffer
    if allow_no_keyword:
        base += 5.0
    return base


def _fuzzy_hotel_candidates(norm: str, *, allow_no_keyword: bool = False) -> list[dict[str, Any]]:
    """
    Fuzzy-match norm against all accommodation names in the DB.

    Returns up to TOP_N_CANDIDATES match dicts, ordered by score descending,
    filtered to those that meet the (length-tiered) threshold.

    When ``allow_no_keyword`` is True the threshold is bumped slightly so a
    naked name like "Mường Thanh" still matches but noise queries don't.
    """
    if len(norm.replace(" ", "")) < HOTEL_NAME_MIN_CHARS:
        return []

    core_query = _strip_generic_words(norm)
    min_score = _min_score_for_length(core_query, allow_no_keyword=allow_no_keyword)

    try:
        from accommodations.models import Accommodation

        try:
            from rapidfuzz import fuzz
            _use_rf = True
        except ImportError:
            from difflib import SequenceMatcher
            _use_rf = False

        # Try to import Jaro-Winkler for short queries (better for prefix matching)
        try:
            from rapidfuzz.distance import JaroWinkler
            _has_jw = True
        except ImportError:
            _has_jw = False

        accommodations = list(
            Accommodation.objects.only("id", "name", "accommodation_type", "area")
        )
        if not accommodations:
            return []

        scored: list[tuple[float, Any]] = []
        is_short_query = len(core_query.replace(" ", "")) <= 4

        for acc in accommodations:
            acc_norm = normalize_key(acc.name or "")
            if not acc_norm:
                continue

            core_acc = _strip_generic_words(acc_norm)
            if len(core_acc.replace(" ", "")) < 3:
                continue

            if _use_rf:
                if is_short_query and _has_jw:
                    # Jaro-Winkler weights common prefix — great for "ACB" → "AU LAC LEGEND" via tokens
                    jw_token_max = max(
                        (JaroWinkler.similarity(core_query, tok) for tok in core_acc.split() if tok),
                        default=0.0,
                    )
                    score = max(
                        fuzz.WRatio(core_query, core_acc),
                        fuzz.partial_ratio(core_query, core_acc) * 0.92,
                        fuzz.token_set_ratio(core_query, core_acc) * 0.95,
                        jw_token_max * 100,
                    )
                else:
                    score = max(
                        fuzz.WRatio(core_query, core_acc),
                        fuzz.partial_ratio(core_query, core_acc) * 0.90,
                        fuzz.token_set_ratio(core_query, core_acc) * 0.95,
                    )
            else:
                score = SequenceMatcher(None, core_query, core_acc).ratio() * 100

            if score >= min_score:
                scored.append((score, acc))

        scored.sort(key=lambda pair: pair[0], reverse=True)

        # Dedupe by normalized name + area: a hotel with duplicate seed rows
        # (same name in same area, different ids) should appear once.
        candidates: list[dict[str, Any]] = []
        seen_keys: set[tuple[str, str]] = set()
        for score, acc in scored:
            name_norm = normalize_key(acc.name or "")
            area_norm = normalize_key(acc.area or "")
            key = (name_norm, area_norm)
            if key in seen_keys:
                continue
            seen_keys.add(key)
            candidates.append({
                "score": round(score, 1),
                "accommodation_id": acc.id,
                "name": acc.name,
                "area": acc.area,
                "accommodation_type": acc.accommodation_type,
            })
            if len(candidates) >= TOP_N_CANDIDATES:
                break
        return candidates
    except Exception:
        return []


def _fuzzy_hotel_match(norm: str) -> dict[str, Any] | None:
    """Backward-compat helper: return the top single match or None."""
    candidates = _fuzzy_hotel_candidates(norm)
    return candidates[0] if candidates else None
