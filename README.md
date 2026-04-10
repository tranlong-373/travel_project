# Accommodation Management System

## Giới thiệu
Dự án xây dựng hệ thống quản lý chỗ ở sử dụng Django.  
Cho phép quản lý thông tin khách sạn, khu vực, giá cả và các tiện ích.

## Yêu cầu hệ thống
- Python 3.x
- Django x.x.x ( mình đang dùng 5.2.13 mọi người tải chung cho đồng bộ đi )

---

## 1. Tạo môi trường ảo
```bash
python -m venv venv
venv\Scripts\activate

pip install -r requirements.txt Hiện tại cái này chưa á nào có api thì sẽ thêm vào

## Cấu hình databse
python manage.py makemigrations
python manage.py migrate
## Tạo tài khoản admin
python manage.py createsuperuser

##Nạp dữ liệu
python seed.py

##Chạy server
python manage.py runserver


// quá trình tích hợp API đễ dễ quản lí thì mọi người ĐỪNG tạo bằng new folder mà truy cập vào thư mục chứa file manage.py trong terminal
gõ

python manage.py startapp name_api

nó sẽ tự cấu trúc file cho đồng bộ ( phải có django trước )
Khi này sẽ sửa các file sau sửa phần

settings trong accomodation_project.setting tìm  phần INSTALLED_APP vè thêm [ .... 'name_api',]

rồi vào thư mục vừa tạo bằng startapp tìm phần views.py và gõ

from django.http import JsonResponse
from accommodations.models import Accommodation
def accommodation_list(request):
    data = list(Accommodation.objects.values())
    return JsonResponse(data, safe=False)

sau đó vào trong thư mục của api đó
tạo file urls.py ( đồng bộ giữa các phần )
gõ :

from django.urls import path
from . import views

urlpatterns = [
    path("accommodations/", views.accommodation_list, name="api_accommodation_list"),
]



Tiến hành nối router tổng :

from django.urls import path, include
from django.contrib import admin

urlpatterns = [
    path("admin/", admin.site.urls), // này là có sẵn rồi chỉ thêm đường dẫn từ router tổng đến app api 

    path("api/", include("api.urls")),
]


