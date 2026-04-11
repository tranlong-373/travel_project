from __future__ import annotations

import unicodedata

from accommodations.models import Accommodation


AMENITY_ALIASES = {
    # Từ khóa Wifi
    "wifi": "wifi",
    "wi-fi": "wifi",
    "internet": "wifi",
    "mang": "wifi",
    "mạng": "wifi",
    "wi fi": "wifi",
    
    # Từ khóa Máy lạnh / Điều hòa
    "dieu hoa": "air_conditioner",
    "điều hòa": "air_conditioner",
    "may lanh": "air_conditioner",
    "máy lạnh": "air_conditioner",
    "air conditioner": "air_conditioner",
    "ac": "air_conditioner",
    "may dieu hoa": "air_conditioner",
    "máy điều hòa": "air_conditioner",
    
    # Từ khóa Bếp
    "bep": "kitchen",
    "bếp": "kitchen",
    "nha bep": "kitchen",
    "nhà bếp": "kitchen",
    "kitchen": "kitchen",
    "nau an": "kitchen",
    "nấu ăn": "kitchen",
    
    # Từ khóa Bãi đỗ xe
    "bai do xe": "parking",
    "bãi đỗ xe": "parking",
    "cho dau xe": "parking",
    "chỗ đậu xe": "parking",
    "parking": "parking",
    "giu xe": "parking",
    "giữ xe": "parking",
    "do xe": "parking",
    "đỗ xe": "parking",
    
    # Từ khóa Hồ bơi
    "ho boi": "pool",
    "hồ bơi": "pool",
    "be boi": "pool",
    "bể bơi": "pool",
    "pool": "pool",
    "be tam": "pool",
    "bể tắm": "pool",
    
    # Từ khóa Máy giặt
    "may giat": "washing_machine",
    "máy giặt": "washing_machine",
    "washing machine": "washing_machine",
    "giat do": "washing_machine",
    "giặt đồ": "washing_machine",
    "giat ui": "washing_machine",
    "giặt ủi": "washing_machine",
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
    for adjacent_area in get_adjacent_areas(requested_area):
        if adjacent_area in accom_area:
            return 0.5

    return 0.0


def calculate_matching_score(accom: Accommodation, req) -> float:
    """Thang điểm 5.0đ đánh giá độ sát sao với toàn bộ yêu cầu của khách hàng"""
    
    # Ràng buộc cứng: Sức chứa không đủ sức chứa khách -> Cho rớt ngay
    if accom.capacity < req.guest_count:
        return 0.0

    score = 0.0

    # 1. Cơ chế giá thành (Max 1.5đ) được phân mốc tuyệt đối: Rẻ (<1tr), Trung bình (1tr-2tr), Mắc (>2tr)
    price = accom.price_per_night
    budget = req.budget

    if price < 1000000:
        base_price_score = 1.5  # Rẻ => Cộng cao nhất
    elif price <= 2000000:
        base_price_score = 0.75 # Trung bình => Điểm trung bình
    else:
        base_price_score = 0.25 # Mắc => Cộng thấp nhất

    # Tính toán chênh lệch so với giá của khách yêu cầu
    if budget > 0 and price > budget:
        # Nếu khách sạn mắc hơn giá khách yêu cầu, bị trừ 0.2đ từ điểm gốc
        score += max(0.0, base_price_score - 0.2)
    elif budget > 0:
        # Nếu rẻ hơn hoặc vừa bằng với giá của khách, ăn trọn điểm gốc
        score += base_price_score

    # 2. Tiện ích (Max 1.5đ): Khớp càng đầy đủ tiện ích mà khách nhắm tới càng cao điểm
    requested_amenities = normalize_amenities(req.required_amenities)
    accommodation_amenities = normalize_amenities(accom.amenities)
    if requested_amenities:
        matched = len(requested_amenities & accommodation_amenities)
        score += 1.5 * (matched / float(len(requested_amenities)))
    else:
        score += 1.5

    # 3. Vị trí (Max 1.0đ): Khớp khu vực với thuật toán linh hoạt
    score += calculate_area_score(accom.area, req.area)

    # 4. Chất lượng (Max 1.0đ) - Dựa trên đánh giá Rating MẶC ĐỊNH của DB
    if accom.rating:
        score += 1.0 * (accom.rating / 5.0)

    return round(score, 2)


def get_candidate_accommodations(preference) -> list[Accommodation]:
    # Lọc nhẹ để tải dữ liệu cơ bản
    base_qs = Accommodation.objects.filter(capacity__gte=preference.guest_count)

    # Gộp tên để tránh trùng lặp dữ liệu từ giả lập seed.py
    unique_items: dict[str, Accommodation] = {}
    for item in base_qs:
        unique_items.setdefault(item.name, item)

    candidates = list(unique_items.values())
    return [item for item in candidates if area_matches(item.area, preference.area)]
