from __future__ import annotations

import difflib
import re
from dataclasses import dataclass

from .location_gazetteer import generate_location_aliases
from .text_normalizer import normalize_user_text

try:
    from rapidfuzz import fuzz
except Exception:  # pragma: no cover - rapidfuzz is optional.
    fuzz = None


@dataclass(frozen=True)
class _AliasEntry:
    canonical_area: str
    city: str | None
    type: str | None
    alias: str
    alias_key: str
    alias_compact: str
    supported: bool


def _empty_result() -> dict:
    return {
        "location_status": "unresolved",
        "canonical_area": None,
        "location_confidence": 0.0,
        "location_source": "none",
        "needs_confirmation": False,
        "confirmation_type": "none",
        "location_candidates": [],
        "matched_text": None,
    }


def _build_alias_entries(supported_locations: list[dict]) -> list[_AliasEntry]:
    entries: list[_AliasEntry] = []
    seen: set[tuple[str, str]] = set()

    for location in supported_locations or []:
        canonical_name = str(location.get("canonical_name") or "").strip()
        if not canonical_name:
            continue

        aliases = set(location.get("aliases") or [])
        aliases.update(
            generate_location_aliases(
                canonical_name,
                city=location.get("city"),
                type=location.get("type"),
            )
        )
        aliases.add(canonical_name)

        for alias in aliases:
            normalized = normalize_user_text(alias)
            alias_key = normalized["no_accent_text"]
            alias_compact = normalized["compact_text"]
            if not alias_key and not alias_compact:
                continue

            key = (canonical_name, alias_compact or alias_key)
            if key in seen:
                continue
            seen.add(key)
            entries.append(
                _AliasEntry(
                    canonical_area=canonical_name,
                    city=location.get("city"),
                    type=location.get("type"),
                    alias=alias,
                    alias_key=alias_key,
                    alias_compact=alias_compact,
                    supported=bool(location.get("supported", True)),
                )
            )

    entries.sort(key=lambda entry: max(len(entry.alias_key), len(entry.alias_compact)), reverse=True)
    return entries


def _candidate(entry: _AliasEntry, confidence: float, source: str, matched_text: str | None) -> dict:
    return {
        "canonical_area": entry.canonical_area,
        "city": entry.city,
        "type": entry.type,
        "alias": entry.alias,
        "matched_text": matched_text,
        "confidence": round(confidence, 3),
        "source": source,
        "supported": entry.supported,
    }


def _unique_candidates(candidates: list[dict]) -> list[dict]:
    unique: list[dict] = []
    seen: set[str] = set()
    for candidate in sorted(candidates, key=lambda item: item["confidence"], reverse=True):
        key = candidate["canonical_area"]
        if key in seen:
            continue
        seen.add(key)
        unique.append(candidate)
    return unique


def _multiple_choice(candidates: list[dict], source: str) -> dict:
    unique = _unique_candidates(candidates)
    return {
        "location_status": "multiple_choice",
        "canonical_area": None,
        "location_confidence": unique[0]["confidence"] if unique else 0.0,
        "location_source": source,
        "needs_confirmation": True,
        "confirmation_type": "explicit",
        "location_candidates": unique,
        "matched_text": unique[0]["matched_text"] if unique else None,
    }


def _result_from_candidate(candidate: dict, source: str) -> dict:
    confidence = float(candidate["confidence"])
    candidates = [candidate]
    matched_text = candidate["matched_text"]

    if not candidate.get("supported", True):
        return {
            "location_status": "unsupported",
            "canonical_area": None,
            "location_confidence": confidence,
            "location_source": source,
            "needs_confirmation": True,
            "confirmation_type": "explicit",
            "location_candidates": candidates,
            "matched_text": matched_text,
        }

    if confidence >= 0.90:
        return {
            "location_status": "ok",
            "canonical_area": candidate["canonical_area"],
            "location_confidence": confidence,
            "location_source": source,
            "needs_confirmation": False,
            "confirmation_type": "none",
            "location_candidates": candidates,
            "matched_text": matched_text,
        }

    if confidence >= 0.75:
        return {
            "location_status": "ok",
            "canonical_area": candidate["canonical_area"],
            "location_confidence": confidence,
            "location_source": source,
            "needs_confirmation": False,
            "confirmation_type": "implicit",
            "location_candidates": candidates,
            "matched_text": matched_text,
        }

    if confidence >= 0.60:
        return {
            "location_status": "ambiguous",
            "canonical_area": None,
            "location_confidence": confidence,
            "location_source": source,
            "needs_confirmation": True,
            "confirmation_type": "explicit",
            "location_candidates": candidates,
            "matched_text": matched_text,
        }

    result = _empty_result()
    result["location_candidates"] = candidates
    return result


def _whole_exact_candidates(normalized: dict, entries: list[_AliasEntry]) -> list[dict]:
    query_values = {
        normalized["normalized_text"],
        normalized["no_accent_text"],
        normalized["compact_text"],
    }
    query_values.discard("")

    candidates: list[dict] = []
    for entry in entries:
        if entry.alias_key in query_values or entry.alias_compact in query_values:
            candidates.append(_candidate(entry, 1.0, "exact", entry.alias))
    return _unique_candidates(candidates)


