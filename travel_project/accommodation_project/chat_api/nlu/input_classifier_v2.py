"""
InputClassifierV2 — rule-based input kind classifier for chat accommodation search.

Classifies user text into 9 input_kind values without calling any DB or geocoder.
Only extracts initial hints; downstream resolvers handle full lookup.

Priority chain (first match wins):
  1. greeting           — pure greeting pattern, no accommodation signals
  2. specific_address   — matches street address regex
  3. mixed_search       — >= 2 distinct signal types (location + amenity/budget/type)
  4. generic_poi_in_area— near-cue + POI category word + area token
  5. landmark_or_poi    — near-cue + named place (no POI category + area combo)
  6. amenity_only       — amenity signals, no location or hotel signals
  7. hotel_name         — accommodation keyword + distinctive proper name
  8. area               — area/district token only, no other signals
  9. unknown            — default fallback

No imports from Django, models, geocoders, or the database.
"""
from __future__ import annotations

import functools
import re
from dataclasses import dataclass, field
from typing import Any

from ..normalizers import normalize_key


# ============================================================================
# Result
# ============================================================================

@dataclass
class ClassificationResult:
    """Output of classify_v2(). All fields are extraction hints, not resolved values."""

    input_kind: str
    confidence: float
    location_phrase: str | None = None   # normalized text phrase (no accents, lowercase)
    location_phrase_raw: str | None = None  # original accented substring — for geocoder calls
    hotel_name: str | None = None        # full original text when kind=hotel_name
    area_hint: str | None = None         # normalized area name, if detected
    amenity_terms: list[str] = field(default_factory=list)  # canonical amenity names
    debug: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "input_kind": self.input_kind,
            "confidence": round(self.confidence, 4),
            "location_phrase": self.location_phrase,
            "location_phrase_raw": self.location_phrase_raw,
            "hotel_name": self.hotel_name,
            "area_hint": self.area_hint,
            "amenity_terms": list(self.amenity_terms),
            "debug": self.debug,
        }


# ============================================================================
# Constants
# ============================================================================

# Amenity aliases defined inline (already no-accent normalized) so this module
# is self-contained and does not import slot_pipeline (which is heavy).
# Mirrors the relevant subset of slot_pipeline.AMENITY_ALIASES.
# Phrases are pre-normalized (lowercase, no diacritics) — normalize_key not needed here.
_AMENITY_SOURCE: tuple[tuple[str, str], ...] = (
    # parking / chỗ đậu xe
    ("co cho dau xe",   "parking"),
    ("co dau xe",       "parking"),
    ("cho dau xe",      "parking"),
    ("cho de xe",       "parking"),
    ("bai do xe",       "parking"),
    ("co parking",      "parking"),
    ("co dau xxe",      "parking"),
    ("dau xxe",         "parking"),
    ("gui xe",          "parking"),
    ("do xe",           "parking"),
    ("parking",         "parking"),
    ("garage",          "parking"),
    ("gara",            "parking"),
    ("dau xe",          "parking"),
    # wifi / internet
    ("co wifi",         "wifi"),
    ("wi-fi",           "wifi"),
    ("internet",        "wifi"),
    ("wifi",            "wifi"),
    # swimming pool / hồ bơi
    ("co ho boi",       "pool"),
    ("co be boi",       "pool"),
    ("swimming pool",   "pool"),
    ("ho boi",          "pool"),
    ("be boi",          "pool"),
    ("pool",            "pool"),
    # kitchen / bếp
    ("co bep",          "kitchen"),
    ("nha bep",         "kitchen"),
    ("bep",             "kitchen"),
    ("nau an",          "kitchen"),
    ("kitchen",         "kitchen"),
    ("cook",            "kitchen"),
    # air conditioner / máy lạnh / điều hòa
    ("co may lanh",     "air_conditioner"),
    ("co dieu hoa",     "air_conditioner"),
    ("may lanh",        "air_conditioner"),
    ("dieu hoa",        "air_conditioner"),
    ("aircon",          "air_conditioner"),
    # washing machine / máy giặt
    ("co may giat",     "washing_machine"),
    ("giat do",         "washing_machine"),
    ("may giat",        "washing_machine"),
    ("washing machine", "washing_machine"),
    ("laundry",         "washing_machine"),
)

# Sort longest-first for greedy substring matching (avoids "wifi" shadowing "co wifi").
_AMENITY_PHRASES: tuple[tuple[str, str], ...] = tuple(
    sorted(_AMENITY_SOURCE, key=lambda x: len(x[0]), reverse=True)
)

