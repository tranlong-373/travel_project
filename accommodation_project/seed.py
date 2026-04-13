import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'accommodation_project.settings')
django.setup()

from accommodations.models import Accommodation

# Xóa dữ liệu cũ
Accommodation.objects.all().delete()

data = [
    {
        "accommodation_code": "HCM001",
        "name": "Liberty Central Saigon Riverside Hotel",
        "accommodation_type": "hotel",
        "area": "Quận 1",
        "address": "17 Tôn Đức Thắng",
        "price_per_night": 1500000,
        "capacity": 2,
        "rating": 4.6,
        "review_count": 120,
        "latitude": 10.7757,
        "longitude": 106.7058,
        "amenities": ["wifi", "hồ bơi", "gym"],
        "description": "Khách sạn view sông Sài Gòn"
    },
    {
        "accommodation_code": "HCM002",
        "name": "Silverland Yen Hotel",
        "accommodation_type": "hotel",
        "area": "Quận 1",
        "address": "73-75 Thủ Khoa Huân",
        "price_per_night": 1400000,
        "capacity": 2,
        "rating": 4.5,
        "review_count": 100,
        "latitude": 10.7725,
        "longitude": 106.6971,
        "amenities": ["wifi", "buffet sáng"],
        "description": "Khách sạn gần chợ Bến Thành"
    },
    {
        "accommodation_code": "HCM003",
        "name": "Cozrum Homes - Ambera",
        "accommodation_type": "homestay",
        "area": "Quận 3",
        "address": "Nguyễn Đình Chiểu",
        "price_per_night": 550000,
        "capacity": 3,
        "rating": 4.3,
        "review_count": 60,
        "latitude": 10.7801,
        "longitude": 106.6845,
        "amenities": ["wifi", "bếp"],
        "description": "Homestay ấm cúng"
    },
    {
        "accommodation_code": "HCM004",
        "name": "Orchids Saigon Hotel",
        "accommodation_type": "hotel",
        "area": "Quận 3",
        "address": "192 Pasteur",
        "price_per_night": 1300000,
        "capacity": 2,
        "rating": 4.4,
        "review_count": 90,
        "latitude": 10.7794,
        "longitude": 106.6913,
        "amenities": ["wifi", "gym"],
        "description": "Khách sạn sang trọng"
    },
    {
        "accommodation_code": "HCM005",
        "name": "Sunrise City Apartment",
        "accommodation_type": "apartment",
        "area": "Quận 7",
        "address": "Nguyễn Hữu Thọ",
        "price_per_night": 950000,
        "capacity": 4,
        "rating": 4.7,
        "review_count": 150,
        "latitude": 10.7411,
        "longitude": 106.7035,
        "amenities": ["wifi", "hồ bơi", "gym"],
        "description": "Căn hộ cao cấp"
    },
    {
        "accommodation_code": "HCM006",
        "name": "Saigon South Residence",
        "accommodation_type": "apartment",
        "area": "Quận 7",
        "address": "Nguyễn Hữu Thọ",
        "price_per_night": 800000,
        "capacity": 4,
        "rating": 4.6,
        "review_count": 110,
        "latitude": 10.7325,
        "longitude": 106.7182,
        "amenities": ["wifi", "bãi đỗ xe"],
        "description": "Khu căn hộ hiện đại"
    },
    {
        "accommodation_code": "HCM007",
        "name": "KTX Mini SPKT",
        "accommodation_type": "room",
        "area": "Thủ Đức",
        "address": "Gần ĐH SPKT",
        "price_per_night": 200000,
        "capacity": 2,
        "rating": 3.9,
        "review_count": 50,
        "latitude": 10.8506,
        "longitude": 106.7719,
        "amenities": ["wifi"],
        "description": "Phù hợp sinh viên"
    },
    {
        "accommodation_code": "HCM008",
        "name": "Vinhomes Grand Park Studio",
        "accommodation_type": "apartment",
        "area": "Thủ Đức",
        "address": "Nguyễn Xiển",
        "price_per_night": 600000,
        "capacity": 2,
        "rating": 4.5,
        "review_count": 80,
        "latitude": 10.8414,
        "longitude": 106.8286,
        "amenities": ["wifi", "hồ bơi"],
        "description": "Căn hộ hiện đại"
    },
    {
        "accommodation_code": "HCM009",
        "name": "Villa Thao Dien Riverside",
        "accommodation_type": "villa",
        "area": "Quận 2",
        "address": "Thảo Điền",
        "price_per_night": 2500000,
        "capacity": 6,
        "rating": 4.9,
        "review_count": 70,
        "latitude": 10.8038,
        "longitude": 106.7365,
        "amenities": ["wifi", "hồ bơi"],
        "description": "Villa sang trọng"
    },
    {
        "accommodation_code": "HCM010",
        "name": "Masteri Thao Dien Apartment",
        "accommodation_type": "apartment",
        "area": "Quận 2",
        "address": "Xa lộ Hà Nội",
        "price_per_night": 1100000,
        "capacity": 4,
        "rating": 4.7,
        "review_count": 130,
        "latitude": 10.8031,
        "longitude": 106.7312,
        "amenities": ["wifi", "gym"],
        "description": "Căn hộ cao cấp"
    }
]
for i in range(8):  
    for item in data:
        Accommodation.objects.get_or_create(name=item['name'], defaults=item)
print("✅ Đã thêm dữ liệu thành công!")