def _contains_alias(normalized: dict, entry: _AliasEntry) -> bool:
    alias_key = entry.alias_key
    alias_compact = entry.alias_compact
    no_accent_text = normalized["no_accent_text"]
    compact_text = normalized["compact_text"]

    if alias_key:
        pattern = rf"(?<!\w){re.escape(alias_key)}(?!\w)"
        if re.search(pattern, no_accent_text):
            return True

    if alias_compact and (len(alias_compact) >= 4 or any(char.isdigit() for char in alias_compact)):
        return alias_compact in compact_text

    return False


def _clear_alias_candidates(normalized: dict, entries: list[_AliasEntry]) -> list[dict]:
    candidates = [
        _candidate(entry, 0.95, "alias", entry.alias)
        for entry in entries
        if _contains_alias(normalized, entry)
    ]
    return _unique_candidates(candidates)


def _digits_compatible(query: str, alias: str) -> bool:
    alias_digits = set(re.findall(r"\d+", alias))
    if not alias_digits:
        return True
    query_digits = set(re.findall(r"\d+", query))
    return bool(alias_digits & query_digits)


def _sequence_ratio(left: str, right: str) -> float:
    if not left or not right:
        return 0.0
    if fuzz is not None:
        return fuzz.ratio(left, right) / 100
    return difflib.SequenceMatcher(None, left, right).ratio()


def _compact_window_score(query: str, alias: str) -> float:
    if not query or not alias:
        return 0.0
    if len(query) <= len(alias) + 2:
        return _sequence_ratio(query, alias)

    best = 0.0
    min_size = max(2, len(alias) - 2)
    max_size = min(len(query), len(alias) + 2)
    for size in range(min_size, max_size + 1):
        for start in range(0, len(query) - size + 1):
            best = max(best, _sequence_ratio(query[start : start + size], alias))
    return best


def _ngram_score(tokens: list[str], alias_tokens: list[str], alias_key: str) -> float:
    if not tokens or not alias_tokens:
        return 0.0

    best = 0.0
    min_size = max(1, len(alias_tokens) - 1)
    max_size = min(len(tokens), len(alias_tokens) + 1)
    for size in range(min_size, max_size + 1):
        for start in range(0, len(tokens) - size + 1):
            candidate = " ".join(tokens[start : start + size])
            best = max(best, _sequence_ratio(candidate, alias_key))
    return best


def _fuzzy_score(normalized: dict, entry: _AliasEntry) -> float:
    query_key = normalized["no_accent_text"]
    query_compact = normalized["compact_text"]
    alias_key = entry.alias_key
    alias_compact = entry.alias_compact

    if not _digits_compatible(query_key, alias_key):
        return 0.0

    tokens = normalized["no_accent_text"].split()
    alias_tokens = alias_key.split()
    return max(
        _ngram_score(tokens, alias_tokens, alias_key),
        _compact_window_score(query_compact, alias_compact),
    )


def _fuzzy_candidates(normalized: dict, entries: list[_AliasEntry]) -> list[dict]:
    best_by_area: dict[str, dict] = {}

    for entry in entries:
        if len(entry.alias_compact) < 3 and not any(char.isdigit() for char in entry.alias_compact):
            continue

        score = _fuzzy_score(normalized, entry)
        if score <= 0:
            continue
        if not _has_location_overlap(normalized, entry):
            continue

        candidate = _candidate(entry, score, "fuzzy_gazetteer", entry.alias)
        existing = best_by_area.get(entry.canonical_area)
        if existing is None or candidate["confidence"] > existing["confidence"]:
            best_by_area[entry.canonical_area] = candidate

    return sorted(best_by_area.values(), key=lambda item: item["confidence"], reverse=True)


def _has_location_overlap(normalized: dict, entry: _AliasEntry) -> bool:
    query_tokens = normalized["no_accent_text"].split()
    query_compact = normalized["compact_text"]
    if any(char.isdigit() for char in entry.alias_compact):
        return _digits_compatible(normalized["no_accent_text"], entry.alias_key)

    compact_prefix = entry.alias_compact[:3]
    if len(compact_prefix) == 3 and compact_prefix in query_compact:
        return True

    for alias_token in entry.alias_key.split():
        if len(alias_token) < 3:
            continue
        prefix = alias_token[:3]
        if any(token.startswith(prefix) or prefix in token for token in query_tokens):
            return True
    return False


def resolve_location_fuzzy(text: str, supported_locations: list[dict]) -> dict:
    normalized = normalize_user_text(text)
    if not normalized["normalized_text"]:
        return _empty_result()

    entries = _build_alias_entries(supported_locations)
    if not entries:
        return _empty_result()

    exact_candidates = _whole_exact_candidates(normalized, entries)
    if len(exact_candidates) > 1:
        return _multiple_choice(exact_candidates, "exact")
    if exact_candidates:
        return _result_from_candidate(exact_candidates[0], "exact")

    alias_candidates = _clear_alias_candidates(normalized, entries)
    if len(alias_candidates) > 1:
        return _multiple_choice(alias_candidates, "alias")
    if alias_candidates:
        return _result_from_candidate(alias_candidates[0], "alias")

    fuzzy_candidates = _fuzzy_candidates(normalized, entries)
    if not fuzzy_candidates or fuzzy_candidates[0]["confidence"] < 0.60:
        return _empty_result()

    result = _result_from_candidate(fuzzy_candidates[0], "fuzzy_gazetteer")
    result["location_candidates"] = fuzzy_candidates[:5]
    return result
