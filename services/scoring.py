# Trọng số cho từng tiêu chí
# Giá quan trọng nhất, sau đó là rating, rồi đến loại chỗ ở
W_PRICE = 4
W_RATING = 3
W_TYPE = 2
W_BONUS = 1


# Hàm chấm điểm cho từng chỗ ở
# Dựa trên: giá, rating, loại chỗ ở, số người và tiện nghi (nếu có)
def calculate_score(item, request):
    score = 0

    # So sánh giá với ngân sách 
    if request.budget_max:
        price_ratio = item["PricePerNight"] / request.budget_max
        price_score = max(0, 1 - price_ratio * 0.7)
        score += price_score * W_PRICE
    else:
        # Nếu không có ngân sách → cho điểm trung bình
        score += 1

    # Chuẩn hóa rating về [0,1]
    rating_score = item["Rating"] / 5
    score += rating_score * W_RATING

    # Nếu đúng loại chỗ ở mong muốn → cộng điểm
    if request.type and item["AccommodationType"] == request.type:
        score += W_TYPE

    # Kiểm tra sức chứa
    if request.people:
        if item["MaxPeople"] >= request.people:
            score += 1
        else:
            score -= 1  

    # So khớp tiện nghi (nếu có)
    """if request.amenities:
        item_amenities = item.get("Amenities", [])
        matched = sum(1 for a in request.amenities if a in item_amenities)
        score += matched * 0.5"""

    # Thưởng nếu rating rất cao
    if item["Rating"] >= 4.5:
        score += W_BONUS

    return round(score, 2)