from __future__ import annotations

import re
import unicodedata


def normalize_text(text: str) -> str:
    text = text.strip().lower()
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