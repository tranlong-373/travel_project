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
