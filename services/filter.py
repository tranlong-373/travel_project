import math
from typing import List, Dict, Any


def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Tính khoảng cách giữa hai tọa độ trong km."""
    # Bán kính Trái Đất 
    R = 6371.0  

    rlat1, rlon1 = math.radians(lat1), math.radians(lon1)
    rlat2, rlon2 = math.radians(lat2), math.radians(lon2)

    dlat = rlat2 - rlat1
    dlon = rlon2 - rlon1

    a = math.sin(dlat / 2) ** 2 + math.cos(rlat1) * math.cos(rlat2) * math.sin(dlon / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c


def filter_accommodations(
    data: List[Dict[str, Any]],
    budget_max: float | None = None,
    city: str | None = None,
    location: Dict[str, float] | None = None,
    amenities: List[str] | None = None,
) -> List[Dict[str, Any]]:
    """Lọc chỗ ở theo ngân sách, vị trí và tiện nghi."""
    if not data:
        return []

    amenities = amenities or []
    result: List[Dict[str, Any]] = []

    for item in data:
        price = float(item.get("price", 0.0))

        if budget_max is not None and price > budget_max:
            continue

        if city:
            if str(item.get("city", "")).strip().lower() != city.strip().lower():
                continue

        if location:
            lat = item.get("lat")
            lng = item.get("lng")
            if lat is None or lng is None:
                continue
            dist_km = haversine_distance(location["lat"], location["lng"], float(lat), float(lng))
            if dist_km > location.get("radius_km", 0):
                continue

        if amenities:
            item_amenities = [str(a).strip().lower() for a in item.get("amenities", [])]
            if not all(req.strip().lower() in item_amenities for req in amenities):
                continue

        result.append(item)

    return result
