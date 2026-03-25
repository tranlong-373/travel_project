from typing import List, Dict, Any, Optional
from services.filter import filter_accommodations
from services.scoring import score_accommodations, generate_reason_for_score


def orchestrate_recommendations(
    data: List[Dict[str, Any]],
    budget_max: Optional[float] = None,
    city: Optional[str] = None,
    location: Optional[Dict[str, float]] = None,
    amenities: Optional[List[str]] = None,
    user_profile: Optional[Dict[str, Any]] = None,
    top_n: int = 5,
) -> Dict[str, Any]:
    """Orchestration:
    1. Lọc theo Filter (ngân sách, Vị trí, Tiện nghi).
    2. Gọi service AI để chấm điểm (scoring).
    3. Sort top kết quả.
    4. Ghép dữ liệu trả về.
    """
    user_profile = user_profile or {}

    filtered = filter_accommodations(
        data=data,
        budget_max=budget_max,
        city=city,
        location=location,
        amenities=amenities,
    )

    if not filtered:
        raise ValueError("Không tìm thấy chỗ ở nào phù hợp với tiêu chí lọc của bạn.")

    user_profile["budget_max"] = budget_max or user_profile.get("budget_max")
    scored = score_accommodations(filtered, user_profile)

    ranked = sorted(scored, key=lambda x: x.get("score", 0.0), reverse=True)
    top_results = ranked[:max(1, min(50, top_n))]

    recommendations = []
    for i, item in enumerate(top_results, 1):
        reason = generate_reason_for_score(item)
        recommendations.append(
            {
                "rank": i,
                "id": item.get("id"),
                "name": item.get("name"),
                "price": item.get("price"),
                "score": item.get("score"),
                "reason": reason,
                "amenities": item.get("amenities", []),
                "location": {
                    "city": item.get("city"),
                    "lat": item.get("lat"),
                    "lng": item.get("lng"),
                },
            }
        )

    return {
        "status": "success",
        "total_filtered": len(filtered),
        "returned": len(recommendations),
        "recommendations": recommendations,
    }
