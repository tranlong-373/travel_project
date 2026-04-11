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
        "amenities": ["wifi", "điều hòa", "tivi"],
        "description": "Khách sạn trung tâm",
        "image_url": "https://du-lich.chudu24.com/f/m/2303/29/khach-san-a-la-carte-ha-long-bay-quang-ninh.jpg"

    },
    {
        "name": "Homestay B",
        "accommodation_type": "homestay",
        "area": "Quận 3",
        "address": "45 Nguyễn Thị Minh Khai",
        "price_per_night": 500000,
        "capacity": 3,
        "rating": 4.2,
        "amenities": ["wifi", "bếp", "máy giặt"],
        "description": "Không gian ấm cúng",
        "image_url": "https://du-lich.chudu24.com/f/m/2303/29/khach-san-a-la-carte-ha-long-bay-quang-ninh.jpg"

    },
    {
        "name": "Căn hộ C",
        "accommodation_type": "apartment",
        "area": "Quận 7",
        "address": "Phú Mỹ Hưng",
        "price_per_night": 1000000,
        "capacity": 4,
        "rating": 4.8,
        "amenities": ["wifi", "hồ bơi", "gym"],
        "description": "Căn hộ cao cấp",
        "image_url": "https://du-lich.chudu24.com/f/m/2303/29/khach-san-a-la-carte-ha-long-bay-quang-ninh.jpg"
    },
    {
        "name": "Nhà trọ D",
        "accommodation_type": "room",
        "area": "Thủ Đức",
        "address": "Gần ĐH SPKT",
        "price_per_night": 200000,
        "capacity": 2,
        "rating": 3.8,
        "amenities": ["wifi"],
        "description": "Phù hợp sinh viên",
        "image_url": "https://du-lich.chudu24.com/f/m/2303/29/khach-san-a-la-carte-ha-long-bay-quang-ninh.jpg"
    },
    {
        "name": "Villa E",
        "accommodation_type": "villa",
        "area": "Quận 2",
        "address": "Thảo Điền",
        "price_per_night": 2000000,
        "capacity": 6,
        "rating": 4.9,
        "amenities": ["wifi", "hồ bơi", "bãi đỗ xe"],
        "description": "Villa sang trọng",
        "image_url": "https://du-lich.chudu24.com/f/m/2303/29/khach-san-a-la-carte-ha-long-bay-quang-ninh.jpg"
    }
]

# nhân dữ liệu lên nhiều lần cho đủ số lượng
for i in range(5):  
    for item in data:
        Accommodation.objects.get_or_create(name=item['name'], defaults=item)
print("✅ Đã thêm dữ liệu thành công!")