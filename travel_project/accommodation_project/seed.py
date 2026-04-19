import os
import django
import random

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'accommodation_project.settings')
django.setup()

from accommodations.models import Accommodation, Room

# Xóa dữ liệu cũ
Room.objects.all().delete()
Accommodation.objects.all().delete()

areas = [
    "Quận 1", "Quận 3", "Quận 5", "Quận 7", "Quận 10",
    "Thủ Đức", "Quận 2", "Bình Thạnh", "Phú Nhuận", "Tân Bình"
]

types = ["hotel", "homestay", "apartment", "hostel"]

names = [
    "Sunrise Hotel", "Moonlight Homestay", "Green Apartment",
    "City View Hotel", "Luxury Stay", "Happy Home",
    "Central Residence", "Saigon Comfort", "Urban Living",
    "RiverSide Inn", "Golden Place", "Blue Sky Hotel"
]

street_names = [
    "Nguyễn Huệ", "Lê Lợi", "Trần Hưng Đạo", "Điện Biên Phủ",
    "Phan Xích Long", "Nguyễn Thị Minh Khai", "Cách Mạng Tháng 8",
    "Võ Văn Tần", "Hai Bà Trưng", "Pasteur"
]

amenities_list = [
    "wifi", "gym", "hồ bơi", "bếp", "bãi đỗ xe",
    "máy lạnh", "tv", "ban công", "máy nước nóng", "thang máy"
]

room_name_map = {
    "single": ["Phòng Standard 1 người", "Phòng Single Basic", "Phòng Solo"],
    "double": ["Phòng Deluxe 2 người", "Phòng Double View City", "Phòng Couple"],
    "twin": ["Phòng Twin 2 giường", "Phòng Twin Standard"],
    "family": ["Phòng Gia đình", "Family Deluxe Room"],
    "deluxe": ["Phòng Deluxe", "Deluxe Premium"],
    "suite": ["Phòng Suite", "Executive Suite"],
    "dorm": ["Giường Dorm", "Phòng Dorm Tiết kiệm"],
    "other": ["Phòng đặc biệt", "Phòng linh hoạt"]
}

room_types = ["single", "double", "twin", "family", "deluxe", "suite", "dorm"]


def random_hotline():
    return "09" + str(random.randint(10000000, 99999999))


def random_address():
    so_nha = random.randint(1, 300)
    duong = random.choice(street_names)
    return f"{so_nha} {duong}"


for i in range(50):
    acc_type = random.choice(types)
    capacity = random.randint(1, 8)

    # Tạo accommodation trước với giá tạm = 0
    accommodation = Accommodation.objects.create(
        accommodation_code=f"HCM{i+1:03}",
        name=f"{random.choice(names)} {i+1}",
        accommodation_type=acc_type,
        area=random.choice(areas),
        address=random_address(),
        price_per_night=0,   # sẽ cập nhật lại bằng giá trung bình của Room
        capacity=capacity,
        rating=0,
        review_count=0,
        latitude=10.70 + random.random() * 0.15,
        longitude=106.60 + random.random() * 0.18,
        amenities=random.sample(amenities_list, k=random.randint(2, 5)),
        description=f"{acc_type.title()} tiện nghi, phù hợp nghỉ ngắn ngày và du lịch.",
        hotline=random_hotline(),
        image_url=f"https://picsum.photos/seed/accommodation{i+1}/800/500"
    )

    # Mỗi accommodation có 2 -> 5 loại phòng
    so_loai_phong = random.randint(2, 5)
    selected_room_types = random.sample(room_types, k=so_loai_phong)

    room_prices = []

    for j, room_type in enumerate(selected_room_types, start=1):
        room_price = random.randint(180000, 2500000)
        room_capacity = random.randint(1, 6)
        total_rooms = random.randint(3, 15)
        available_rooms = random.randint(0, total_rooms)

        Room.objects.create(
            accommodation=accommodation,
            room_code=f"{accommodation.accommodation_code}-R{j:02}",
            room_type=room_type,
            name=random.choice(room_name_map.get(room_type, ["Phòng mặc định"])),
            price_per_night=room_price,
            capacity=room_capacity,
            total_rooms=total_rooms,
            available_rooms=available_rooms,
            amenities=random.sample(amenities_list, k=random.randint(2, 5)),
            description=f"{room_type.title()} room với đầy đủ tiện nghi cơ bản.",
            is_active=True
        )

        room_prices.append(room_price)

    # Cập nhật lại giá trung bình của accommodation theo Room
    if room_prices:
        accommodation.price_per_night = sum(room_prices) // len(room_prices)
        accommodation.save(update_fields=["price_per_night"])

print("✅ Đã seed Accommodation + Room thành công!")