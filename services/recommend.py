from typing import List, Dict, Any
from services.filter import filter_accommodations
from services.scoring import score_with_ai, generate_reasoning_with_ai

def recommend_orchestrator(data: List[Dict[str, Any]], request_payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    \brief Mô-đun Điều phối cho đề xuất chỗ ở.

    \details Hàm này điều phối quá trình đề xuất bằng cách lọc,
    chấm điểm, xếp hạng và định dạng kết quả.

    1. Lọc theo điều kiện (ngân sách, vị trí, tiện nghi).
    2. Gọi dịch vụ AI để chấm điểm.
    3. Sắp xếp kết quả top.
    4. Định dạng dữ liệu đầu ra.

    \param data Danh sách từ điển chỗ ở.
    \param request_payload Từ điển chứa bộ lọc, hồ sơ người dùng và giới hạn.
    \return Từ điển với trạng thái, siêu dữ liệu và đề xuất.
    """
    filters = request_payload.get("filters", {})
    user_profile = request_payload.get("user_profile", {})
    top_n = request_payload.get("limit", 5)

    # Bước 1: Lọc qua điều kiện từ request (ngân sách, vị trí, tiện nghi)
    filtered_data = filter_accommodations(data, filters)

    # Dữ liệu dự phòng nếu bộ lọc quá chặt và không trả về kết quả
    if not filtered_data:
        filtered_data = data

    # Bước 2: Gọi dịch vụ AI để chấm điểm 
    scored_results = []
    for item in filtered_data:
        score = score_with_ai(user_profile, item)

        # Bổ sung Lý do nếu điểm tốt hoặc tùy theo kịch bản
        reasoning = generate_reasoning_with_ai(user_profile, item)

        # Tạo đối tượng tạm thời để xếp hạng
        new_item = item.copy()  # Sao chép đối tượng để không sửa db
        new_item["ai_score"] = score
        new_item["ai_reasoning"] = reasoning
        scored_results.append(new_item)

    # Bước 3: Sắp xếp Kết quả Top theo điểm AI (giảm dần)
    ranked_results = sorted(scored_results, key=lambda x: x["ai_score"], reverse=True)
    top_results = ranked_results[:top_n]

    # Bước 4: Logic ghép dữ liệu trả về 
    response = {
        "status": "success",
        "metadata": {
            "total_matches": len(scored_results),
            "returned_count": len(top_results),
        },
        "recommendations": []
    }

    for rank_idx, result in enumerate(top_results, start=1):
        formatted_item = {
            "rank": rank_idx,
            "id": result.get("id"),
            "name": result.get("name"),
            "price": result.get("price"),
            "score": result.get("ai_score"),
            "reasoning": result.get("ai_reasoning"),
            # Ghép thêm thông tin gốc 
            "details": {
                "location": {
                    "lat": result.get("lat"),
                    "lng": result.get("lng")
                },
                "amenities": result.get("amenities", []),
                "description": result.get("description", "")
            }
        }
        response["recommendations"].append(formatted_item)

    return response