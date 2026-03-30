from typing import List, Dict, Any
from app.schemas.recommendation import (
    RecommendationRequest, RecommendationResponse, RecommendationItem,
    RecommendationMetadata, AccommodationLocation, RecommendationDetails
)
from app.engines.filter import filter_accommodations
from app.engines.scoring import score_accommodations, generate_reason_for_score

def orchestrate_recommendations(
    data: List[Dict[str, Any]],
    request_data: RecommendationRequest,
) -> RecommendationResponse:
    """
    Điều phối tổng thể quá trình Recommendation:
    1. Lọc chỗ ở bằng Filter Engine.
    2. Chấm điểm qua Scoring Engine (hoặc AI).
    3. Xếp hạng và trích xuất top kết quả.
    4. Trả về format chuẩn theo Response Schema.
    """
    filters = request_data.filters
    user_profile = request_data.user_profile or {}
    top_n = request_data.limit

    budget_max = None
    city = None
    location_filter = None
    amenities = None

    if filters:
        budget_max = filters.budget_max
        city = filters.city
        amenities = filters.amenities
        if filters.location:
            location_filter = filters.location.model_dump()

    # Step 1: Lọc dữ liệu thô
    filtered = filter_accommodations(
        data=data,
        budget_max=budget_max,
        city=city,
        location=location_filter,
        amenities=amenities,
    )

    # Dự phòng nếu bộ lọc quá chặt
    if not filtered:
        filtered = data
        if not filtered:
            return RecommendationResponse(
                status="success",
                metadata=RecommendationMetadata(total_matches=0, returned_count=0),
                recommendations=[]
            )

    # Truyền max budget vào để user_profile chấm điểm chuẩn xác nếu có
    if budget_max is not None:
        user_profile["budget_max"] = budget_max

    # Step 2: Chấm điểm bằng Scoring Engine
    scored_results = score_accommodations(filtered, user_profile)

    for item in scored_results:
        # Ở đây ta giả sử score Engine đã tính ra ai_score. Ta dùng chung cho reason
        reason = generate_reason_for_score(item)
        item["rule_reason"] = reason
        # Nơi này có thể gọi thêm AI model (như LLM) thực tế để sinh reasoning
        item["ai_reasoning"] = f"Dựa trên đánh giá và ngân sách: {reason}"

    # Step 3: Sắp xếp kết quả Top theo điểm số
    ranked = sorted(scored_results, key=lambda x: x.get("score", 0.0), reverse=True)
    top_results = ranked[:max(1, min(50, top_n))]

    # Step 4: Map kết quả ra Schema RecommendationResponse
    recommendations: List[RecommendationItem] = []
    for rank_idx, result in enumerate(top_results, start=1):
        loc = AccommodationLocation(
            city=result.get("city"),
            lat=result.get("lat"),
            lng=result.get("lng")
        )
        
        details = RecommendationDetails(
            location=loc,
            amenities=result.get("amenities", []),
            description=result.get("description", "")
        )
        
        # Parse price safely
        raw_price = result.get("price")
        price = float(raw_price) if raw_price is not None else None
        
        rec_item = RecommendationItem(
            rank=rank_idx,
            id=str(result.get("id", "unknown")),
            name=str(result.get("name", "Unknown Name")),
            price=price,
            score=result.get("score", 0.0),
            reason=result.get("rule_reason"),
            reasoning=result.get("ai_reasoning"),
            amenities=result.get("amenities", []),
            location=loc,
            details=details,
        )
        recommendations.append(rec_item)

    return RecommendationResponse(
        status="success",
        metadata=RecommendationMetadata(
            total_matches=len(scored_results),
            returned_count=len(recommendations)
        ),
        recommendations=recommendations
    )
