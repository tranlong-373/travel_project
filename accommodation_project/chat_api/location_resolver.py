from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from .normalizers import normalize_key

LocationStatus = Literal["ok", "multiple_choice", "conflict", "unsupported", "unresolved"]

DATA_DIR = Path(__file__).resolve().parent / "data"


@dataclass(frozen=True)
class AliasEntry:
    alias: str
    area_id: str
    canonical_area: str
    supported: bool
    source: str
    label: str
    category: str | None = None
    importance: int = 0


def _load_json(name: str) -> Any:
    path = DATA_DIR / name
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


@lru_cache(maxsize=1)
def _reference_data() -> dict[str, Any]:
    supported_areas = _load_json("supported_areas.json")
    landmarks = _load_json("landmarks.json")
    rules = _load_json("location_rules.json")

    supported_by_id = {area["id"]: area for area in supported_areas if area.get("supported")}
    unsupported_by_id = {area["id"]: area for area in rules.get("unsupported_areas", [])}
    aliases: list[AliasEntry] = []

    for area in supported_areas:
        if not area.get("supported"):
            continue
        area_id = area["parent_id"] or area["id"]
        canonical_area = supported_by_id[area_id]["canonical_name"]
        for alias in area.get("aliases", []):
            aliases.append(
                AliasEntry(
                    alias=normalize_key(alias),
                    area_id=area_id,
                    canonical_area=canonical_area,
                    supported=True,
                    source="area",
                    label=area["canonical_name"],
                    category=area.get("type"),
                    importance=70,
                )
            )

    for area in rules.get("unsupported_areas", []):
        for alias in area.get("aliases", []):
            aliases.append(
                AliasEntry(
                    alias=normalize_key(alias),
                    area_id=area["id"],
                    canonical_area=area["canonical_name"],
                    supported=False,
                    source="unsupported_area",
                    label=area["canonical_name"],
                    category="unsupported_area",
                    importance=60,
                )
            )

    for landmark in landmarks:
        parent_area_id = landmark["parent_area_id"]
        parent_supported = parent_area_id in supported_by_id
        parent_area = supported_by_id.get(parent_area_id) or unsupported_by_id.get(parent_area_id)
        canonical_area = parent_area["canonical_name"] if parent_area else parent_area_id
        for alias in landmark.get("aliases", []):
            aliases.append(
                AliasEntry(
                    alias=normalize_key(alias),
                    area_id=parent_area_id,
                    canonical_area=canonical_area,
                    supported=parent_supported,
                    source="landmark",
                    label=landmark["name"],
                    category=landmark.get("category"),
                    importance=int(landmark.get("importance") or 0),
                )
            )

    aliases = [entry for entry in aliases if entry.alias]
    aliases.sort(key=lambda entry: (len(entry.alias), entry.importance), reverse=True)

    return {
        "supported_by_id": supported_by_id,
        "unsupported_by_id": unsupported_by_id,
        "aliases": aliases,
        "multiple_choice_phrases": [normalize_key(p) for p in rules.get("multiple_choice_phrases", [])],
    }


def _overlaps(span: tuple[int, int], spans: list[tuple[int, int]]) -> bool:
    start, end = span
    return any(start < used_end and end > used_start for used_start, used_end in spans)


def extract_location_mentions(text: str) -> list[dict[str, Any]]:
    norm = normalize_key(text)
    if not norm:
        return []

    matches: list[dict[str, Any]] = []
    used_spans: list[tuple[int, int]] = []

    for entry in _reference_data()["aliases"]:
        for match in re.finditer(rf"(?<!\w){re.escape(entry.alias)}(?!\w)", norm):
            span = (match.start(), match.end())
            if _overlaps(span, used_spans):
                continue
            used_spans.append(span)
            matches.append(
                {
                    "matched_text": match.group(0),
                    "area_id": entry.area_id,
                    "canonical_area": entry.canonical_area,
                    "supported": entry.supported,
                    "source": entry.source,
                    "label": entry.label,
                    "category": entry.category,
                    "importance": entry.importance,
                    "span": [match.start(), match.end()],
                }
            )
            break

    matches.sort(key=lambda item: (item["span"][0], -item["importance"]))
    return matches


