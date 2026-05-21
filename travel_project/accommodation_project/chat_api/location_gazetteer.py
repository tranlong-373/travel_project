from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from .text_normalizer import strip_vietnamese_accents

_DVHCVN_PATH = Path(__file__).parent / "data" / "vietnamese_admin_units.json"


_FALLBACK_LOCATION_SPECS: tuple[tuple[str, str | None, str | None], ...] = (
    ("TP HCM", None, "city"),
    ("Hà Nội", None, "city"),
    ("Đà Lạt", None, "city"),
    ("Đà Nẵng", None, "city"),
    ("Cần Thơ", None, "city"),
    ("Thanh Hóa", None, "city"),
    ("Đồng Nai", None, "province"),
    ("An Giang", None, "province"),
    ("Bình Định", None, "province"),
    ("Quận 1", "TP HCM", "district"),
    ("Quận 2", "TP HCM", "district"),
    ("Quận 3", "TP HCM", "district"),
    ("Quận 4", "TP HCM", "district"),
    ("Quận 5", "TP HCM", "district"),
    ("Quận 6", "TP HCM", "district"),
    ("Quận 7", "TP HCM", "district"),
    ("Quận 8", "TP HCM", "district"),
    ("Quận 9", "TP HCM", "district"),
    ("Quận 10", "TP HCM", "district"),
    ("Quận 11", "TP HCM", "district"),
    ("Quận 12", "TP HCM", "district"),
    ("Thủ Đức", "TP HCM", "district"),
    ("Bình Thạnh", "TP HCM", "district"),
    ("Gò Vấp", "TP HCM", "district"),
    ("Tân Bình", "TP HCM", "district"),
    ("Tân Phú", "TP HCM", "district"),
    ("Phú Nhuận", "TP HCM", "district"),
    ("Củ Chi", "TP HCM", "district"),
    ("Nhà Bè", "TP HCM", "district"),
    ("Bình Chánh", "TP HCM", "district"),
)


def _normalize_phrase(text: str) -> str:
    text = (text or "").lower().strip()
    text = re.sub(r"[^\w\s]", " ", text, flags=re.UNICODE)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _add_alias_forms(aliases: set[str], value: str) -> None:
    normalized = _normalize_phrase(value)
    if not normalized:
        return

    no_accent = strip_vietnamese_accents(normalized)
    for alias in {normalized, no_accent}:
        if alias:
            aliases.add(alias)
            aliases.add(alias.replace(" ", ""))


def _name_without_city_prefix(canonical_name: str) -> str | None:
    normalized = _normalize_phrase(canonical_name)
    without_prefix = re.sub(r"^(?:tp|thành phố|thanh pho)\s+", "", normalized, count=1)
    return without_prefix if without_prefix != normalized and without_prefix else None


def _district_number(canonical_name: str) -> str | None:
    no_accent = strip_vietnamese_accents(_normalize_phrase(canonical_name))
    match = re.fullmatch(r"(?:quan|q|district)\s*(\d+)", no_accent)
    return match.group(1) if match else None


def _is_thu_duc(canonical_name: str) -> bool:
    no_accent = strip_vietnamese_accents(_normalize_phrase(canonical_name))
    no_accent = re.sub(r"^(?:tp|thanh pho)\s+", "", no_accent, count=1)
    return no_accent == "thu duc"


# Non-derivable city synonyms ONLY consulted by canonicalize_area_name (v2 path).
# Kept out of generate_location_aliases() so v1's fuzzy_location resolver does
# not start matching "Sài Gòn" in unrelated POI/text and breaking tests like
# test_required_standalone_pois_resolve_as_near_anchor.
_V2_EXTRA_CITY_SYNONYMS: dict[str, str] = {
    # synonym (normalized no-accent) → canonical display name
    "sai gon": "TP HCM",
    "saigon": "TP HCM",
    "sg": "TP HCM",
    "ho chi minh": "TP HCM",
    "ho chi minh city": "TP HCM",
    "hcmc": "TP HCM",
    "tp ho chi minh": "TP HCM",
    "thanh pho ho chi minh": "TP HCM",
    "hanoi": "Hà Nội",
}


