from typing import List, Dict, Any, Optional
from app.utils.geo import haversine_distance

def filter_accommodations(
    data: List[Dict[str, Any]],
    budget_max: Optional[float] = None,
    city: Optional[str] = None,
    location: Optional[Dict[str, Any]] = None,
    amenities: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """Lọc chỗ ở theo ngân sách, vị trí và tiện nghi."""
    if not data:
        return []

    amenities = amenities or []
    result: List[Dict[str, Any]] = []

    for item in data:
        raw_price = item.get("price")
        price = float(raw_price) if raw_price is not None else 0.0

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
                
            loc_lat = location.get("lat", 0.0)
            loc_lng = location.get("lng", 0.0)
            radius = location.get("radius_km", 0.0)
            
            dist_km = haversine_distance(loc_lat, loc_lng, float(lat), float(lng))
            if dist_km > radius:
                continue

        if amenities:
            item_amenities = [str(a).strip().lower() for a in item.get("amenities", [])]
            if not all(req.strip().lower() in item_amenities for req in amenities):
                continue

        result.append(item)

    return result