# Proximity prepositions — trigger landmark/POI classification.
_NEAR_CUES: frozenset[str] = frozenset({
    "gan",          # gần
    "xung quanh",   # xung quanh
    "quanh",        # quanh
    "ke ben",       # kế bên
    "ke",           # kế (standalone)
    "canh",         # cạnh
    "sat",          # sát
    "o gan",        # ở gần
    "o quanh",      # ở quanh
    "near",
    "around",
    "next to",
    "close to",
    "khu vuc",      # khu vực (area-of context)
})

# Precomputed longest-first ordering — used by every classify_v2 call.
_NEAR_CUES_BY_LEN: tuple[str, ...] = tuple(sorted(_NEAR_CUES, key=len, reverse=True))

# Accommodation type keywords — when present without near-cue, hints at hotel_name or type filter.
_ACC_KEYWORDS: frozenset[str] = frozenset({
    "khach san", "ks", "hotel", "hotels",
    "homestay", "homstay", "home stay", "honestay", "homestate",
    "hostel", "nha tro", "phong tro", "o tro", "tro",
    "resort", "villa", "motel",
    "can ho", "apartment", "studio", "chung cu",
    "serviced apartment",
})

# Precomputed longest-first ordering — used by every classify_v2 call.
_ACC_KEYWORDS_BY_LEN: tuple[str, ...] = tuple(sorted(_ACC_KEYWORDS, key=len, reverse=True))

# Admin-level area tokens (normalized, no accent).
_AREA_ADMIN_TOKENS: frozenset[str] = frozenset({
    "quan", "phuong", "huyen", "xa", "tp", "thanh pho", "tinh",
    "q.", "p.", "h.",
})

# Known named areas — HCM districts + major cities (normalized, no accent).
# Used when text lacks admin tokens but contains a known toponym.
_KNOWN_AREAS: frozenset[str] = frozenset({
    # HCM numbered districts
    "quan 1", "quan 2", "quan 3", "quan 4", "quan 5",
    "quan 6", "quan 7", "quan 8", "quan 9", "quan 10",
    "quan 11", "quan 12",
    # HCM named districts (normalized)
    "binh thanh", "phu nhuan", "go vap", "tan binh", "tan phu",
    "binh tan", "thu duc", "binh chanh", "hoc mon", "cu chi",
    "nha be", "can gio",
    # Major cities
    "ha noi", "sai gon", "tp hcm", "ho chi minh",
    "da nang", "hoi an", "hue", "nha trang",
    "vung tau", "can tho", "da lat", "phu quoc",
    "sapa", "ha long", "quy nhon", "buon ma thuot",
    "bien hoa", "thu dau mot", "long xuyen",
})

# POI category words → canonical category name.
# Used to distinguish generic_poi_in_area ("gần quán cafe ở Q5")
# from landmark_or_poi ("gần Nhà thờ Đức Bà").
_POI_CATEGORIES: dict[str, str] = {
    "quan cafe": "cafe",
    "quan ca phe": "cafe",
    "ca phe": "cafe",
    "cafe": "cafe",
    "coffee": "cafe",
    "benh vien": "hospital",
    "bv": "hospital",
    "phong kham": "clinic",
    "nha thuoc": "pharmacy",
    "cho": "market",
    "sieu thi": "supermarket",
    "co op mart": "supermarket",
    "truong hoc": "school",
    "truong": "school",
    "dai hoc": "university",
    "cong vien": "park",
    "san bay": "airport",
    "phi truong": "airport",
    "ga tau": "train_station",
    "ga xe lua": "train_station",
    "ben xe": "bus_station",
    "ngan hang": "bank",
    "atm": "atm",
    "nha hang": "restaurant",
    "quan an": "restaurant",
    "quan nhau": "bar",
    "buu dien": "post_office",
    "gym": "gym",
    "phong gym": "gym",
    "trung tam thuong mai": "mall",
    "vincom": "mall",
    "aeon": "mall",
    # gas stations
    "tram xang": "gas_station",
    "cay xang": "gas_station",
    "xang dau": "gas_station",
    "tram xang dau": "gas_station",
    "gas station": "gas_station",
    "petrol station": "gas_station",
    "cua hang xang": "gas_station",
}

# Budget detection — a number followed by a monetary unit.
_BUDGET_RE = re.compile(
    r"\b\d+(?:[.,]\d+)?\s*"
    r"(?:k\b|ngan\b|nghin\b|tr\b|trieu\b|m\b|mil\b|million\b|dong\b|vnd\b|usd\b|\$)",
    re.IGNORECASE,
)