def generate_location_aliases(
    canonical_name: str,
    city: str | None = None,
    type: str | None = None,
) -> set[str]:
    aliases: set[str] = set()
    _add_alias_forms(aliases, canonical_name)

    number = _district_number(canonical_name)
    if number:
        _add_alias_forms(aliases, f"quận {number}")
        _add_alias_forms(aliases, f"quan {number}")
        _add_alias_forms(aliases, f"q{number}")
        _add_alias_forms(aliases, f"district {number}")

    city_name = _name_without_city_prefix(canonical_name)
    if city_name:
        no_accent_city_name = strip_vietnamese_accents(city_name)
        _add_alias_forms(aliases, f"tp {city_name}")
        _add_alias_forms(aliases, f"thành phố {city_name}")
        _add_alias_forms(aliases, f"thanh pho {no_accent_city_name}")
        _add_alias_forms(aliases, city_name)
        _add_alias_forms(aliases, f"{city_name} city")
    elif _is_thu_duc(canonical_name):
        _add_alias_forms(aliases, f"tp {canonical_name}")
        _add_alias_forms(aliases, f"thành phố {canonical_name}")
        _add_alias_forms(aliases, "thanh pho thu duc")
        _add_alias_forms(aliases, f"{canonical_name} city")
    elif type == "city":
        _add_alias_forms(aliases, f"{canonical_name} city")

    if city:
        _add_alias_forms(aliases, f"{canonical_name} {city}")

    return aliases


def _location_entry(canonical_name: str, city: str | None, type: str | None) -> dict:
    aliases = generate_location_aliases(canonical_name, city=city, type=type)
    return {
        "canonical_name": canonical_name,
        "city": city,
        "type": type,
        "aliases": sorted(aliases),
    }


def _fallback_locations() -> list[dict]:
    return [_location_entry(name, city, location_type) for name, city, location_type in _FALLBACK_LOCATION_SPECS]


