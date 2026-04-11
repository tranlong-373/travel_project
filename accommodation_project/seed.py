import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'accommodation_project.settings')
django.setup()

from accommodations.models import Accommodation

# Xóa dữ liệu cũ
Accommodation.objects.all().delete()

data = [
    {
        "name": "Khách sạn A",
        "accommodation_type": "hotel",
        "area": "Quận 1",
        "address": "123 Lê Lợi",
        "price_per_night": 800000,
        "capacity": 2,
        "rating": 4.5,
        "amenities": ["wifi", "air_conditioner"],
        "description": "Khách sạn trung tâm"
    },
    {
        "name": "Homestay B",
        "accommodation_type": "homestay",
        "area": "Quận 3",
        "address": "45 Nguyễn Thị Minh Khai",
        "price_per_night": 500000,
        "capacity": 3,
        "rating": 4.2,
        "amenities": ["wifi", "kitchen", "washing_machine"],
        "description": "Không gian ấm cúng"
    },
    {
        "name": "Căn hộ C",
        "accommodation_type": "apartment",
        "area": "Quận 7",
        "address": "Phú Mỹ Hưng",
        "price_per_night": 1000000,
        "capacity": 4,
        "rating": 4.8,
        "amenities": ["wifi", "pool"],
        "description": "Căn hộ cao cấp"
    },
    {
        "name": "Nhà trọ D",
        "accommodation_type": "hostel",
        "area": "Thủ Đức",
        "address": "Gần ĐH SPKT",
        "price_per_night": 200000,
        "capacity": 2,
        "rating": 3.8,
        "amenities": ["wifi"],
        "description": "Phù hợp sinh viên"
    },
    {
        "name": "Villa E",
        "accommodation_type": "apartment",
        "area": "Quận 2",
        "address": "Thảo Điền",
        "price_per_night": 2000000,
        "capacity": 6,
        "rating": 4.9,
        "amenities": ["wifi", "pool", "parking"],
        "description": "Villa sang trọng"
    }
]

# nhân dữ liệu lên nhiều lần cho đủ số lượng
for i in range(5):  
    for item in data:
        Accommodation.objects.create(**item)

print("✅ Đã thêm dữ liệu thành công!")
