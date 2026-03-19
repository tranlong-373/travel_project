from services.filter import filter_data
from services.scoring import calculate_score
from services.ranking import rank_data


# Tạo danh sách lý do giải thích vì sao chỗ ở được đề xuất
# Dựa trên ngân sách, rating, loại chỗ ở, số người và khoảng cách
def generate_reason(item, request):
    reasons = []

    # Giá thành so với ngân sách
    if request.budget_max:
        if item["PricePerNight"] <= request.budget_max:
            reasons.append("giá phù hợp ngân sách")
        else:
            reasons.append("giá hơi cao so với ngân sách")

    # Điểm đánh giá
    if item["Rating"] >= 4.5:
        reasons.append("đánh giá rất cao")
    elif item["Rating"] >= 4:
        reasons.append("đánh giá tốt")
    else:
        reasons.append("đánh giá trung bình")

    # Kiểu chỗ ở
    if request.type:
        if item["AccommodationType"] == request.type:
            reasons.append("đúng loại lưu trú mong muốn")
        else:
            reasons.append("không đúng loại lưu trú mong muốn")

    # Tiện nghi(nếu có)
    """if hasattr(request, "amenities") and request.amenities:
        item_amenities = item.get("Amenities", [])
        matched = sum(1 for a in request.amenities if a in item_amenities)
        if matched == len(request.amenities):
            reasons.append("đủ tiện nghi mong muốn")
        else:
            reasons.append("thiếu một số tiện nghi mong muốn")"""

    # Số người
    if hasattr(request, "people") and request.people:
        if item["MaxPeople"] >= request.people:
            reasons.append("phù hợp số người hiện tại")
        else:
            reasons.append("có thể không đủ chỗ cho số người hiện tại")

    # Khoảng cách đến trung tâm 
    """if "distance" in item:
        if item["distance"] <= 3:
            reasons.append("gần trung tâm")
        else:
            reasons.append("hơi xa trung tâm")"""

    return ", ".join(reasons)


# Hàm chính thực hiện recommendation
# Gồm: filter → chấm điểm → xếp hạng → trả top kết quả
def recommend(data, request):
    # Lọc dữ liệu theo yêu cầu người dùng
    filtered = filter_data(data, request)

    # Nếu không có kết quả thì fallback toàn bộ dữ liệu
    if not filtered:
        filtered = data  

    # Chấm điểm và sinh lý do cho từng item
    for item in filtered:
        item["score"] = calculate_score(item, request)
        item["reason"] = generate_reason(item, request)

    # Gọi ranking service
    ranked = rank_data(filtered)

    # Trả về top 5 kết quả
    limit = getattr(request, "limit", 5)
    return ranked[:limit]