from copy import copy, deepcopy

from django.core.paginator import Paginator
from django.shortcuts import render, get_object_or_404
from preferences.models import UserPreference
from .services import (
    calculate_matching_score,
    get_candidate_accommodations,
    node_value,
    preference_accommodation_types,
    preference_has_user_location,
)

SORT_OPTIONS = (
    ("distance_asc", "Gần bạn nhất"),
    ("recommended", "Phù hợp nhất"),
    ("price_asc", "Giá thấp nhất"),
    ("price_desc", "Giá cao nhất"),
    ("rating_desc", "Đánh giá cao nhất"),
    ("rating_asc", "Đánh giá thấp nhất"),
)
VALID_SORT_KEYS = {key for key, _ in SORT_OPTIONS}
TYPE_OPTIONS = (
    ("hotel", "Khách sạn"),
    ("homestay", "Homestay"),
    ("hostel", "Hostel"),
    ("apartment", "Căn hộ"),
)
AMENITY_OPTIONS = (
    ("wifi", "Wifi", "fa-wifi"),
    ("pool", "Hồ bơi", "fa-person-swimming"),
    ("parking", "Đỗ xe", "fa-square-parking"),
    ("air_conditioner", "Điều hòa", "fa-wind"),
    ("kitchen", "Bếp", "fa-kitchen-set"),
    ("washing_machine", "Máy giặt", "fa-jug-detergent"),
)
PRICE_BUCKETS = {
    "0-500k": (None, 500_000),
    "500k-1tr": (500_000, 1_000_000),
    "1tr-2tr": (1_000_000, 2_000_000),
    "2tr+": (2_000_000, None),
}
DEFAULT_PAGE_SIZE = 10


def normalize_sort_key(sort_key):
    return sort_key if sort_key in VALID_SORT_KEYS else "recommended"


def sort_scored_results(scored_results, sort_key):
    sort_key = normalize_sort_key(sort_key)

    if sort_key == "price_asc":
        return sorted(
            scored_results,
            key=lambda result: (result[0].price_per_night or float("inf"), -result[1]),
        )
    if sort_key == "price_desc":
        return sorted(
            scored_results,
            key=lambda result: (result[0].price_per_night or 0, result[1]),
            reverse=True,
        )
    if sort_key == "rating_desc":
        return sorted(
            scored_results,
            key=lambda result: (result[0].rating or 0, result[1]),
            reverse=True,
        )
    if sort_key == "rating_asc":
        return sorted(
            scored_results,
            key=lambda result: (
                result[0].rating if result[0].rating is not None else float("inf"),
                -result[1],
            ),
        )
    if sort_key == "distance_asc":
        return sorted(
            scored_results,
            key=lambda result: (getattr(result[0], "distance_km", float("inf")), -result[1]),
        )

    return sorted(scored_results, key=lambda result: result[1], reverse=True)


def recommendation_result(request, pref_id):
    preference = get_object_or_404(UserPreference, id=pref_id)
    active_preference = build_active_preference(preference, request.GET)
    default_sort = "distance_asc" if preference_has_user_location(active_preference) else "recommended"
    selected_sort = normalize_sort_key(request.GET.get("sort", default_sort))

    accommodations = get_candidate_accommodations(active_preference)

    scored_results = []

    for item in accommodations:
        # Gọi thuật toán Matching Score. Rating mặc định của DB nằm sẵn trong item.rating
        scored_results.append((item, calculate_matching_score(item, active_preference)))

    scored_results = filter_scored_results(scored_results, request.GET.get("destination", "").strip())
    scored_results = sort_scored_results(scored_results, selected_sort)
    page_size = normalize_page_size(request.GET.get("page_size"))
    paginator = Paginator(scored_results, page_size)
    page_obj = paginator.get_page(request.GET.get("page", 1))

    query_params = request.GET.copy()
    query_params.pop("page", None)

    return render(
        request,
        'recommendations/recommendation_result.html',
        {
            'preference': active_preference,
            'original_preference': preference,
            'results': page_obj.object_list,
            'page_obj': page_obj,
            'total_results': paginator.count,
            'total_pages': paginator.num_pages,
            'page_size': page_size,
            'query_string': query_params.urlencode(),
            'selected_sort': selected_sort,
            'sort_options': SORT_OPTIONS,
            'type_options': TYPE_OPTIONS,
            'amenity_options': AMENITY_OPTIONS,
            'current_types': preference_accommodation_types(active_preference),
            'current_amenities': active_preference.required_amenities or [],
            'current_budget_min': node_value(active_preference, "budget_min") or "",
            'current_budget_max': node_value(active_preference, "budget_max") or active_preference.budget or "",
            'current_price': request.GET.get("price", ""),
            'current_destination': request.GET.get("destination", ""),
            'current_guests': "" if not node_value(active_preference, "guest_count") else active_preference.guest_count,
            'relaxed': getattr(active_preference, 'relaxed', False),
            'relaxed_filters': getattr(active_preference, 'relaxed_filters', []),
            'relaxation_message': getattr(active_preference, 'relaxation_message', ''),
            'used_radius_km': getattr(active_preference, 'used_radius_km', active_preference.search_radius_km),
        },
    )