# Greeting patterns — must match the FULL input (stripped) to avoid
# misclassifying "xin chào tôi cần tìm khách sạn" as a greeting.
_GREETING_RE = re.compile(
    r"^(?:xin\s+chao|chao|hello|hi|alo|hey|e\s+ban|good\s+morning|good\s+evening)$",
    re.IGNORECASE,
)

# ANYWHERE intent patterns (normalized, no-accent) — exclude from hotel_name fallback.
_ANYWHERE_CLASSIFIER_RE = re.compile(
    r"\bo\s+dau\b|\banywhere\b|\bwherever\b|\bkhap\s+noi\b"
)

# Generic conversation/search words — their presence in the "remaining" text
# (after stripping acc keyword) disqualifies the hotel_name classification.
_GENERIC_WORDS: frozenset[str] = frozenset({
    "toi", "minh", "tui", "em", "anh", "chi", "ban", "chung", "minh",
    "can", "muon", "tim", "kiem", "giup", "xin", "cho", "dum", "nhe", "nha",
    "co the", "duoc", "vay", "vay a", "ah", "uh",
    "dang", "dang can", "dang tim",
})

# Simplified address patterns (normalized, no-accent form).
# Full set lives in input_classifier.py; v2 uses a focused subset.
_ADDRESS_PATTERNS: list[re.Pattern] = [
    re.compile(p, re.IGNORECASE | re.UNICODE)
    for p in [
        # Full address: "N Tên, P.X, Q.Y, TP/Tỉnh Z" — capture toàn bộ bao gồm tỉnh/thành
        r"\d{1,5}(?:/\d+[A-Za-z]?)?[A-Za-z]?\s+\w[\w\s]{2,50},\s*(?:phuong|xa|p\.)\s*\w[\w\s]{0,15},\s*(?:quan|huyen|q\.)\s*\w[\w\s]{0,15}(?:,\s*(?:tp\.?|tinh|thanh pho)\s*[\w\s]{1,30})?",
        # "[số]/[số chữ] đường/hẻm/ngõ [tên]"
        r"(?:so\s+)?\d{1,5}(?:/\d+[A-Za-z]?)?\s+(?:duong|pho|hem|ngo|ngach)\s+\w[\w\s]{1,50}",
        # "[số] [tên], quận/phường N" — số + tên đường + admin
        r"\d{1,5}(?:/\d+[A-Za-z]?)?[A-Za-z]?\s+\w[\w\s]{4,50},\s*(?:quan|phuong|q\.|p\.)\s*\d",
        # "phường N, quận N"
        r"(?:p\.|phuong)\s*\d+\s*[,\s]+(?:q\.|quan)\s*\d+",
        # "phường/xã X, quận/huyện Y"
        r"(?:phuong|xa)\s+\w[\w\s]{0,20},\s*(?:quan|huyen|q\.|h\.)\s*\w[\w\s]{0,20}",
        # "N đường/phố/hẻm X, P.M, Q.N" — full address with 3+ components
        r"\d{1,5}\s+\w[\w\s]{2,40},\s*(?:phuong|xa|p\.)\s*\w[\w\s]{0,15},\s*(?:quan|huyen|q\.)",
        # International / postal-code format: "N Street, Ward/Area, City 70000, Vietnam, Quận N"
        # Matches: number + street words + comma + 2+ more segments ending with quan/huyen + number
        r"\d{1,5}\s+\w[\w\s]{2,40}(?:,\s*[\w][\w\s]{1,40}){2,},\s*(?:quan|huyen|q\.)\s*\d+",
    ]
]


# ============================================================================
# Signal detectors (private)
# ============================================================================

@functools.lru_cache(maxsize=1)
def _load_static_landmark_aliases() -> frozenset[str]:
    """
    Return a frozenset of normalized landmark aliases from data/landmarks.json.
    Cached for the process lifetime — used by _is_known_landmark_alias().
    """
    try:
        import json
        from pathlib import Path
        data_dir = Path(__file__).resolve().parents[1] / "data"
        landmarks = json.loads((data_dir / "landmarks.json").read_text(encoding="utf-8"))
        aliases: set[str] = set()
        for lm in landmarks:
            for alias in lm.get("aliases", []):
                norm = normalize_key(alias)
                if norm:
                    aliases.add(norm)
        return frozenset(aliases)
    except Exception:
        return frozenset()


def _is_known_landmark_alias(phrase: str) -> bool:
    """True if phrase contains a known static landmark alias as a substring."""
    if not phrase:
        return False
    for alias in _load_static_landmark_aliases():
        if alias in phrase:
            return True
    return False


