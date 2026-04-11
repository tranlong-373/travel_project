from __future__ import annotations

from typing import Any

from .schema import SLOTS, empty_slots


AREA_ALIAS_FLAT = {
    "sài gòn": "tp hcm",
    "sai gon": "tp hcm",
    "hồ chí minh": "tp hcm",
    "ho chi minh": "tp hcm",
    "tp hồ chí minh": "tp hcm",
    "tp ho chi minh": "tp hcm",
    "hcm": "tp hcm",
    "hcmc": "tp hcm",
    "da lat": "đà lạt",
    "da nang": "đà nẵng",
    "hoi an": "hội an",
    "hue": "huế",
    "vung tau": "vũng tàu",
    "ha noi": "hà nội",
    "phu quoc": "phú quốc",
    "mui ne": "mũi né",
    "sapa": "sapa",
    "quy nhon": "quy nhơn",
    "can tho": "cần thơ",
    "phan thiet": "phan thiết",
}


def _as_int(x: Any) -> int | None:
    if x is None or isinstance(x, bool):
        return None
    if isinstance(x, int):
        return x
    if isinstance(x, float):
        return int(x)
    if isinstance(x, str):
        xs = x.strip().replace(",", "").replace(".", "")
        if xs.isdigit():
            return int(xs)
    return None


def _as_str(x: Any) -> str | None:
    if x is None:
        return None
    if isinstance(x, str):
        s = x.strip().lower()
        return s if s else None
    return None


def _as_list_str(x: Any) -> list[str]:
    if x is None:
        return []
    if isinstance(x, list):
        out = []
        for i in x:
            if isinstance(i, str):
                v = i.strip().lower()
                if v and v not in out:
                    out.append(v)
        return out
    if isinstance(x, str) and x.strip():
        return [x.strip().lower()]
    return []


def _canonical_area(x: Any) -> str | None:
    s = _as_str(x)
    if not s:
        return None
    return AREA_ALIAS_FLAT.get(s, s)


def validate_and_normalize_slots(slots_partial: dict[str, Any]) -> dict[str, Any]:
    slots = empty_slots()
    slots.update(slots_partial or {})

    slots["area"] = _canonical_area(slots.get("area"))
    slots["budget"] = _as_int(slots.get("budget"))
    slots["guest_count"] = _as_int(slots.get("guest_count"))
    slots["preferred_type"] = _as_str(slots.get("preferred_type"))
    slots["required_amenities"] = _as_list_str(slots.get("required_amenities"))
    slots["priorities"] = _as_list_str(slots.get("priorities"))
    slots["special_requirements"] = _as_list_str(slots.get("special_requirements"))
    slots["trip_days"] = _as_int(slots.get("trip_days"))

    for k in ["preferred_type", "required_amenities", "priorities", "special_requirements"]:
        spec = SLOTS.get(k)
        if not spec or not spec.allowed:
            continue

        if k == "preferred_type":
            if slots[k] not in spec.allowed:
                slots[k] = None
        else:
            normalized = []
            for v in slots[k]:
                if v in spec.allowed and v not in normalized:
                    normalized.append(v)
            slots[k] = normalized

    # sanity check để chặn budget kiểu 900 bị lọt
    if slots["budget"] is not None and slots["budget"] < 50_000:
        slots["budget"] = None

    if slots["budget"] is not None and slots["budget"] <= 0:
        slots["budget"] = None
    if slots["guest_count"] is not None and slots["guest_count"] <= 0:
        slots["guest_count"] = None
    if slots["trip_days"] is not None and slots["trip_days"] <= 0:
        slots["trip_days"] = None

    return slots