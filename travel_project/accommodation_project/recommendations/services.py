from __future__ import annotations

import unicodedata
from math import asin, cos, radians, sin, sqrt
from typing import Any

from accommodations.models import Accommodation

DEFAULT_NEARBY_RADIUS_KM = 10.0
BUDGET_RELAXATION_MULTIPLIER = 1.15
RADIUS_RELAXATION_MULTIPLIER = 2.0
NEARBY_RADIUS_STEPS_KM = (2.5, 5.0, 8.0, 10.0, 15.0, 20.0)
NEARBY_LOCATION_MODES = {"near_anchor", "near_user", "city_center"}
COORDINATE_ORIGIN_TYPES = {"anchor", "semantic_center", "user_location"}

AMENITY_ALIASES = {
    # Từ khóa Wifi
    "wifi": "wifi", "wi-fi": "wifi", "internet": "wifi", "mang": "wifi", "mạng": "wifi", "wi fi": "wifi", "cap quang": "wifi", "cáp quang": "wifi", "mang meo": "wifi", "mạng mẽo": "wifi",
    
    # Từ khóa Máy lạnh / Điều hòa
    "dieu hoa": "air_conditioner", "điều hòa": "air_conditioner", "may lanh": "air_conditioner", "máy lạnh": "air_conditioner", "air conditioner": "air_conditioner", "ac": "air_conditioner", "may dieu hoa": "air_conditioner", "máy điều hòa": "air_conditioner", "may quat": "air_conditioner", "máy quạt": "air_conditioner", "lam mat": "air_conditioner", "làm mát": "air_conditioner",
    
    # Từ khóa Bếp
    "bep": "kitchen", "bếp": "kitchen", "nha bep": "kitchen", "nhà bếp": "kitchen", "kitchen": "kitchen", "nau an": "kitchen", "nấu ăn": "kitchen", "cho nau": "kitchen", "chỗ nấu": "kitchen", "tu nau": "kitchen", "tự nấu": "kitchen", "nau nuong": "kitchen", "nấu nướng": "kitchen", "lo vi song": "kitchen", "lò vi sóng": "kitchen",
    
    # Từ khóa Bãi đỗ xe
    "bai do xe": "parking", "bãi đỗ xe": "parking", "cho dau xe": "parking", "chỗ đậu xe": "parking", "parking": "parking", "giu xe": "parking", "giữ xe": "parking", "do xe": "parking", "đỗ xe": "parking", "gui xe": "parking", "gửi xe": "parking", "cho de xe": "parking", "chỗ để xe": "parking", "gara": "parking", "garage": "parking",
    
    # Từ khóa Hồ bơi
    "ho boi": "pool", "hồ bơi": "pool", "be boi": "pool", "bể bơi": "pool", "pool": "pool", "be tam": "pool", "bể tắm": "pool", "cho boi": "pool", "chỗ bơi": "pool", "boi loi": "pool", "bơi lội": "pool",
    
    # Từ khóa Máy giặt
    "may giat": "washing_machine", "máy giặt": "washing_machine", "washing machine": "washing_machine", "giat do": "washing_machine", "giặt đồ": "washing_machine", "giat ui": "washing_machine", "giặt ủi": "washing_machine", "giat la": "washing_machine", "giặt là": "washing_machine", "may say": "washing_machine", "máy sấy": "washing_machine", "cho phoi": "washing_machine", "chỗ phơi": "washing_machine",
    
    # Từ khóa Bữa sáng
    "an sang": "breakfast", "ăn sáng": "breakfast", "bua sang": "breakfast", "bữa sáng": "breakfast", "breakfast": "breakfast", "buffet": "breakfast", "diem tam": "breakfast", "điểm tâm": "breakfast", "bao an sang": "breakfast", "bao ăn sáng": "breakfast",
    
    # Từ khóa Đưa đón sân bay
    "dua don": "airport_shuttle", "đưa đón": "airport_shuttle", "san bay": "airport_shuttle", "sân bay": "airport_shuttle", "airport shuttle": "airport_shuttle", "shuttle": "airport_shuttle", "don san bay": "airport_shuttle", "đón sân bay": "airport_shuttle", "xe don khach": "airport_shuttle", "xe đón khách": "airport_shuttle",
    
    # Từ khóa Lễ tân / 24h
    "le tan": "front_desk", "lễ tân": "front_desk", "24/7": "front_desk", "24h": "front_desk", "front desk": "front_desk", "reception": "front_desk", "tiep tan": "front_desk", "tiếp tân": "front_desk", "24/24": "front_desk", "nhan phong dem": "front_desk", "nhận phòng đêm": "front_desk",
    
    # Từ khóa Gym / Thể hình
    "gym": "gym", "phong gym": "gym", "phòng gym": "gym", "the hinh": "gym", "thể hình": "gym", "phong tap": "gym", "phòng tập": "gym", "tap gym": "gym", "tập gym": "gym",
    
    # Từ khóa Spa / Massage
    "spa": "spa", "massage": "spa", "xong hoi": "spa", "xông hơi": "spa", "mat xa": "spa", "mát xa": "spa", "massa": "spa", "tam quat": "spa", "tẩm quất": "spa", "thu gian": "spa", "thư giãn": "spa",
    
    # Từ khóa Thang máy
    "thang may": "elevator", "thang máy": "elevator", "elevator": "elevator",
    
    # Từ khóa Thú cưng
    "thu cung": "pet_friendly", "thú cưng": "pet_friendly", "cho meo": "pet_friendly", "chó mèo": "pet_friendly", "pet": "pet_friendly", "pet friendly": "pet_friendly", "thu nuoi": "pet_friendly", "thú nuôi": "pet_friendly", "mang cho": "pet_friendly", "mang chó": "pet_friendly"
}