def _detect_amenities(norm: str) -> list[str]:
    """
    Find all amenity terms in normalized text.
    Uses greedy longest-first matching to avoid double-counting
    ('co wifi' before 'wifi', 'cho dau xe' before 'dau xe').
    Returns canonical amenity names in order of appearance.
    """
    matched: list[tuple[int, str]] = []  # (position, canonical)
    covered: set[int] = set()

    for phrase_norm, canonical in _AMENITY_PHRASES:
        idx = 0
        while True:
            idx = norm.find(phrase_norm, idx)
            if idx == -1:
                break
            span = set(range(idx, idx + len(phrase_norm)))
            if not span & covered:
                matched.append((idx, canonical))
                covered |= span
            idx += 1

    matched.sort(key=lambda x: x[0])
    # Deduplicate canonical names while preserving order
    seen: set[str] = set()
    result: list[str] = []
    for _, canonical in matched:
        if canonical not in seen:
            seen.add(canonical)
            result.append(canonical)
    return result


def _has_near_cue(norm: str) -> bool:
    """Return True if text contains a proximity preposition."""
    for cue in _NEAR_CUES:
        if re.search(r"(?:^|\s)" + re.escape(cue) + r"(?:\s|$)", norm):
            return True
    return False


def _extract_near_remainder(norm: str, text: str | None = None) -> tuple[str | None, str | None]:
    """Return (normalized, original) text following the first near-cue.

    Original form preserves Vietnamese accents so it can be sent to Nominatim.
    Returns (None, None) when no near-cue is found.
    """
    for cue in _NEAR_CUES_BY_LEN:  # longest first, precomputed at import time
        m = re.search(r"(?:^|\s)" + re.escape(cue) + r"\s+(.+)", norm)
        if m:
            normalized = m.group(1).strip()
            original = _map_norm_phrase_to_original(text or "", norm, normalized) if text else normalized
            return normalized, original
    return None, None


def _detect_acc_keyword(norm: str) -> str | None:
    """Return the matched accommodation keyword (longest first), or None."""
    for kw in _ACC_KEYWORDS_BY_LEN:
        if re.search(r"(?:^|\s)" + re.escape(kw) + r"(?:\s|$)", norm):
            return kw
    return None


def _strip_acc_keyword(norm: str, kw: str) -> str:
    """Remove the accommodation keyword from normalized text and compress whitespace."""
    result = re.sub(r"(?:^|\s)" + re.escape(kw) + r"(?:\s|$)", " ", norm)
    return re.sub(r"\s+", " ", result).strip()


def _detect_address(text: str) -> tuple[str | None, str | None]:
    """Return (normalized_phrase, original_phrase) for matched address, or (None, None).

    The normalized phrase is used for downstream regex matching; the original
    phrase preserves Vietnamese accents so Nominatim can geocode it accurately.
    """
    norm = normalize_key(text)
    for pattern in _ADDRESS_PATTERNS:
        m = pattern.search(norm)
        if m:
            matched = m.group(0).strip()
            return matched, _map_norm_phrase_to_original(text, norm, matched)
    return None, None


def _map_norm_phrase_to_original(text: str, norm: str, norm_phrase: str) -> str:
    """Map a substring of normalize_key(text) back to its original accented form.

    Word-aligned mapping: if word counts in `text` and `norm` match, the
    matched run of words has a direct correspondence in the original.
    Falls back to the normalized phrase if alignment fails.
    """
    text_words = text.split()
    norm_words = norm.split()
    match_words = norm_phrase.split()
    if not match_words or len(text_words) != len(norm_words):
        return norm_phrase
    for i in range(len(norm_words) - len(match_words) + 1):
        if norm_words[i:i + len(match_words)] == match_words:
            return " ".join(text_words[i:i + len(match_words)])
    return norm_phrase


_ADMIN_NUMERIC_RE = re.compile(
    r"(?:^|\s)(?:o\s+|tai\s+|khu\s+vuc\s+)?"
    r"(?:quan|phuong|huyen|xa|tp\.?|q\.?|p\.?)\s*"
    r"(\d{1,2})(?=\s|$|,)"
)
_ADMIN_WORD_RE = re.compile(
    r"(?:^|\s)(?:o\s+|tai\s+|khu\s+vuc\s+)?"
    r"(?:quan|phuong|huyen|xa|tp\.?|q\.|p\.)\s*"
    r"(\w[\w\s]{1,25}?)(?=\s|$|,)"
)
_ADMIN_PREFIX_RE = re.compile(r"^(?:o|tai|khu vuc)\s+")


def _extract_admin_area(m: re.Match) -> str:
    """Return 'admin suffix' from a regex match, stripping leading prepositions."""
    raw = m.group(0).strip()
    return _ADMIN_PREFIX_RE.sub("", raw).strip()


