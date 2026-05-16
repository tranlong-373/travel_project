from __future__ import annotations

import re
import unicodedata

from .normalizers import normalize_common_typos


_ABBREVIATIONS = {
    "ks": ["khach", "san"],
    "ksan": ["khach", "san"],
    "hotel": ["khach", "san"],
    "wf": ["wifi"],
}


def strip_vietnamese_accents(text: str) -> str:
    text = text.replace("đ", "d").replace("Đ", "D")
    return "".join(
        char
        for char in unicodedata.normalize("NFD", text)
        if unicodedata.category(char) != "Mn"
    )


def _clean_spacing(text: str) -> str:
    text = re.sub(r"[^\w\s]", " ", text, flags=re.UNICODE)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _split_joined_letters_and_digits(text: str) -> str:
    text = re.sub(r"(?<=[^\W\d_])(?=\d)", " ", text, flags=re.UNICODE)
    text = re.sub(r"(?<=\d)(?=[^\W\d_])", " ", text, flags=re.UNICODE)
    return text


def _expand_tokens(tokens: list[str]) -> list[str]:
    expanded: list[str] = []
    index = 0

    while index < len(tokens):
        token = tokens[index]
        next_token = tokens[index + 1] if index + 1 < len(tokens) else None

        if token.isdigit() and next_token == "ng":
            expanded.extend([token, "nguoi"])
            index += 2
            continue

        if token in _ABBREVIATIONS:
            expanded.extend(_ABBREVIATIONS[token])
        else:
            expanded.append(token)
        index += 1

    return expanded


def normalize_user_text(text: str) -> dict:
    raw_text = "" if text is None else str(text)
    lowered = normalize_common_typos(raw_text).lower().strip()
    spaced = _clean_spacing(lowered)
    split_text = _split_joined_letters_and_digits(spaced)
    split_text = _clean_spacing(split_text)
    tokens = _expand_tokens(split_text.split()) if split_text else []

    normalized_text = " ".join(tokens)
    no_accent_text = strip_vietnamese_accents(normalized_text)
    compact_text = no_accent_text.replace(" ", "")

    return {
        "raw_text": raw_text,
        "normalized_text": normalized_text,
        "no_accent_text": no_accent_text,
        "compact_text": compact_text,
        "tokens": tokens,
    }
