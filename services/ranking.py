# Hàm xếp hạng dữ liệu dựa trên điểm số đã có sẵn
# Chỉ thực hiện sắp xếp, không tính lại score
def rank_data(data):
    # Sắp xếp theo score giảm dần
    return sorted(data, key=lambda x: x["score"], reverse=True)