def _has_choice_phrase(text: str) -> bool:
    norm = normalize_key(text)
    for phrase in _reference_data()["multiple_choice_phrases"]:
        if phrase and re.search(rf"(?<!\w){re.escape(phrase)}(?!\w)", norm):
            return True
    return False


def _unique_candidates(mentions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    candidates: list[dict[str, Any]] = []
    for mention in mentions:
        key = mention["area_id"]
        if key in seen:
            continue
        seen.add(key)
        candidates.append(
            {
                "area_id": mention["area_id"],
                "canonical_area": mention["canonical_area"],
                "supported": mention["supported"],
                "matched_text": mention["matched_text"],
                "source": mention["source"],
                "label": mention["label"],
            }
        )
    return candidates


def _question(locale: str, vi: str, en: str) -> str:
    return en if locale == "en" else vi


def resolve_location(text: str, *, locale: str = "vi") -> dict[str, Any]:
    mentions = extract_location_mentions(text)
    if not mentions:
        return {
            "location_status": "unresolved",
            "location_candidates": [],
            "canonical_area": None,
            "follow_up_question": None,
            "debug": {"mentions": []},
        }

    supported_mentions = [mention for mention in mentions if mention["supported"]]
    unsupported_mentions = [mention for mention in mentions if not mention["supported"]]
    supported_area_ids = {mention["area_id"] for mention in supported_mentions}
    candidates = _unique_candidates(mentions)

    if unsupported_mentions and not supported_mentions:
        names = ", ".join(dict.fromkeys(mention["canonical_area"] for mention in unsupported_mentions))
        return {
            "location_status": "unsupported",
            "location_candidates": candidates,
            "canonical_area": None,
            "follow_up_question": _question(
                locale,
                f"Hiện mình chỉ hỗ trợ TP HCM, Hà Nội, Thanh Hóa, Đồng Nai, An Giang và Bình Định. Bạn muốn chọn nơi nào trong các khu vực này thay cho {names}?",
                f"I currently support TP HCM, Hanoi, Thanh Hoa, Dong Nai, An Giang, and Binh Dinh. Which of these should I use instead of {names}?",
            ),
            "debug": {"mentions": mentions},
        }

    if unsupported_mentions and supported_mentions:
        names = ", ".join(dict.fromkeys(mention["canonical_area"] for mention in unsupported_mentions))
        return {
            "location_status": "unsupported",
            "location_candidates": candidates,
            "canonical_area": None,
            "follow_up_question": _question(
                locale,
                f"Mình thấy có địa điểm ngoài phạm vi hỗ trợ ({names}). Bạn muốn tìm trong TP HCM, Hà Nội, Thanh Hóa, Đồng Nai, An Giang hay Bình Định?",
                f"I found unsupported locations ({names}). Should I search in TP HCM, Hanoi, Thanh Hoa, Dong Nai, An Giang, or Binh Dinh?",
            ),
            "debug": {"mentions": mentions},
        }

    if len(supported_area_ids) == 1:
        area_id = next(iter(supported_area_ids))
        canonical_area = next(mention["canonical_area"] for mention in supported_mentions if mention["area_id"] == area_id)
        return {
            "location_status": "ok",
            "location_candidates": _unique_candidates(supported_mentions),
            "canonical_area": canonical_area,
            "follow_up_question": None,
            "debug": {"mentions": mentions},
        }

    if _has_choice_phrase(text):
        choices = ", ".join(candidate["canonical_area"] for candidate in _unique_candidates(supported_mentions))
        return {
            "location_status": "multiple_choice",
            "location_candidates": _unique_candidates(supported_mentions),
            "canonical_area": None,
            "follow_up_question": _question(
                locale,
                f"Bạn muốn chốt khu vực nào: {choices}?",
                f"Which area should I use: {choices}?",
            ),
            "debug": {"mentions": mentions},
        }

    choices = ", ".join(candidate["canonical_area"] for candidate in _unique_candidates(supported_mentions))
    return {
        "location_status": "conflict",
        "location_candidates": _unique_candidates(supported_mentions),
        "canonical_area": None,
        "follow_up_question": _question(
            locale,
            f"Mình thấy các địa điểm không cùng khu vực ({choices}). Bạn xác nhận giúp mình muốn tìm ở đâu?",
            f"I found locations from different areas ({choices}). Which one should I use?",
        ),
        "debug": {"mentions": mentions},
    }