def _load_dvhcvn_units() -> list[dict]:
    """Load phường/xã/thị trấn từ dvhcvn dataset và tạo alias entries."""
    try:
        raw = json.loads(_DVHCVN_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []

    entries: list[dict] = []
    for province in raw.get("provinces", []):
        province_name: str = province.get("name", "")
        for district in province.get("districts", []):
            district_name: str = district.get("name", "")
            district_type: str = district.get("type", "district")
            entries.append(_location_entry(district_name, province_name, district_type))
            for ward in district.get("wards", []):
                ward_name: str = ward.get("name", "")
                if not ward_name:
                    continue
                # Alias cả có prefix (Phường Bến Nghé) lẫn không (Bến Nghé)
                short_name = re.sub(
                    r"^(?:phường|xã|thị trấn|thi tran)\s+",
                    "",
                    ward_name,
                    flags=re.IGNORECASE,
                )
                extra_aliases: set[str] = set()
                if short_name and short_name.lower() != ward_name.lower():
                    _add_alias_forms(extra_aliases, short_name)
                    _add_alias_forms(extra_aliases, f"{short_name} {district_name}")
                entry = _location_entry(ward_name, district_name, "ward")
                if extra_aliases:
                    entry["aliases"] = sorted(set(entry["aliases"]) | extra_aliases)
                entries.append(entry)
    return entries


def _model_location_type(model_name: str) -> str | None:
    if "district" in model_name:
        return "district"
    if "city" in model_name or "province" in model_name:
        return "city"
    if "landmark" in model_name:
        return "landmark"
    if "location" in model_name or "area" in model_name:
        return "location"
    return None


def _string_value(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _locations_from_database() -> list[dict]:
    try:
        from django.apps import apps

        if not apps.ready:
            return []

        locations: list[dict] = []
        seen: set[str] = set()

        for model in apps.get_models():
            model_name = model._meta.model_name.lower()
            field_names = {field.name for field in model._meta.fields}

            if model_name == "accommodation" and "area" in field_names:
                areas = (
                    model.objects.exclude(area__isnull=True)
                    .exclude(area__exact="")
                    .values_list("area", flat=True)
                    .distinct()[:500]
                )
                for area in areas:
                    canonical_name = _string_value(area)
                    if not canonical_name:
                        continue
                    key = strip_vietnamese_accents(_normalize_phrase(canonical_name))
                    if key in seen:
                        continue
                    seen.add(key)
                    locations.append(_location_entry(canonical_name, None, "area"))
                continue

            location_type = _model_location_type(model_name)
            name_field = next(
                (field for field in ("canonical_name", "name", "title") if field in field_names),
                None,
            )
            if not location_type or not name_field:
                continue

            for instance in model.objects.all()[:500]:
                canonical_name = _string_value(getattr(instance, name_field, None))
                if not canonical_name:
                    continue
                key = strip_vietnamese_accents(_normalize_phrase(canonical_name))
                if key in seen:
                    continue
                seen.add(key)

                city = None
                for city_field in ("city", "province", "parent_city"):
                    if city_field in field_names:
                        city = _string_value(getattr(instance, city_field, None))
                        break

                locations.append(_location_entry(canonical_name, city, location_type))

        return locations
    except Exception:
        return []


def _location_merge_key(canonical_name: str) -> str:
    no_accent = strip_vietnamese_accents(_normalize_phrase(canonical_name))
    without_city_prefix = re.sub(r"^(?:tp|thanh pho)\s+", "", no_accent, count=1)
    if without_city_prefix == "thu duc":
        return without_city_prefix
    return no_accent


@lru_cache(maxsize=1)
def _load_supported_locations_cached() -> tuple[dict, ...]:
    db_locations = _locations_from_database()
    dvhcvn_locations = _load_dvhcvn_units()
    locations = _merge_locations(_fallback_locations(), dvhcvn_locations, db_locations)
    return tuple(locations)


def load_supported_locations() -> list[dict]:
    return [
        {
            "canonical_name": location["canonical_name"],
            "city": location.get("city"),
            "type": location.get("type"),
            "aliases": list(location.get("aliases", [])),
        }
        for location in _load_supported_locations_cached()
    ]


@lru_cache(maxsize=1)
def _alias_to_canonical_index() -> dict[str, str]:
    """Lookup table: every alias (and its compact form) → canonical_name.

    Built once from the cached gazetteer.  Reused by v2 NLU so area_hint
    from the classifier (which is normalized/no-accent) can be mapped back
    to display form like "Quận 3", "Bình Thạnh".
    """
    index: dict[str, str] = {}
    for entry in _load_supported_locations_cached():
        canonical = entry.get("canonical_name") or ""
        if not canonical:
            continue
        for alias in entry.get("aliases", []):
            if alias and alias not in index:
                index[alias] = canonical
        # Also map the canonical itself (lowercased + no-accent + compact)
        norm_canonical = _normalize_phrase(canonical)
        no_accent = strip_vietnamese_accents(norm_canonical)
        for form in {norm_canonical, no_accent, no_accent.replace(" ", "")}:
            index.setdefault(form, canonical)
    return index


def canonicalize_area_name(text: str | None) -> str | None:
    """Return the canonical display form of an area string, or None on no match.

    Accepts inputs in any form: with/without accents, compact ("binhthanh"),
    short prefix ("q3"), full ("Quận 3"). Returns the gazetteer's canonical
    name ("Quận 3", "Bình Thạnh", "TP HCM", ...).
    """
    if not text:
        return None
    raw = str(text).strip()
    if not raw:
        return None
    index = _alias_to_canonical_index()
    candidates: list[str] = []
    norm = _normalize_phrase(raw)
    no_accent = strip_vietnamese_accents(norm)
    candidates.extend([raw, raw.lower(), norm, no_accent, no_accent.replace(" ", "")])
    for cand in candidates:
        if not cand:
            continue
        if cand in index:
            return index[cand]
        if cand in _V2_EXTRA_CITY_SYNONYMS:
            return _V2_EXTRA_CITY_SYNONYMS[cand]
    return None


def _merge_locations(*groups: list[dict]) -> list[dict]:
    merged: dict[str, dict] = {}
    for group in groups:
        for location in group:
            key = _location_merge_key(location.get("canonical_name") or "")
            if not key:
                continue
            if key not in merged:
                merged[key] = {
                    "canonical_name": location["canonical_name"],
                    "city": location.get("city"),
                    "type": location.get("type"),
                    "aliases": set(location.get("aliases") or []),
                }
            else:
                merged[key]["aliases"].update(location.get("aliases") or [])
                merged[key]["city"] = merged[key].get("city") or location.get("city")
                merged[key]["type"] = merged[key].get("type") or location.get("type")

    return [
        {
            "canonical_name": location["canonical_name"],
            "city": location.get("city"),
            "type": location.get("type"),
            "aliases": sorted(location["aliases"]),
        }
        for location in merged.values()
    ]
