import os
import django
import random

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'accommodation_project.settings')
django.setup()

from accommodations.models import Accommodation

Accommodation.objects.all().delete()

areas = ["Quận 1", "Quận 3", "Quận 7", "Thủ Đức", "Quận 2"]
types = ["hotel", "homestay", "apartment", "hostel"]

names = [
    "Sunrise Hotel", "Moonlight Homestay", "Green Apartment",
    "City View Hotel", "Luxury Stay", "Happy Home",
    "Central Residence", "Saigon Comfort", "Urban Living"
]

amenities_list = ["wifi", "gym", "hồ bơi", "bếp", "bãi đỗ xe"]

for i in range(50):  # 👈 tạo 50 dòng
    Accommodation.objects.create(
        accommodation_code=f"HCM{i+1:03}",
        name=random.choice(names) + f" {i}",
        accommodation_type=random.choice(types),
        area=random.choice(areas),
        address="Địa chỉ ngẫu nhiên",
        price_per_night=random.randint(200000, 2500000),
        capacity=random.randint(1, 6),
        rating = 0,
        review_count = 0,
        latitude=10.7 + random.random() * 0.2,
        longitude=106.6 + random.random() * 0.2,
        amenities=random.sample(amenities_list, k=random.randint(1, 3)),
        description="Mô tả ngẫu nhiên",
        hotline="09" + str(random.randint(10000000, 99999999))
    )

print("✅ Đã thêm dữ liệu random!")