# Hàm lọc dữ liệu theo yêu cầu người dùng
# Dựa trên các tiêu chí: city, ngân sách, loại chỗ ở
def filter_data(data, request):
    result = []

    # Duyệt qua từng chỗ ở trong dữ liệu
    for item in data:

        # Lọc theo thành phố
        if request.city and item["City"].lower() != request.city.lower():
            continue

        # Lọc theo ngân sách tối đa
        if request.budget_max and item["PricePerNight"] > request.budget_max:
            continue

        # Lọc theo loại chỗ ở
        if request.type and item["AccommodationType"] != request.type:
            continue

        # Lọc theo điểm đánh giá tối thiểu
        if request.min_rating and item["Rating"] < request.min_rating:
            continue
        
        # Lọc theo tiện nghi (nếu có yêu cầu)
        """if request.amenities:
            if not all(a in item.get("Amenities", []) for a in request.amenities):
                continue"""

        # Nếu thỏa tất cả điều kiện thì thêm vào kết quả
        result.append(item)

    return result