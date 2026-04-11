from __future__ import annotations

import unicodedata

from accommodations.models import Accommodation


AMENITY_ALIASES = {
    "wifi": "wifi",
    "wi-fi": "wifi",
    "internet": "wifi",
    "dieu hoa": "air_conditioner",
    "điều hòa": "air_conditioner",
    "may lanh": "air_conditioner",
    "máy lạnh": "air_conditioner",
    "air conditioner": "air_conditioner",
    "ac": "air_conditioner",
    "bep": "kitchen",
    "bếp": "kitchen",
    "nha bep": "kitchen",
    "nhà bếp": "kitchen",
    "kitchen": "kitchen",
    "bai do xe": "parking",
    "bãi đỗ xe": "parking",
    "cho dau xe": "parking",
    "chỗ đậu xe": "parking",
    "parking": "parking",
    "ho boi": "pool",
    "hồ bơi": "pool",
    "be boi": "pool",
    "bể bơi": "pool",
    "pool": "pool",
    "may giat": "washing_machine",
    "máy giặt": "washing_machine",
    "washing machine": "washing_machine",
}

TP_HCM_LEGACY_AREA_HINTS = (
    "tp hcm",
    "tphcm",
    "ho chi minh",
    "sai gon",
    "saigon",
    "quan ",
    "quận ",
    "district ",
    "dist ",
    "thu duc",
    "thủ đức",
    "binh thanh",
    "bình thạnh",
    "tan binh",
    "tân bình",
    "phu nhuan",
    "phú nhuận",
    "thao dien",
    "thảo điền",
    "phu my hung",
    "phú mỹ hưng",
)

ADJACENT_AREAS = {
    "quan 1": ["quan 3", "quan 4", "quan 5", "quan 10", "binh thanh"],
    "quan 3": ["quan 1", "quan 10", "tan binh", "phu nhuan"],
    "quan 2": ["quan 9", "thu duc", "quan 1", "binh thanh"],
    "quan 7": ["quan 4", "nha be", "quan 8"],
}


def normalize_text(value: str | None) -> str:
    if not value:
        return ""
    text = value.strip().lower().replace("đ", "d")
    text = "".join(
        char
        for char in unicodedata.normalize("NFD", text)
        if unicodedata.category(char) != "Mn"
    )
    return " ".join(text.split())


def normalize_amenity(value: str) -> str:
    key = normalize_text(value)
    return AMENITY_ALIASES.get(key, key)


def normalize_amenities(values: list[str] | tuple[str, ...] | None) -> set[str]:
    return {normalize_amenity(value) for value in (values or []) if value}


def area_matches(accommodation_area: str, requested_area: str) -> bool:
    accom_area = normalize_text(accommodation_area)
    req_area = normalize_text(requested_area)
    if not req_area:
        return True
    if req_area in accom_area or accom_area in req_area:
        return True

    # Legacy seed rows store TP HCM only as district names such as "Quận 1".
    # Treat those as TP HCM matches without changing the canonical chat_api area.
    if req_area in {"tp hcm", "hcm", "ho chi minh", "sai gon", "saigon"}:
        return any(hint in accom_area for hint in TP_HCM_LEGACY_AREA_HINTS)

    return False


def get_adjacent_areas(area: str) -> list[str]:
    norm_area = normalize_text(area)
    for main_area, adjacent_list in ADJACENT_AREAS.items():
        if main_area in norm_area or norm_area in main_area:
            return adjacent_list
    return []


def calculate_area_score(accommodation_area: str, requested_area: str) -> float:
    if area_matches(accommodation_area, requested_area):
        return 1.0

    accom_area = normalize_text(accommodation_area)
    for adjacent_area in get_adjacent_areas(requested_area):
        if adjacent_area in accom_area:
            return 0.5

    return 0.0


def calculate_matching_score(accom: Accommodation, req) -> float:
    """Score accommodation against a structured UserPreference.

    This keeps the friend recommender's lightweight 5-point style while
    accepting canonical keys emitted by chat_api.
    """
    if accom.capacity < req.guest_count:
        return 0.0

    score = 0.0

    price = accom.price_per_night
    budget = req.budget

    if price < 1_000_000:
        base_price_score = 1.5
    elif price <= 2_000_000:
        base_price_score = 0.75
    else:
        base_price_score = 0.25

    if budget > 0 and price > budget:
        score += max(0.0, base_price_score - 0.2)
    elif budget > 0:
        score += base_price_score

    requested_amenities = normalize_amenities(req.required_amenities)
    accommodation_amenities = normalize_amenities(accom.amenities)
    if requested_amenities:
        matched = len(requested_amenities & accommodation_amenities)
        score += 1.5 * (matched / float(len(requested_amenities)))
    else:
        score += 1.5

    score += calculate_area_score(accom.area, req.area)

    if req.preferred_type and accom.accommodation_type == req.preferred_type:
        score += 0.5

    if accom.rating:
        score += 1.0 * (accom.rating / 5.0)

    return round(score, 2)


def get_candidate_accommodations(preference) -> list[Accommodation]:
    base_qs = Accommodation.objects.filter(capacity__gte=preference.guest_count)

    unique_items: dict[str, Accommodation] = {}
    for item in base_qs:
        unique_items.setdefault(item.name, item)

    candidates = list(unique_items.values())
    return [item for item in candidates if area_matches(item.area, preference.area)]
