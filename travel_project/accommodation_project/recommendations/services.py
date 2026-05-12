from __future__ import annotations

import unicodedata

from accommodations.models import Accommodation


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
    for adjacent_area in get_adjacent_areas(requested_area):
        if adjacent_area in accom_area:
            return 0.5

    return 0.0


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

    # Ràng buộc cứng: Sức chứa không đủ -> rớt ngay
    if accom.capacity < req.guest_count:
        return 0.0

    price = accom.price_per_night
    budget = req.budget

    # Ràng buộc cứng: Vượt budget quá mức cho phép (300,000đ) -> rớt ngay
    if budget and budget > 0 and price > budget + 300_000:
        return 0.0

    # Trọng số các tiêu chí (tổng = 5.0)
    # Tự động điều chỉnh trọng số dựa trên ngữ cảnh: Đi gia đình/nhóm thì tiện ích quan trọng hơn
    is_group_trip = req.guest_count >= 3
    WEIGHTS = {
        "price": 1.25,
        "amenities": 1.2 if is_group_trip else 1.0,
        "location": 1.25,
        "quality": 1.0,
        "type": 0.3 if is_group_trip else 0.5
    }
    
    # Cân bằng lại tổng trọng số về đúng 5.0
    total_weight = sum(WEIGHTS.values())
    for k in WEIGHTS:
        WEIGHTS[k] = (WEIGHTS[k] / total_weight) * 5.0
        
    scores = {}

    # 1. Điểm giá thành (Price Score) [0.0 - 1.0]
    if budget and budget > 0:
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
            # Vượt ngân sách (nhưng chưa quá 300k) -> Giảm dần từ 0.8 về 0.4
            excess = price - budget
            scores["price"] = max(0.4, 0.8 - 0.4 * (excess / 300_000))
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
        elif req.guest_count == 1:
            latent_amenities = {"wifi", "air_conditioner"}
            
        if latent_amenities:
            matched = len(latent_amenities & accommodation_amenities)
            # Khởi điểm 0.6 vì khách không bắt buộc, nếu có thì cộng thêm lên max 1.0
            scores["amenities"] = 0.6 + 0.4 * (matched / len(latent_amenities))
        else:
            scores["amenities"] = 1.0

    # 3. Điểm vị trí (Location Score) [0.0 - 1.0]
    scores["location"] = calculate_area_score(accom.area, req.area)

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
    if req.preferred_type:
        scores["type"] = 1.0 if accom.accommodation_type == req.preferred_type else 0.0
    else:
        scores["type"] = 1.0

    # Tính tổng điểm (Weighted Sum Model)
    final_score = sum(scores[k] * WEIGHTS[k] for k in WEIGHTS)

    return min(round(final_score, 2), 5.0)

def get_candidate_accommodations(preference) -> list[Accommodation]:
    base_qs = Accommodation.objects.filter(capacity__gte=preference.guest_count)

    if preference.budget and preference.budget > 0:
        base_qs = base_qs.filter(price_per_night__lte=preference.budget + 300_000)

    if preference.preferred_type:
        base_qs = base_qs.filter(accommodation_type=preference.preferred_type)

    unique_items: dict[str, Accommodation] = {}
    for item in base_qs:
        unique_items.setdefault(item.name, item)

    candidates = list(unique_items.values())
    return [item for item in candidates if area_matches(item.area, preference.area)]
