from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from chat_api.normalizers import normalize_key


NUMBER_WORDS = {
    "khong": 0,
    "mot": 1,
    "một": 1,
    "motj": 1,
    "mốt": 1,
    "hai": 2,
    "ba": 3,
    "bon": 4,
    "bốn": 4,
    "tu": 4,
    "tư": 4,
    "nam": 5,
    "năm": 5,
    "lam": 5,
    "lăm": 5,
    "sau": 6,
    "sáu": 6,
    "bay": 7,
    "bảy": 7,
    "tam": 8,
    "tám": 8,
    "chin": 9,
    "chín": 9,
    "muoi": 10,
    "mười": 10,
}

MONEY_WORD = r"khong|mot|một|motj|mốt|hai|ba|bon|bốn|tu|tư|nam|năm|lam|lăm|sau|sáu|bay|bảy|tam|tám|chin|chín|muoi|mười|tram|trăm|linh|lẻ|le|ruoi|rưỡi"
MONEY_PHRASE = rf"(?:{MONEY_WORD})(?:\s+(?:{MONEY_WORD}))*"
UNIT_WORD = r"khong|mot|một|motj|mốt|hai|ba|bon|bốn|tu|tư|nam|năm|lam|lăm|sau|sáu|bay|bảy|tam|tám|chin|chín"
MILLION_TAIL = rf"(?:ruoi|rưỡi|(?:{UNIT_WORD})(?:\s+(?:tram|trăm))?|(?:{UNIT_WORD})\s+(?:muoi|mười)(?:\s+(?:{UNIT_WORD}))?)"

RAW_FILLER_PATTERNS = [
    r"\b(ờ|ừ|ừm|ờm|à)\b",
]

FILLER_PATTERNS = [
    r"\b(u|um|uh|om|a|ah|ha|nha|nhe)\b",
    r"\b(cho mình hỏi là|mình muốn hỏi là|kiểu như là|nói chung là)\b",
]

LOCATION_CORRECTIONS = {
    "da lac": "da lat",
    "da lat": "da lat",
    "da lach": "da lat",
    "vung tau": "vung tau",
    "vung tauw": "vung tau",
    "vung tauu": "vung tau",
    "vung tao": "vung tau",
    "sai gon": "sai gon",
    "sai gion": "sai gon",
    "sai gonh": "sai gon",
    "ha loi": "ha noi",
    "ha noi": "ha noi",
    "ha noij": "ha noi",
}


@dataclass
class TranscriptCleanupResult:
    original_text: str
    cleaned_text: str
    replacements: list[dict[str, str]]
    confidence_flags: list[str]

    @property
    def changed(self) -> bool:
        return normalize_key(self.original_text) != normalize_key(self.cleaned_text)

    def as_dict(self) -> dict[str, Any]:
        return {
            "changed": self.changed,
            "replacements": self.replacements,
            "confidence_flags": self.confidence_flags,
        }


def cleanup_transcript(transcript: str) -> TranscriptCleanupResult:
    raw_text = _strip_raw_fillers(transcript or "", replacements := [])
    text = normalize_key(raw_text)
    flags: list[str] = []

    text = _strip_fillers(text, replacements)
    text = _correct_locations(text, replacements, flags)
    text = _replace_digit_money_units(text, replacements, flags)
    text = _replace_spoken_millions(text, replacements, flags)
    text = _replace_spoken_thousands(text, replacements, flags)
    text = _strip_non_numeric_punctuation(text)
    text = re.sub(r"\s+", " ", text).strip()

    return TranscriptCleanupResult(
        original_text=transcript or "",
        cleaned_text=text,
        replacements=replacements,
        confidence_flags=_unique(flags),
    )


def _strip_raw_fillers(text: str, replacements: list[dict[str, str]]) -> str:
    cleaned = text
    for pattern in RAW_FILLER_PATTERNS:
        new_text, count = re.subn(pattern, " ", cleaned, flags=re.IGNORECASE)
        if count:
            replacements.append({"type": "filler_removed", "from": pattern, "to": ""})
            cleaned = new_text
    return cleaned


def build_confirmation(cleanup: TranscriptCleanupResult, parsed_result: dict[str, Any]) -> dict[str, Any]:
    slots = (parsed_result or {}).get("slots") or {}
    area = slots.get("area")
    budget = slots.get("budget_max") or slots.get("budget")
    guests = slots.get("guest_count")
    reasons: list[str] = []

    if "money_from_spoken_vietnamese" in cleanup.confidence_flags or "money_unit_noise" in cleanup.confidence_flags:
        reasons.append("budget_inferred_from_noisy_speech")
    if "location_corrected" in cleanup.confidence_flags:
        reasons.append("location_text_was_corrected")
    if (parsed_result or {}).get("location_status") in {"multiple_choice", "conflict", "unsupported"}:
        reasons.append(f"location_status_{parsed_result.get('location_status')}")

    needs_confirmation = bool(reasons and (area or budget or guests))
    question = None
    if needs_confirmation:
        summary_parts = []
        if area:
            summary_parts.append(str(area).title())
        if budget:
            summary_parts.append(f"ngân sách khoảng {_format_vnd(int(budget))}")
        if guests:
            summary_parts.append(f"{guests} người")
        summary = ", ".join(summary_parts)
        question = f"Mình nghe là {summary}. Đúng không?"

    return {
        "needs_confirmation": needs_confirmation,
        "question": question,
        "reasons": reasons,
        "fields": {
            "area": area,
            "budget": budget,
            "guest_count": guests,
        },
    }