_MIN_COMPACT_ALIAS_LEN = 4  # ≥4 chars to avoid noise like "sg", "q1", "go"


@functools.lru_cache(maxsize=1)
def _gazetteer_aliases() -> tuple[str, ...]:
    """Aliases from the canonical gazetteer, sorted longest-first.

    Only aliases ≥ _MIN_COMPACT_ALIAS_LEN are returned to avoid false matches
    on common short words.  Numeric district short forms ("q1", "q3") are
    handled separately by _ADMIN_NUMERIC_RE.

    Cached for the process lifetime — the gazetteer is loaded once at import
    time and never mutated, so a single computation amortises across all
    requests.
    """
    from ..location_gazetteer import _alias_to_canonical_index
    aliases = [a for a in _alias_to_canonical_index().keys() if len(a) >= _MIN_COMPACT_ALIAS_LEN]
    return tuple(sorted(aliases, key=len, reverse=True))


def _detect_area(norm: str) -> str | None:
    """
    Return normalized area string (matched alias / extracted suffix), or None.

    Priority:
      1. Admin token + NUMERIC suffix (e.g. "quan 5") — high precision.
      2. Admin token + WORD suffix, only if suffix is NOT a POI category.
      3. Gazetteer aliases (longest first, word-boundary) — covers compact
         forms like "binhthanh", "thuduc", "govap" via the gazetteer's
         alias generator.
      4. Curated _KNOWN_AREAS legacy fallback.
    """
    # Pass 1 — numeric suffix (high precision, avoids "quan cafe" false match)
    m = _ADMIN_NUMERIC_RE.search(norm)
    if m:
        return _extract_admin_area(m)

    # Pass 2 — word suffix, but exclude POI category words
    m = _ADMIN_WORD_RE.search(norm)
    if m:
        suffix = m.group(1).strip()
        if suffix not in _POI_CATEGORIES:
            return _extract_admin_area(m)

    # Pass 3 — gazetteer aliases (compact + spaced forms)
    for alias in _gazetteer_aliases():
        if re.search(r"(?:^|\s)" + re.escape(alias) + r"(?=\s|$|,)", norm):
            return alias

    # Pass 4 — curated named areas legacy (kept for behaviors not yet in gazetteer)
    for area in sorted(_KNOWN_AREAS, key=len, reverse=True):
        if re.search(r"(?:^|\s)" + re.escape(area) + r"(?=\s|$|,)", norm):
            return area

    return None


def _detect_poi_category(norm: str) -> str | None:
    """Return canonical POI category found in text, or None (longest-first)."""
    for phrase in sorted(_POI_CATEGORIES, key=len, reverse=True):
        if re.search(r"(?:^|\s)" + re.escape(phrase) + r"(?:\s|$)", norm):
            return _POI_CATEGORIES[phrase]
    return None


def _has_budget(norm: str) -> bool:
    return bool(_BUDGET_RE.search(norm))


def _is_greeting(norm: str) -> bool:
    return bool(_GREETING_RE.match(norm.strip()))


def _is_area_only(norm: str, area: str) -> bool:
    """
    True if the text contains ONLY the area name and common prepositions /
    pronouns / city qualifiers.  Used to confirm area-only queries like
    "Quận 3", "ở Phú Nhuận", "Quận 3 TP HCM", "Tôi muốn đi Quận 5".
    """
    without_area = norm.replace(area, "").strip()
    # Strip pronouns / verbs / search filler + city qualifiers so an
    # "I want to go to <area>" sentence is still considered area-only.
    stripped = re.sub(
        r"\b(?:o|tai|khu|vuc|khu vuc|tim|kiem|muon|can|dang|dang tim|o dau|"
        r"toi|minh|tui|em|anh|chi|ban|di|den|toi muon di|"
        r"tp|tphcm|hcm|hcmc|tphn|hn|thanh\s+pho|sai\s+gon|saigon|ho\s+chi\s+minh|"
        r"ha\s+noi|hanoi|viet\s+nam|vietnam|vn|city)\b",
        "",
        without_area,
    )
    stripped = re.sub(r"[,.\s]+", "", stripped)
    return len(stripped) == 0


