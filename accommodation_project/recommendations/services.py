def get_adjacent_areas(area):
    """Tìm các khu vực lân cận để lấy lại một phần điểm vị trí"""
    area = area.lower()
    adjacents = {
        'quận 1': ['quận 3', 'quận 4', 'quận 5', 'quận 10', 'bình thạnh'],
        'quận 3': ['quận 1', 'quận 10', 'tân bình', 'phú nhuận'],
        'quận 2': ['quận 9', 'thủ đức', 'quận 1', 'bình thạnh'],
        'quận 7': ['quận 4', 'nhà bè', 'quận 8'],
    }
    for main_area, adjacent_list in adjacents.items():
        if main_area in area or area in main_area:
            return adjacent_list
    return []


def calculate_matching_score(accom, req):
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
        score += max(0, base_price_score - 0.2)
    else:
        # Nếu rẻ hơn hoặc vừa bằng với giá của khách, ăn trọn điểm gốc
        score += base_price_score
        
    # 2. Tiện ích (Max 1.5đ): Khớp càng đầy đủ tiện ích mà khách nhắm tới càng cao điểm
    if req.required_amenities:
        matched = len(set(req.required_amenities) & set(accom.amenities))
        score += 1.5 * (matched / float(len(req.required_amenities)))
    else:
        score += 1.5
        
    # 3. Vị trí (Max 1.0đ): Khớp khu vực 
    accom_area = accom.area.lower()
    req_area = req.area.lower()
    
    if req_area in accom_area or accom_area in req_area:
        score += 1.0
    else:
        adj_areas = get_adjacent_areas(req_area)
        for adj in adj_areas:
            if adj in accom_area:
                score += 0.5
                break
                
    # 4. Chất lượng (Max 1.0đ) - Dựa trên đánh giá Rating MẶC ĐỊNH của DB
    if accom.rating:
        score += 1.0 * (accom.rating / 5.0)
    
    return round(score, 2)
