from __future__ import annotations

import re
import unicodedata


COMMON_TYPO_REPLACEMENTS: tuple[tuple[str, str], ...] = (
    (r"\btruang\s+t[aâ]m\b", "trung tâm"),
    (r"\btrug\s+t[aâ]m\b", "trung tâm"),
    (r"\btrung\s+tam\b", "trung tâm"),
    (r"(?<!\btrung\s)\bt[aâ]m\s+th[aà]nh\s+ph[oố]\b", "trung tâm thành phố"),
    (r"(?<!\btrung\s)\btam\s+thanh\s+pho\b", "trung tâm thành phố"),
    (r"\bthanh\s+pho\b", "thành phố"),
    (r"\bch[oổ]\s+ở\b", "chỗ ở"),
    (r"\btìn\b", "tìm"),
    (r"\bmuốm\b", "muốn"),
    (r"\b(?:homstay|homestate|honestay|hómtay|hómstay)\b", "homestay"),
)


def normalize_common_typos(text: str | None) -> str:
    value = "" if text is None else str(text)
    for pattern, replacement in COMMON_TYPO_REPLACEMENTS:
        value = re.sub(pattern, replacement, value, flags=re.IGNORECASE)
    return value


def normalize_text(text: str) -> str:
    text = normalize_common_typos(text).strip().lower()
    text = re.sub(r"\s+", " ", text)
    return text


def strip_accents(text: str) -> str:
    text = text.replace("đ", "d").replace("Đ", "D")
    return "".join(
        c for c in unicodedata.normalize("NFD", text)
        if unicodedata.category(c) != "Mn"
    )


def normalize_key(text: str) -> str:
    text = strip_accents(text.lower())
    text = re.sub(r"[^\w\s/.,-]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


# ─── Display label cleaning ───────────────────────────────────────────────────
# Tokens that are administrative noise from Nominatim — strip them out so labels
# stay concise (e.g. "Dinh Độc Lập" instead of the full 8-part display_name).
_NOISE_PARTS_PATTERN = re.compile(
    r"^(?:"
    r"\d{4,6}"                                # postal codes: 70000, 71009
    r"|kp\s*\d+|khu\s*ph[oố]\s*\d+"           # block/quarter numbers
    r"|vi[eệ]t\s*nam|vietnam"                 # country
    r"|kh[uú]\s*ph[oố]"                       # district-block label without number
    r")$",
    re.IGNORECASE,
)

_CITY_KEYWORDS = (
    "hồ chí minh", "ho chi minh", "tp hcm", "tp.hcm", "tp. hcm",
    "hà nội", "ha noi", "tp ha noi", "tp hà nội",
    "đà nẵng", "da nang",
)


def _is_noise_part(part: str) -> bool:
    stripped = part.strip()
    if not stripped:
        return True
    return bool(_NOISE_PARTS_PATTERN.match(stripped))


def _detect_city_in_parts(parts: list[str]) -> str | None:
    """Return a friendly city label if any part mentions a major VN city."""
    for raw in parts:
        lower = raw.strip().lower()
        if not lower:
            continue
        for keyword in _CITY_KEYWORDS:
            if keyword in lower:
                if "hồ chí minh" in lower or "ho chi minh" in lower or "hcm" in lower:
                    return "TP HCM"
                if "hà nội" in lower or "ha noi" in lower:
                    return "Hà Nội"
                if "đà nẵng" in lower or "da nang" in lower:
                    return "Đà Nẵng"
    return None


def clean_display_label(raw_label: str | None, *, max_parts: int = 2) -> str | None:
    """Return a concise human-friendly version of a long Nominatim display_name.

    Examples
    --------
    >>> clean_display_label(
    ...     "Dinh Độc Lập, 135, Nam Kỳ Khởi Nghĩa, Khu phố 7, Phường Bến Thành, "
    ...     "Thành phố Thủ Đức, Thành phố Hồ Chí Minh, 71009, Việt Nam"
    ... )
    'Dinh Độc Lập (TP HCM)'

    Rules:
        - Splits on commas, trims each part.
        - Drops noise parts: postal codes, "Việt Nam", "Khu phố N", empties.
        - Returns the first 1-2 meaningful parts, optionally appending a city
          tag like "(TP HCM)" when the original string referenced one.
    """
    if not raw_label or not isinstance(raw_label, str):
        return raw_label

    raw_label = raw_label.strip()
    if "," not in raw_label:
        return raw_label

    parts = [p.strip() for p in raw_label.split(",") if p.strip()]
    if not parts:
        return raw_label

    meaningful = [p for p in parts if not _is_noise_part(p)]
    if not meaningful:
        return parts[0]

    city = _detect_city_in_parts(parts)
    head = meaningful[0]

    # If user already said city-level (e.g. label IS "TP HCM"), don't double-up
    if city and city.lower() in head.lower():
        return head

    # Skip filler administrative prefixes between head and city (Phường, Quận, …)
    if len(meaningful) > 1 and city:
        return f"{head} ({city})"

    if len(meaningful) >= 2 and max_parts >= 2:
        return f"{head}, {meaningful[1]}"

    return head