def _looks_like_standalone_poi(text: str, norm: str, *, area: str | None) -> bool:
    """Decide whether a raw input describes a standalone POI/landmark.

    Reuses v1's `has_concrete_place_noun` for clear POI nouns ("chợ", "công viên",
    "bảo tàng"...) and falls back to a multi-token heuristic for capitalized
    place names with an optional city-suffix ("Snow Town Sài Gòn",
    "Bình Quới 1").  Used by classify_v2 to route these inputs to
    FallbackGeocodeStrategy instead of HotelNameStrategy.
    """
    if not norm:
        return False
    has_poi_noun = False
    try:
        from ..location_phrase_cleaner import has_concrete_place_noun
        has_poi_noun = bool(has_concrete_place_noun(text))
    except Exception:
        has_poi_noun = False
    tokens = norm.split()
    if len(tokens) < 2:
        return has_poi_noun
    # Avoid generic accommodation/amenity/guest tokens — those are not POIs.
    blocked_tokens = {
        # accommodation types
        "khach", "san", "hotel", "homestay", "hostel", "apartment", "resort",
        "villa", "homtay", "homstay", "honestay", "homestate",
        # amenities
        "parking", "wifi", "phong", "room",
        # trip duration / guest count
        "ngay", "dem", "nguoi", "ng", "guest", "people", "person",
        # search filler / Vietnamese verbs+pronouns
        "soft", "filter", "tim", "kiem", "tim kiem",
        "toi", "minh", "tui", "ban", "muon", "can", "di",
    }
    if any(t in blocked_tokens for t in tokens):
        return has_poi_noun  # only treat as POI if there's a real POI noun
    # Pure-numeric or near-numeric — not a place name.
    if all(t.isdigit() or len(t) <= 1 for t in tokens):
        return False
    if norm in _KNOWN_AREAS:
        return False
    # If the only content is the area itself, leave it as area.
    if area and _is_area_only(norm, area):
        return False
    # If after stripping the area + admin prefixes / city qualifiers the
    # remainder is empty, the input is "area + city qualifier" not a POI.
    # E.g. "Quận 3 TP HCM" → strip area + "tp hcm" → empty → not a POI.
    remainder = norm
    if area:
        remainder = remainder.replace(area, " ")
    remainder = re.sub(
        r"\b(?:tp|tphcm|hcm|tphn|hn|thanh\s+pho|city|vn|vietnam|viet\s+nam|"
        r"quan|phuong|huyen|xa|q\.?|p\.?|district)\b",
        " ",
        remainder,
    )
    remainder = re.sub(r"\d+", " ", remainder)
    remainder = re.sub(r"\s+", " ", remainder).strip()
    if not remainder:
        return False
    return True


def _remaining_looks_like_hotel_name(remaining_norm: str) -> bool:
    """
    Heuristic: the remaining text (after stripping acc keyword) looks like
    a hotel proper name if it has no generic conversation/search words.
    """
    if len(remaining_norm) < 3:
        return False
    words = set(remaining_norm.split())
    if words & _GENERIC_WORDS:
        return False
    # Must not be purely an area
    if remaining_norm in _KNOWN_AREAS:
        return False
    return True


# ============================================================================
# Main classifier
# ============================================================================