def chat_recommendation_page(request):
    return render(request, 'recommendations/chat_recommendation.html')


def build_active_preference(preference, query_params):
    active = copy(preference)
    active.filter_tree_json = deepcopy(preference.filter_tree_json or {})
    if not has_filter_override(query_params):
        return active

    replacements = []

    selected_types = selected_types_from_query(query_params)
    active.preferred_type = selected_types[0] if selected_types else None
    if selected_types:
        replacements.append(filter_node("accommodation_types", selected_types, "in"))

    budget_min, budget_max = budget_range_from_query(query_params)
    active.budget = int(budget_max or 0)
    if budget_min:
        replacements.append(filter_node("budget_min", int(budget_min), "gte"))
    if budget_max:
        replacements.append(filter_node("budget_max", int(budget_max), "lte"))

    guest_count = positive_int(query_params.get("guests"))
    active.guest_count = guest_count or 1
    if guest_count:
        replacements.append(filter_node("guest_count", guest_count, "gte_capacity"))

    amenities = [item for item in query_params.getlist("amenity") if item]
    active.required_amenities = list(dict.fromkeys(amenities))
    if active.required_amenities:
        replacements.append(filter_node("amenities", active.required_amenities, "contains"))

    active.filter_tree_json = replace_filter_nodes(
        active.filter_tree_json,
        replacements,
        {"accommodation_type", "accommodation_types", "budget_min", "budget_max", "guest_count", "amenities"},
    )
    return active


def has_filter_override(query_params) -> bool:
    if query_params.get("filters") == "1":
        return True
    return any(
        key in query_params
        for key in ("type", "types", "price", "budget_min", "budget_max", "amenity", "guests", "destination")
    )


def selected_types_from_query(query_params) -> list[str]:
    values = list(query_params.getlist("type"))
    values.extend((query_params.get("types") or "").split(","))
    allowed = {value for value, _ in TYPE_OPTIONS}
    return [value for value in dict.fromkeys(item.strip() for item in values if item.strip()) if value in allowed]


def budget_range_from_query(query_params) -> tuple[int | None, int | None]:
    price_key = query_params.get("price") or ""
    if price_key in PRICE_BUCKETS:
        return PRICE_BUCKETS[price_key]
    return positive_int(query_params.get("budget_min")), positive_int(query_params.get("budget_max"))


def positive_int(value) -> int | None:
    try:
        parsed = int(str(value or "").strip())
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def filter_node(key, value, operator) -> dict:
    return {
        "key": key,
        "value": value,
        "operator": operator,
        "strength": "soft",
        "confidence": 1.0,
        "priority": "important",
        "source": "recommendation_page",
        "reason": "result_page_filter",
    }


def replace_filter_nodes(tree: dict, replacements: list[dict], replaced_keys: set[str]) -> dict:
    tree = deepcopy(tree or {})
    nodes = [
        node for node in (tree.get("filters") or [])
        if isinstance(node, dict) and node.get("key") not in replaced_keys
    ]
    tree["filters"] = [*nodes, *replacements]
    return tree


def filter_scored_results(scored_results, destination: str):
    if not destination:
        return scored_results
    needle = destination.strip().lower()
    return [
        result for result in scored_results
        if needle in " ".join(
            str(value or "").lower()
            for value in [
                result[0].name,
                result[0].area,
                result[0].address,
                result[0].description,
            ]
        )
    ]


def normalize_page_size(value) -> int:
    size = positive_int(value) or DEFAULT_PAGE_SIZE
    return min(max(size, 5), 50)