TP_HCM_LEGACY_AREA_HINTS = (
    "tp hcm", "tphcm", "ho chi minh", "hồ chí minh", "sài gòn", "sai gon", "saigon", "hcm",
    "quan ", "quận ", "district ", "dist ", "q.", "q",
    "thu duc", "thủ đức", "binh thanh", "bình thạnh", "tan binh", "tân bình", 
    "phu nhuan", "phú nhuận", "thao dien", "thảo điền", "phu my hung", "phú mỹ hưng",
    "go vap", "gò vấp", "tan phu", "tân phú", "binh tan", "bình tân",
    "nha be", "nhà bè", "hoc mon", "hóc môn", "cu chi", "củ chi", "binh chanh", "bình chánh", "can gio", "cần giờ",
)

ADJACENT_AREAS = {
    "quan 1": ["quan 3", "quận 3", "quan 4", "quận 4", "quan 5", "quận 5", "quan 10", "quận 10", "binh thanh", "bình thạnh", "phu nhuan", "phú nhuận"],
    "quan 2": ["quan 9", "quận 9", "thu duc", "thủ đức", "quan 1", "quận 1", "binh thanh", "bình thạnh"],
    "quan 3": ["quan 1", "quận 1", "quan 10", "quận 10", "tan binh", "tân bình", "phu nhuan", "phú nhuận"],
    "quan 4": ["quan 1", "quan 1", "quan 7", "quận 7", "quan 8", "quận 8", "quan 5", "quận 5"],
    "quan 5": ["quan 1", "quan 1", "quan 6", "quận 6", "quan 10", "quận 10", "quan 11", "quận 11", "quan 8", "quận 8"],
    "quan 6": ["quan 5", "quận 5", "quan 11", "quận 11", "binh tan", "bình tân", "quan 8", "quận 8"],
    "quan 7": ["quan 4", "quận 4", "nha be", "nhà bè", "quan 8", "quận 8", "binh chanh", "bình chánh"],
    "quan 8": ["quan 4", "quận 4", "quan 5", "quận 5", "quan 6", "quận 6", "quan 7", "quận 7", "binh chanh", "bình chánh"],
    "quan 9": ["quan 2", "quận 2", "thu duc", "thủ đức"],
    "quan 10": ["quan 1", "quận 1", "quan 3", "quận 3", "quan 5", "quận 5", "quan 11", "quận 11", "tan binh", "tân bình"],
    "quan 11": ["quan 5", "quận 5", "quan 6", "quận 6", "quan 10", "quận 10", "tan binh", "tân bình", "tan phu", "tân phú"],
    "quan 12": ["hoc mon", "hóc môn", "go vap", "gò vấp", "tan binh", "tân bình", "binh thanh", "bình thạnh", "thu duc", "thủ đức"],
    "binh thanh": ["quan 1", "quận 1", "quan 2", "quận 2", "phu nhuan", "phú nhuận", "go vap", "gò vấp", "quan 12", "quận 12", "thu duc", "thủ đức"],
    "phu nhuan": ["quan 1", "quận 1", "quan 3", "quận 3", "binh thanh", "bình thạnh", "tan binh", "tân bình", "go vap", "gò vấp"],
    "go vap": ["binh thanh", "bình thạnh", "phu nhuan", "phú nhuận", "tan binh", "tân bình", "quan 12", "quận 12"],
    "tan binh": ["quan 3", "quận 3", "quan 10", "quận 10", "quan 11", "quận 11", "tan phu", "tân phú", "phu nhuan", "phú nhuận", "go vap", "gò vấp", "quan 12", "quận 12"],
    "tan phu": ["tan binh", "tân bình", "quan 11", "quận 11", "binh tan", "bình tân", "quan 6", "quận 6"],
    "binh tan": ["quan 6", "quận 6", "quan 8", "quận 8", "tan phu", "tân phú", "binh chanh", "bình chánh"],
    "thu duc": ["quan 2", "quận 2", "quan 9", "quận 9", "binh thanh", "bình thạnh", "quan 12", "quận 12"],
    "nha be": ["quan 7", "quận 7", "binh chanh", "bình chánh", "can gio", "cần giờ"],
    "binh chanh": ["quan 7", "quận 7", "quan 8", "quận 8", "binh tan", "bình tân", "nha be", "nhà bè", "hoc mon", "hóc môn"],
    "hoc mon": ["quan 12", "quận 12", "cu chi", "củ chi", "binh chanh", "bình chánh"],
    "cu chi": ["hoc mon", "hóc môn"],
    "can gio": ["nha be", "nhà bè"],
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
    """Tìm các khu vực lân cận để lấy lại một phần điểm vị trí"""
    norm_area = normalize_text(area)
    for main_area, adjacent_list in ADJACENT_AREAS.items():
        if main_area in norm_area or norm_area in main_area:
            return adjacent_list
    return []


def calculate_area_score(accommodation_area: str, requested_area: str) -> float:
    if area_matches(accommodation_area, requested_area):
        return 1.0

    accom_area = normalize_text(accommodation_area)
    for idx, adjacent_area in enumerate(get_adjacent_areas(requested_area)):
        if adjacent_area in accom_area:
            return max(0.4, 0.8 - idx * 0.2)

    return 0.0


def preference_has_user_location(req) -> bool:
    origin = preference_search_origin(req)
    return (
        origin["type"] == "user_location"
        and origin["latitude"] is not None
        and origin["longitude"] is not None
    )


def preference_has_coordinate_origin(req) -> bool:
    origin = preference_search_origin(req)
    return (
        origin["type"] in COORDINATE_ORIGIN_TYPES
        and origin["latitude"] is not None
        and origin["longitude"] is not None
    )


def preference_search_origin(req) -> dict[str, Any]:
    tree = preference_filter_tree(req)
    origin = tree.get("search_origin")
    if isinstance(origin, dict):
        return _normalize_search_origin(origin, req)

    location = tree.get("location") or {}
    mode = preference_location_mode(req)
    origin_type = {
        "area": "area",
        "city_center": "semantic_center",
        "near_anchor": "anchor",
        "near_user": "user_location",
    }.get(mode, "none")
    label = (
        getattr(req, "location_label", None)
        or location.get("location_display_label")
        or location.get("canonical_area")
        or getattr(req, "area", None)
    )
    return _normalize_search_origin(
        {
            "type": origin_type,
            "label": label,
            "latitude": getattr(req, "user_latitude", None),
            "longitude": getattr(req, "user_longitude", None),
            "radius_km": getattr(req, "search_radius_km", None),
        },
        req,
    )


def preference_location_mode(req) -> str:
    filter_tree = preference_filter_tree(req)
    return (
        getattr(req, "location_mode", None)
        or (filter_tree.get("location") or {}).get("mode")
        or "unknown"
    )


def preference_filter_tree(req) -> dict[str, Any]:
    tree = getattr(req, "filter_tree_json", None) or {}
    return tree if isinstance(tree, dict) else {}


def filter_nodes(req) -> list[dict[str, Any]]:
    nodes = preference_filter_tree(req).get("filters") or []
    return [node for node in nodes if isinstance(node, dict)]


def has_filter_node(req, key: str) -> bool:
    nodes = filter_nodes(req)
    if key == "accommodation_type" and any(node.get("key") == "accommodation_types" for node in nodes):
        return True
    if not nodes:
        if key == "budget_max":
            return bool(getattr(req, "budget", 0))
        if key == "budget_min":
            return node_value(req, "budget_min") is not None
        if key == "guest_count":
            return bool(getattr(req, "guest_count", 0))
        if key == "accommodation_type":
            return bool(getattr(req, "preferred_type", None))
        if key == "amenities":
            return bool(getattr(req, "required_amenities", None))
        if key == "rating":
            return node_value(req, "rating") is not None
        return False
    return any(node.get("key") == key for node in nodes)


def node_value(req, key: str, default: Any = None) -> Any:
    for node in filter_nodes(req):
        if node.get("key") == key:
            return node.get("value", default)
    if key == "accommodation_type":
        for node in filter_nodes(req):
            if node.get("key") == "accommodation_types":
                return node.get("value", default)
    return default


def preference_accommodation_types(req) -> list[str]:
    values: list[str] = []
    node_types = node_value(req, "accommodation_types")
    if node_types is None:
        node_types = node_value(req, "accommodation_type")
    if isinstance(node_types, str):
        values.append(node_types)
    elif isinstance(node_types, (list, tuple, set)):
        values.extend(str(item) for item in node_types)
    if getattr(req, "preferred_type", None):
        values.append(req.preferred_type)
    return [
        value for value in dict.fromkeys(item.strip() for item in values if item and item.strip())
        if value in {"hotel", "homestay", "hostel", "apartment"}
    ]


def haversine_distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius_km = 6371.0
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return 2 * radius_km * asin(sqrt(a))


def accommodation_distance_km(accom: Accommodation, req) -> float | None:
    origin = preference_search_origin(req)
    if origin["type"] not in COORDINATE_ORIGIN_TYPES:
        return None
    lat = accom.latitude
    lon = accom.longitude
    if lat is None or lon is None or origin["latitude"] is None or origin["longitude"] is None:
        return None
    return haversine_distance_km(
        float(origin["latitude"]),
        float(origin["longitude"]),
        float(lat),
        float(lon),
    )


def calculate_distance_score(distance_km: float | None, radius_km: float) -> float:
    if distance_km is None:
        return 0.0
    if distance_km <= 1:
        return 1.0
    return max(0.0, 1.0 - (distance_km / max(radius_km, 1.0)))


def is_quality_first_request(req) -> bool:
    return (
        not getattr(req, "area", None)
        and not getattr(req, "budget", None)
        and not getattr(req, "required_amenities", None)
        and getattr(req, "guest_count", 1) == 1
        and getattr(req, "preferred_type", None) == "hotel"
    )


def calculate_matching_score(accom: Accommodation, req) -> float:
    """Tính điểm phù hợp (tối đa 5.0) theo phương pháp MCDM, có Context-Aware và Bayesian Average."""

    if is_quality_first_request(req):
        rating = accom.rating or 0
        return round(float(rating), 2)

    has_guest_filter = has_filter_node(req, "guest_count")
    has_budget_filter = has_filter_node(req, "budget_max")

    # Ràng buộc cứng: Sức chứa không đủ -> rớt ngay khi user có nói số khách.
    if has_guest_filter and accom.capacity < req.guest_count:
        return 0.0

    price = accom.price_per_night
    budget = req.budget

    # Ràng buộc cứng: Vượt budget quá 15% -> rớt ngay khi có budget.
    if has_budget_filter and budget and budget > 0 and price > budget * BUDGET_RELAXATION_MULTIPLIER:
        return 0.0

    # Trọng số các tiêu chí (tổng = 5.0)
    # Tự động điều chỉnh trọng số dựa trên ngữ cảnh: Đi gia đình/nhóm thì tiện ích quan trọng hơn
    is_group_trip = has_guest_filter and req.guest_count >= 3
    WEIGHTS = {
        "price": 1.25,
        "amenities": 1.2 if is_group_trip else 1.0,
        "location": 1.25,
        "quality": 1.0,
        "type": 0.3 if is_group_trip else 0.5
    }
    if preference_location_mode(req) in NEARBY_LOCATION_MODES and preference_has_coordinate_origin(req):
        WEIGHTS["location"] = 1.8
        WEIGHTS["price"] = 1.0
        WEIGHTS["amenities"] = 1.2 if is_group_trip else 1.0
        WEIGHTS["quality"] = 0.8
        WEIGHTS["type"] = 0.2 if is_group_trip else 0.4
    
    # Cân bằng lại tổng trọng số về đúng 5.0
    total_weight = sum(WEIGHTS.values())
    for k in WEIGHTS:
        WEIGHTS[k] = (WEIGHTS[k] / total_weight) * 5.0
        
    scores = {}

    # 1. Điểm giá thành (Price Score) [0.0 - 1.0]
    if has_budget_filter and budget and budget > 0:
        ratio = price / budget
        
        if ratio < 0.5:
            # Giá quá thấp (dưới 50% ngân sách) -> Sai phân khúc, phạt điểm giảm dần về 0.2
            scores["price"] = 0.2 + (ratio / 0.5) * 0.6
        elif ratio <= 0.8:
            # Vùng giá lý tưởng (50% - 80% ngân sách) -> Đạt điểm tối đa (1.0) khi ở mốc 80%
            scores["price"] = 0.8 + ((ratio - 0.5) / 0.3) * 0.2
        elif ratio <= 1.0:
            # Gần sát ngân sách (80% - 100%) -> Hơi đắt nhưng vẫn trong ngân sách
            scores["price"] = 1.0 - ((ratio - 0.8) / 0.2) * 0.2
        else:
            # Vượt ngân sách (nhưng chưa quá 15%) -> Giảm dần từ 0.8 về 0.4
            excess = price - budget
            max_allowed_excess = budget * (BUDGET_RELAXATION_MULTIPLIER - 1.0)
            scores["price"] = max(0.4, 0.8 - 0.4 * (excess / max_allowed_excess))
    else:
        # Rational Decay cho người không nhập budget
        scores["price"] = 1.0 / (1.0 + (price / 2_000_000))

    # 2. Điểm tiện ích (Amenities Score) [0.0 - 1.0] - Context-Aware
    requested_amenities = normalize_amenities(req.required_amenities)
    accommodation_amenities = normalize_amenities(accom.amenities)
    
    if requested_amenities:
        # Nếu khách có yêu cầu cứng
        matched = len(requested_amenities & accommodation_amenities)
        base_amenity_score = matched / float(len(requested_amenities))
        
        # Ngữ cảnh ẩn (Context): Bonus thêm nếu đi nhóm mà KS có bếp/hồ bơi
        if is_group_trip:
            bonus_amenities = {"kitchen", "pool"} - requested_amenities
            if bonus_amenities:
                bonus_matched = len(bonus_amenities & accommodation_amenities)
                # Điểm base chiếm 80%, bonus chiếm 20%
                scores["amenities"] = (base_amenity_score * 0.8) + (0.2 * (bonus_matched / len(bonus_amenities)))
            else:
                scores["amenities"] = base_amenity_score
        else:
            scores["amenities"] = base_amenity_score
    else:
        # Nếu khách KHÔNG yêu cầu tiện ích, tự động nội suy (Infer intent)
        latent_amenities = set()
        if is_group_trip:
            latent_amenities = {"kitchen", "pool"}
        elif has_guest_filter and req.guest_count == 2:
            latent_amenities = {"wifi", "air_conditioner"}
        elif has_guest_filter and req.guest_count == 1:
            latent_amenities = {"wifi", "air_conditioner"}
            
        if latent_amenities:
            matched = len(latent_amenities & accommodation_amenities)
            # Khởi điểm 0.6 vì khách không bắt buộc, nếu có thì cộng thêm lên max 1.0
            scores["amenities"] = 0.6 + 0.4 * (matched / len(latent_amenities))
        else:
            scores["amenities"] = 1.0

    # 3. Điểm vị trí (Location Score) [0.0 - 1.0]
    location_mode = preference_location_mode(req)
    if preference_has_coordinate_origin(req) and location_mode in NEARBY_LOCATION_MODES:
        distance_km = getattr(accom, "distance_km", None)
        if distance_km is None:
            distance_km = accommodation_distance_km(accom, req)
            if distance_km is not None:
                accom.distance_km = round(distance_km, 2)
        scores["location"] = calculate_distance_score(
            distance_km,
            getattr(req, "search_radius_km", None) or DEFAULT_NEARBY_RADIUS_KM,
        )
    elif getattr(req, "area", None):
        scores["location"] = calculate_area_score(accom.area, req.area)
    else:
        scores["location"] = 1.0

    # 4. Điểm chất lượng (Quality Score) theo Bayesian Average [0.0 - 1.0]
    # Khắc phục lỗi: Khách sạn 5 sao ít review bị đánh giá sai lệch
    GLOBAL_AVG_RATING = 3.5
    CONFIDENCE_THRESHOLD = 5.0
    review_count = getattr(accom, "review_count", 0) or 0
    rating = accom.rating or 0.0
    
    if review_count > 0:
        bayesian_rating = (CONFIDENCE_THRESHOLD * GLOBAL_AVG_RATING + review_count * rating) / (CONFIDENCE_THRESHOLD + review_count)
        scores["quality"] = bayesian_rating / 5.0
    else:
        scores["quality"] = GLOBAL_AVG_RATING / 5.0

    # 5. Điểm loại chỗ ở (Type Score) [0.0 - 1.0]
    requested_types = preference_accommodation_types(req)
    if requested_types:
        scores["type"] = 1.0 if accom.accommodation_type in requested_types else 0.0
    else:
        scores["type"] = 1.0

    # Tính tổng điểm (Weighted Sum Model)
    final_score = sum(scores[k] * WEIGHTS[k] for k in WEIGHTS)

    return min(round(final_score, 2), 5.0)


def get_candidate_accommodations(preference) -> list[Accommodation]:
    location_mode = preference_location_mode(preference)
    if location_mode in NEARBY_LOCATION_MODES and not preference_has_coordinate_origin(preference):
        _attach_relaxation_metadata(preference, [])
        return []

    attempts = [
        (set(), 1.0, 1.0, []),
        ({"amenities"}, 1.0, 1.0, ["amenities"]),
        ({"amenities", "type"}, 1.0, 1.0, ["amenities", "accommodation_type"]),
        ({"amenities", "type", "rating"}, 1.0, 1.0, ["amenities", "accommodation_type", "rating"]),
        ({"amenities", "type", "rating"}, RADIUS_RELAXATION_MULTIPLIER, 1.0, ["amenities", "accommodation_type", "rating", "radius"]),
        (
            {"amenities", "type", "rating", "budget"},
            RADIUS_RELAXATION_MULTIPLIER,
            BUDGET_RELAXATION_MULTIPLIER,
            ["amenities", "accommodation_type", "rating", "radius", "budget"],
        ),
    ]
    if location_mode in NEARBY_LOCATION_MODES:
        attempts = _nearby_attempts(preference)

    for relaxed, radius_multiplier, budget_multiplier, relaxed_filters in attempts:
        pool = _unique_accommodations(
            _candidate_queryset(
                preference,
                relaxed=relaxed,
                radius_multiplier=radius_multiplier,
                budget_multiplier=budget_multiplier,
            )
        )
        candidates = _apply_candidate_filters(
            pool,
            preference,
            relaxed=relaxed,
            radius_multiplier=radius_multiplier,
            budget_multiplier=budget_multiplier,
        )
        if candidates:
            applied_relaxations = _applied_relaxations(preference, relaxed_filters, radius_multiplier, budget_multiplier)
            used_radius_km = _used_radius_km(preference, radius_multiplier)
            _attach_relaxation_metadata(preference, applied_relaxations, used_radius_km=used_radius_km)
            return _sort_candidate_retrieval(candidates, preference)

    _attach_relaxation_metadata(preference, [], used_radius_km=getattr(preference, "search_radius_km", None))
    return []


def _candidate_queryset(preference, *, relaxed: set[str], radius_multiplier: float, budget_multiplier: float):
    queryset = Accommodation.objects.all()

    if has_filter_node(preference, "guest_count"):
        queryset = queryset.filter(capacity__gte=preference.guest_count)

    if has_filter_node(preference, "budget_max"):
        budget = getattr(preference, "budget", 0) or 0
        multiplier = budget_multiplier if "budget" in relaxed else 1.0
        if budget > 0:
            queryset = queryset.filter(price_per_night__lte=int(budget * multiplier))

    if has_filter_node(preference, "budget_min"):
        min_budget = _int_or_none(node_value(preference, "budget_min"))
        if min_budget:
            queryset = queryset.filter(price_per_night__gte=min_budget)

    requested_types = preference_accommodation_types(preference)
    if "type" not in relaxed and requested_types:
        queryset = queryset.filter(accommodation_type__in=requested_types)

    location_mode = preference_location_mode(preference)
    if location_mode in NEARBY_LOCATION_MODES and preference_has_coordinate_origin(preference):
        origin = preference_search_origin(preference)
        radius_km = (origin.get("radius_km") or DEFAULT_NEARBY_RADIUS_KM) * radius_multiplier
        bbox = origin_bounding_box(origin, radius_km)
        if bbox:
            min_lat, max_lat, min_lon, max_lon = bbox
            preference.last_bbox_prefilter = {
                "min_lat": min_lat,
                "max_lat": max_lat,
                "min_lon": min_lon,
                "max_lon": max_lon,
                "radius_km": radius_km,
            }
            queryset = queryset.filter(
                latitude__isnull=False,
                longitude__isnull=False,
                latitude__gte=min_lat,
                latitude__lte=max_lat,
                longitude__gte=min_lon,
                longitude__lte=max_lon,
            )

    return queryset


def _nearby_attempts(preference) -> list[tuple[set[str], float, float, list[str]]]:
    base_radius = getattr(preference, "search_radius_km", None) or DEFAULT_NEARBY_RADIUS_KM
    radius_steps = _radius_steps_from_base(base_radius)
    attempts: list[tuple[set[str], float, float, list[str]]] = []

    for radius in radius_steps:
        multiplier = radius / max(base_radius, 0.1)
        relaxed_filters = ["radius"] if radius > base_radius else []
        attempts.append((set(), multiplier, 1.0, relaxed_filters))

    expanded_multiplier = radius_steps[-1] / max(base_radius, 0.1)
    attempts.extend(
        [
            ({"amenities"}, expanded_multiplier, 1.0, ["radius", "amenities"]),
            ({"amenities", "type"}, expanded_multiplier, 1.0, ["radius", "amenities", "accommodation_type"]),
            ({"amenities", "type", "rating"}, expanded_multiplier, 1.0, ["radius", "amenities", "accommodation_type", "rating"]),
            (
                {"amenities", "type", "rating", "budget"},
                expanded_multiplier,
                BUDGET_RELAXATION_MULTIPLIER,
                ["radius", "amenities", "accommodation_type", "rating", "budget"],
            ),
        ]
    )
    return attempts


def _radius_steps_from_base(base_radius: float) -> list[float]:
    steps = [float(base_radius)]
    for radius in NEARBY_RADIUS_STEPS_KM:
        if radius > base_radius and radius not in steps:
            steps.append(radius)
    return steps


def _unique_accommodations(items) -> list[Accommodation]:
    unique_items: dict[int, Accommodation] = {}
    for item in items:
        unique_items.setdefault(item.id, item)
    return list(unique_items.values())


def _apply_candidate_filters(
    candidates: list[Accommodation],
    preference,
    *,
    relaxed: set[str],
    radius_multiplier: float,
    budget_multiplier: float,
) -> list[Accommodation]:
    output: list[Accommodation] = []
    location_mode = preference_location_mode(preference)
    origin = preference_search_origin(preference)
    radius_km = (origin.get("radius_km") or DEFAULT_NEARBY_RADIUS_KM) * radius_multiplier
    requested_amenities = normalize_amenities(getattr(preference, "required_amenities", None))
    requested_types = preference_accommodation_types(preference)
    high_rating_requested = "high_rating" in (node_value(preference, "priorities", []) or [])
    min_rating = node_value(preference, "rating")

    for item in candidates:
        if has_filter_node(preference, "guest_count") and item.capacity < preference.guest_count:
            continue
        if has_filter_node(preference, "budget_max"):
            budget = getattr(preference, "budget", 0) or 0
            multiplier = budget_multiplier if "budget" in relaxed else 1.0
            if budget > 0 and item.price_per_night > int(budget * multiplier):
                continue
        if has_filter_node(preference, "budget_min"):
            min_budget = _int_or_none(node_value(preference, "budget_min"))
            if min_budget and item.price_per_night < min_budget:
                continue
        if "type" not in relaxed and requested_types:
            if item.accommodation_type not in requested_types:
                continue
        if "amenities" not in relaxed and requested_amenities:
            item_amenities = normalize_amenities(item.amenities)
            if not requested_amenities.issubset(item_amenities):
                continue
        if "rating" not in relaxed:
            if high_rating_requested and (item.rating or 0) < 4.0:
                continue
            if min_rating is not None and (item.rating or 0) < float(min_rating):
                continue

        if location_mode in NEARBY_LOCATION_MODES and preference_has_coordinate_origin(preference):
            distance_km = accommodation_distance_km(item, preference)
            if distance_km is None:
                continue
            item.distance_km = round(distance_km, 2)
            if distance_km > radius_km:
                continue
        elif location_mode == "area" and getattr(preference, "area", None):
            if not area_matches(item.area, preference.area):
                continue

        output.append(item)
    return output


def _sort_candidate_retrieval(candidates: list[Accommodation], preference) -> list[Accommodation]:
    if preference_location_mode(preference) in NEARBY_LOCATION_MODES and preference_has_coordinate_origin(preference):
        return sorted(
            candidates,
            key=lambda item: (
                -calculate_matching_score(item, preference),
                getattr(item, "distance_km", float("inf")),
                -(item.rating or 0),
                item.price_per_night or float("inf"),
            ),
        )
    return candidates


def _applied_relaxations(
    preference,
    relaxed_filters: list[str],
    radius_multiplier: float,
    budget_multiplier: float,
) -> list[str]:
    applied: list[str] = []
    for filter_name in relaxed_filters:
        if filter_name == "amenities" and not getattr(preference, "required_amenities", None):
            continue
        if filter_name == "accommodation_type" and not preference_accommodation_types(preference):
            continue
        if filter_name == "rating" and (
            "high_rating" not in (node_value(preference, "priorities", []) or [])
            and node_value(preference, "rating") is None
        ):
            continue
        if filter_name == "radius" and not (
            radius_multiplier > 1.0
            and preference_location_mode(preference) in NEARBY_LOCATION_MODES
            and preference_has_coordinate_origin(preference)
        ):
            continue
        if filter_name == "budget" and not (budget_multiplier > 1.0 and has_filter_node(preference, "budget_max")):
            continue
        if filter_name not in applied:
            applied.append(filter_name)
    return applied


def _used_radius_km(preference, radius_multiplier: float) -> float | None:
    if not preference_has_coordinate_origin(preference):
        return None
    origin = preference_search_origin(preference)
    base_radius = origin.get("radius_km") or DEFAULT_NEARBY_RADIUS_KM
    return round(float(base_radius) * float(radius_multiplier), 2)


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _attach_relaxation_metadata(preference, relaxed_filters: list[str], *, used_radius_km: float | None = None) -> None:
    if used_radius_km is not None:
        preference.used_radius_km = used_radius_km
        if preference_has_coordinate_origin(preference):
            preference.search_radius_km = used_radius_km
    preference.relaxed = bool(relaxed_filters)
    preference.relaxed_filters = relaxed_filters
    if not relaxed_filters:
        preference.relaxation_message = ""
    elif "radius" in relaxed_filters:
        radius_label = f"{used_radius_km:g}" if used_radius_km else "lớn hơn"
        preference.relaxation_message = f"Mình đã mở rộng phạm vi tìm kiếm lên {radius_label} km để có thêm lựa chọn."
    elif "budget" in relaxed_filters:
        preference.relaxation_message = "Mình cho phép ngân sách vượt nhẹ để không bỏ sót lựa chọn gần với nhu cầu của bạn."
    else:
        preference.relaxation_message = "Mình nới một vài tiêu chí mềm để có thêm lựa chọn phù hợp."


def origin_bounding_box(origin: dict[str, Any], radius_km: float) -> tuple[float, float, float, float] | None:
    try:
        lat = float(origin.get("latitude"))
        lon = float(origin.get("longitude"))
        radius = float(radius_km)
    except (TypeError, ValueError):
        return None
    if radius <= 0:
        return None

    lat_delta = radius / 110.574
    cos_lat = max(cos(radians(lat)), 0.01)
    lon_delta = radius / (111.320 * cos_lat)
    return (lat - lat_delta, lat + lat_delta, lon - lon_delta, lon + lon_delta)


def _normalize_search_origin(origin: dict[str, Any], req) -> dict[str, Any]:
    origin_type = origin.get("type") or "none"
    if origin_type not in {"none", "area", "semantic_center", "anchor", "user_location"}:
        origin_type = "none"
    latitude = _float_or_none(origin.get("latitude"))
    longitude = _float_or_none(origin.get("longitude"))
    radius_km = _float_or_none(origin.get("radius_km"))
    if origin_type not in COORDINATE_ORIGIN_TYPES:
        latitude = None
        longitude = None
        radius_km = None
    elif radius_km is None:
        radius_km = _float_or_none(getattr(req, "search_radius_km", None)) or DEFAULT_NEARBY_RADIUS_KM
    return {
        "type": origin_type,
        "label": origin.get("label") or getattr(req, "location_label", None) or getattr(req, "area", None),
        "latitude": latitude,
        "longitude": longitude,
        "radius_km": radius_km,
    }


def _float_or_none(value: Any) -> float | None:
    try:
        if value is not None:
            return float(value)
    except (TypeError, ValueError):
        return None
    return None