def _strip_fillers(text: str, replacements: list[dict[str, str]]) -> str:
    cleaned = text
    for pattern in FILLER_PATTERNS:
        new_text, count = re.subn(pattern, " ", cleaned)
        if count:
            replacements.append({"type": "filler_removed", "from": pattern, "to": ""})
            cleaned = new_text
    return cleaned


def _strip_non_numeric_punctuation(text: str) -> str:
    return re.sub(r"(?<!\d)[,.]|[,.](?!\d)", " ", text)


def _correct_locations(text: str, replacements: list[dict[str, str]], flags: list[str]) -> str:
    cleaned = text
    for wrong, right in LOCATION_CORRECTIONS.items():
        new_text, count = re.subn(rf"(?<!\w){re.escape(wrong)}(?!\w)", right, cleaned)
        if count and wrong != right:
            replacements.append({"type": "location_correction", "from": wrong, "to": right})
            flags.append("location_corrected")
            cleaned = new_text
    return cleaned


def _replace_digit_money_units(text: str, replacements: list[dict[str, str]], flags: list[str]) -> str:
    def repl(match: re.Match[str]) -> str:
        raw = match.group(0)
        number = match.group("number")
        unit = match.group("unit")
        normalized = f"{number}k" if unit in {"ca", "ka", "cay"} else raw
        if normalized != raw:
            replacements.append({"type": "money_unit_noise", "from": raw, "to": normalized})
            flags.append("money_unit_noise")
        return normalized

    return re.sub(r"(?P<number>\d+(?:[.,]\d+)?)\s*(?P<unit>ca|ka|cay)(?!\w)", repl, text)


def _replace_spoken_millions(text: str, replacements: list[dict[str, str]], flags: list[str]) -> str:
    pattern = rf"(?P<million>{MONEY_PHRASE})\s+(?:trieu|triệu|cu)\s*(?P<tail>{MILLION_TAIL})?"

    def repl(match: re.Match[str]) -> str:
        raw = match.group(0).strip()
        million = _parse_under_1000(match.group("million"))
        tail_text = (match.group("tail") or "").strip()
        if million is None:
            return raw

        amount = million * 1_000_000
        if tail_text:
            if normalize_key(tail_text) in {"ruoi", "rưỡi"}:
                amount += 500_000
            else:
                tail = _parse_under_1000(tail_text)
                if tail is not None:
                    if tail < 10:
                        amount += tail * 100_000
                    elif tail < 100:
                        amount += tail * 10_000
                    else:
                        amount += tail * 1_000

        normalized = str(amount)
        replacements.append({"type": "money_from_spoken_vietnamese", "from": raw, "to": normalized})
        flags.append("money_from_spoken_vietnamese")
        return normalized

    return re.sub(pattern, repl, text)


def _replace_spoken_thousands(text: str, replacements: list[dict[str, str]], flags: list[str]) -> str:
    pattern = rf"(?P<number>{MONEY_PHRASE})\s*(?:nghin|ngàn|ngan|k|ca|ka|cay)(?!\w)"

    def repl(match: re.Match[str]) -> str:
        raw = match.group(0).strip()
        value = _parse_under_1000(match.group("number"))
        if value is None:
            return raw
        normalized = str(value * 1_000)
        replacements.append({"type": "money_from_spoken_vietnamese", "from": raw, "to": normalized})
        flags.append("money_from_spoken_vietnamese")
        return normalized

    return re.sub(pattern, repl, text)


def _parse_under_1000(text: str | None) -> int | None:
    tokens = [token for token in normalize_key(text or "").split() if token not in {"linh", "le", "lẻ"}]
    if not tokens:
        return None
    if tokens == ["ruoi"]:
        return None

    total = 0
    if "tram" in tokens:
        index = tokens.index("tram")
        if index == 0:
            return None
        hundreds = _word_value(tokens[index - 1])
        if hundreds is None:
            return None
        total += hundreds * 100
        rest = tokens[index + 1:]
        if rest:
            rest_value = _parse_under_100(rest)
            if rest_value is None:
                return None
            total += rest_value
        return total

    return _parse_under_100(tokens)


def _parse_under_100(tokens: list[str]) -> int | None:
    if not tokens:
        return 0
    if len(tokens) == 1:
        return _word_value(tokens[0])
    if tokens[0] in {"muoi", "mười"}:
        unit = _word_value(tokens[1]) if len(tokens) > 1 else 0
        return 10 + (unit or 0)
    if len(tokens) >= 2 and tokens[1] in {"muoi", "mười"}:
        tens = _word_value(tokens[0])
        if tens is None:
            return None
        unit = _word_value(tokens[2]) if len(tokens) > 2 else 0
        return tens * 10 + (unit or 0)
    if len(tokens) == 2:
        first = _word_value(tokens[0])
        second = _word_value(tokens[1])
        if first is not None and second is not None:
            return first * 10 + second
    return None


def _word_value(token: str) -> int | None:
    return NUMBER_WORDS.get(token) or NUMBER_WORDS.get(normalize_key(token))


def _format_vnd(value: int) -> str:
    if value >= 1_000_000 and value % 1_000_000 == 0:
        return f"{value // 1_000_000} triệu"
    if value >= 1_000_000:
        return f"{value / 1_000_000:.1f}".replace(".", ",") + " triệu"
    if value >= 1_000:
        return f"{value // 1_000}k"
    return str(value)


def _unique(values: list[str]) -> list[str]:
    output: list[str] = []
    for value in values:
        if value not in output:
            output.append(value)
    return output