def classify_v2(
    text: str,
    *,
    context_slots: dict[str, Any] | None = None,
) -> ClassificationResult:
    """
    Classify user input into one of 9 input_kind values.

    Args:
        text:          Raw user input (any casing, with/without diacritics).
        context_slots: Prior conversation slots — currently unused in classification
                       logic but accepted for future use (e.g. follow-up detection).

    Returns:
        ClassificationResult with input_kind, confidence, and extracted hints.
        Never raises.
    """
    if not text or not text.strip():
        return ClassificationResult(
            input_kind="unknown",
            confidence=0.50,
            debug={"reason": "empty_input"},
        )

    # Pre-correct common Vietnamese typos so "Homstay" → "homestay" etc.
    # is recognized as an accommodation keyword instead of a hotel/POI name.
    try:
        from ..normalizers import normalize_common_typos
        text = normalize_common_typos(text)
    except Exception:
        pass
    norm = normalize_key(text)

    # ── collect signals ────────────────────────────────────────────────────────
    amenity_terms   = _detect_amenities(norm)
    has_near_cue    = _has_near_cue(norm)
    near_remainder, near_remainder_raw = _extract_near_remainder(norm, text) if has_near_cue else (None, None)
    acc_kw          = _detect_acc_keyword(norm)
    address_phrase, address_phrase_raw = _detect_address(text)
    area            = _detect_area(norm)
    poi_category    = _detect_poi_category(norm)
    budget_present  = _has_budget(norm)
    greeting        = _is_greeting(norm)

    signals = {
        "has_amenity":      bool(amenity_terms),
        "has_near_cue":     has_near_cue,
        "has_acc_keyword":  bool(acc_kw),
        "has_address":      bool(address_phrase),
        "has_area":         bool(area),
        "has_poi_category": bool(poi_category),
        "has_budget":       budget_present,
        "is_greeting":      greeting,
    }

    # ── 1. greeting ────────────────────────────────────────────────────────────
    if greeting and not acc_kw and not has_near_cue and not amenity_terms:
        return ClassificationResult(
            input_kind="greeting",
            confidence=0.92,
            debug={"reason": "greeting_pattern", "signals": signals},
        )

    # ── 2. specific_address ────────────────────────────────────────────────────
    if address_phrase:
        return ClassificationResult(
            input_kind="specific_address",
            confidence=0.92,
            location_phrase=address_phrase,
            location_phrase_raw=address_phrase_raw,
            area_hint=area,
            debug={"reason": "address_pattern_match", "matched": address_phrase, "signals": signals},
        )

    # ── 2b. city_center — "trung tâm", "downtown", "city centre" ──────────────
    # Detect early so "gần trung tâm" doesn't fall to landmark_or_poi path.
    # Delegates to v1's chat_api.city_center which has the canonical detector.
    # Pre-apply common typo fixes ("truang tâm" → "trung tâm") so the v1
    # detector sees the corrected form (parity with v1's deterministic_parser).
    try:
        from ..city_center import detect_city_center_intent
        from ..normalizers import normalize_common_typos
        cc_intent = detect_city_center_intent(normalize_common_typos(text))
    except Exception:
        cc_intent = None
    if cc_intent is not None:
        cc_center = cc_intent.get("city_center") or {}
        cc_city = cc_center.get("canonical_area") or cc_intent.get("city_hint")
        return ClassificationResult(
            input_kind="city_center",
            confidence=float(cc_intent.get("confidence") or 0.85),
            location_phrase="trung tâm thành phố",
            location_phrase_raw="trung tâm thành phố",
            area_hint=cc_city,
            debug={
                "reason": cc_intent.get("reason") or "city_center_pattern",
                "city_hint": cc_city,
                "signals": signals,
            },
        )

    # ── count distinct signal types for mixed_search detection ────────────────
    signal_types: list[str] = []
    if has_near_cue or area:
        signal_types.append("location")
    if amenity_terms:
        signal_types.append("amenity")
    if budget_present:
        signal_types.append("budget")
    if acc_kw:
        signal_types.append("type")

    # ── 3. mixed_search — multiple dimensions in a single query ───────────────
    if len(signal_types) >= 2:
        return ClassificationResult(
            input_kind="mixed_search",
            confidence=0.85,
            location_phrase=near_remainder or area,
            location_phrase_raw=near_remainder_raw or near_remainder or area,
            area_hint=area,
            amenity_terms=amenity_terms,
            debug={
                "reason": "multiple_signal_types",
                "signal_types": signal_types,
                "signals": signals,
            },
        )

    # ── 4 & 5. near-cue paths ─────────────────────────────────────────────────
    if has_near_cue:
        # Static landmark takes top priority — wins over generic_poi_in_area and
        # near_cue+known_area_only. "gần chợ Bến Thành" and "gần Bến Thành" both
        # contain landmark aliases, so they resolve as named anchors not area text.
        if near_remainder and _is_known_landmark_alias(near_remainder):
            return ClassificationResult(
                input_kind="landmark_or_poi",
                confidence=0.88,
                location_phrase=near_remainder,
                location_phrase_raw=near_remainder_raw,
                area_hint=area,
                debug={"reason": "near_cue+known_landmark", "signals": signals},
            )

        # generic_poi_in_area: near-cue + category word + explicit area
        # e.g. "gần quán cafe ở Quận 5", "gần bệnh viện ở Phú Nhuận"
        if poi_category and area:
            return ClassificationResult(
                input_kind="generic_poi_in_area",
                confidence=0.87,
                location_phrase=near_remainder,
                location_phrase_raw=near_remainder_raw,
                area_hint=area,
                debug={
                    "reason": "near_cue+poi_category+area",
                    "poi_category": poi_category,
                    "signals": signals,
                },
            )

        # "gần Quận 3", "gần thuduc" — remainder IS a known area, not a POI.
        # Treat as area so DirectAreaStrategy resolves it instead of sending
        # "thuduc" to Nominatim (which never finds it).
        if area and near_remainder and area in (near_remainder, near_remainder.strip()):
            return ClassificationResult(
                input_kind="area",
                confidence=0.85,
                location_phrase=area,
                location_phrase_raw=near_remainder_raw or area,
                area_hint=area,
                debug={"reason": "near_cue+known_area_only", "signals": signals},
            )

        # landmark_or_poi: near-cue + named place
        # e.g. "gần Landmark 81", "gần Dinh Độc Lập"
        return ClassificationResult(
            input_kind="landmark_or_poi",
            confidence=0.80,
            location_phrase=near_remainder,
            location_phrase_raw=near_remainder_raw,
            area_hint=area,
            debug={"reason": "near_cue+named_place", "signals": signals},
        )

    # ── 6. amenity_only ───────────────────────────────────────────────────────
    # Amenity signals present, no location or hotel keyword.
    if amenity_terms and not has_near_cue and not area and not acc_kw:
        return ClassificationResult(
            input_kind="amenity_only",
            confidence=0.88,
            amenity_terms=amenity_terms,
            debug={"reason": "amenity_no_location_no_hotel", "signals": signals},
        )

    # ── 7. hotel_name ─────────────────────────────────────────────────────────
    # Accommodation keyword + no near-cue + remaining text looks like a proper name.
    # No DB lookup — purely textual heuristic.
    if acc_kw and not has_near_cue and not amenity_terms and not budget_present:
        remaining = _strip_acc_keyword(norm, acc_kw)
        if _remaining_looks_like_hotel_name(remaining):
            return ClassificationResult(
                input_kind="hotel_name",
                confidence=0.70,
                hotel_name=text.strip(),
                area_hint=area,
                debug={
                    "reason": "acc_keyword+distinctive_remaining",
                    "acc_kw": acc_kw,
                    "remaining": remaining,
                    "signals": signals,
                },
            )

    # ── 8. area ───────────────────────────────────────────────────────────────
    if area and _is_area_only(norm, area):
        return ClassificationResult(
            input_kind="area",
            confidence=0.82,
            location_phrase=area,
            area_hint=area,
            debug={"reason": "area_token_only", "signals": signals},
        )

    # ── 8b. generic POI in area — no near-cue — "trạm xăng ở Quận 3", "cafe Quận 1"
    # POI category word + explicit area but no near-cue ("ở" is not a near-cue).
    # Prevents geocoding the whole phrase as a vague landmark.
    if poi_category and area and not has_near_cue and not amenity_terms and not acc_kw:
        return ClassificationResult(
            input_kind="generic_poi_in_area",
            confidence=0.82,
            location_phrase=norm,
            location_phrase_raw=text.strip(),
            area_hint=area,
            debug={
                "reason": "poi_category+area_no_near_cue",
                "poi_category": poi_category,
                "signals": signals,
            },
        )

    # ── 8c. standalone POI / landmark — "Đầm Sen", "Snow Town Sài Gòn", — "Đầm Sen", "Snow Town Sài Gòn",
    # "Chợ Tân Bình", "Công viên Văn hóa Đầm Sen", "Bình Quới 1".
    # Reuses v1's has_concrete_place_noun + multi-token heuristic so v2 routes
    # these to FallbackGeocodeStrategy instead of HotelNameStrategy.
    if (
        not has_near_cue
        and not amenity_terms
        and not budget_present
        and not acc_kw
        and not _ANYWHERE_CLASSIFIER_RE.search(norm)
        and _looks_like_standalone_poi(text, norm, area=area)
    ):
        return ClassificationResult(
            input_kind="landmark_or_poi",
            confidence=0.70,
            location_phrase=norm,
            location_phrase_raw=text.strip(),
            area_hint=area,
            debug={"reason": "standalone_poi_phrase", "signals": signals},
        )

    # ── 9b. hotel_name fallback — proper name with no other signals ───────────
    # Catches hotel names that lack an explicit accommodation keyword, e.g.
    # "Park Hyatt Saigon", "Sheraton Saigon", "Liberty Central Saigon".
    # Guarded against ANYWHERE patterns ("ở đâu cũng được") and generic words.
    if (
        not has_near_cue
        and not area
        and not amenity_terms
        and not budget_present
        and not acc_kw
        and not _ANYWHERE_CLASSIFIER_RE.search(norm)
    ):
        words = norm.split()
        word_set = set(words)
        if (
            1 <= len(words) <= 5
            and not (word_set & _GENERIC_WORDS)
            and norm not in _KNOWN_AREAS
        ):
            return ClassificationResult(
                input_kind="hotel_name",
                confidence=0.55,
                hotel_name=text.strip(),
                debug={"reason": "proper_name_fallback", "signals": signals},
            )

    # ── 9. unknown ────────────────────────────────────────────────────────────
    return ClassificationResult(
        input_kind="unknown",
        confidence=0.40,
        area_hint=area,
        amenity_terms=amenity_terms,
        debug={"reason": "no_pattern_matched", "signals": signals},
    )
