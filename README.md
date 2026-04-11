# Accommodation Recommendation Project

Project Django này quản lý dữ liệu chỗ ở và cung cấp flow gợi ý chỗ ở từ câu nhập tự nhiên của user.

Flow chính:

```text
user text -> chat_api parse -> chat_api submit -> UserPreference -> recommendations result
```

`chat_api` không tự recommend trực tiếp. Module này dịch câu tự nhiên thành dữ liệu có cấu trúc. Recommender đọc dữ liệu sạch qua `UserPreference`, không đọc raw text của user.

## App Chính
- `chat_api`: deterministic parser cho text tự nhiên, có `/api/chat/parse/` và `/api/chat/submit/`.
- `preferences`: lưu nhu cầu đã chuẩn hóa vào model `UserPreference`.
- `recommendations`: đọc `pref_id`, lấy `UserPreference`, tính score và render kết quả.
- `accommodations`: lưu dữ liệu chỗ ở trong model `Accommodation`.
- `accounts`: đăng ký, đăng nhập và profile user.

## Cấu hình databse
python manage.py makemigrations
python manage.py migrate
## Tạo tài khoản admin
python manage.py createsuperuser
(ở dòng nhập mật khẩu admin á khi nhập bằng terminal nó bị ẩn đi không có hiện nhưng mà mọi người cứ nhập rồi enter bình thường nhan)

## Flow Tổng Quát

1. Frontend gửi câu user vào `POST /api/chat/parse/`.
2. Nếu thiếu core slots, API trả `follow_up_question`.
3. Frontend hỏi tiếp và gửi câu trả lời kèm `context_slots` cũ.
4. Khi đủ `area`, `budget`, `guest_count` và `location_status = "ok"`, frontend gọi `POST /api/chat/submit/`.
5. `chat_api` tạo `UserPreference` và trả `pref_id`, `recommendation_url`.
6. Frontend mở hoặc gọi `GET /recommendations/<pref_id>/` để lấy trang kết quả recommendation.

Core slots bắt buộc:

- `area`
- `budget`
- `guest_count`

Optional slots parser có thể trả:

- `preferred_type`
- `required_amenities`
- `priorities`
- `special_requirements`
- `trip_days`

Lưu ý: `priorities`, `special_requirements`, `trip_days` hiện có trong parse response nhưng chưa được lưu vào `UserPreference` và chưa được dùng trực tiếp trong recommender.

## Cài Và Chạy Local

Từ repo root:

```powershell
cd accommodation_project
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install django mssql-django pyodbc
python manage.py migrate
python seed.py
python manage.py runserver
```

Repo hiện chưa có `requirements.txt`. Nếu team thêm file này sau, có thể thay bước cài package bằng:

```powershell
python -m pip install -r requirements.txt
```

## Database Và Local Settings

`accommodation_project/accommodation_project/settings.py` đang dùng SQL Server qua `mssql-django`:

- database name: `AccommodationDB`
- host mặc định: `localhost`
- driver: `ODBC Driver 18 for SQL Server`

File `accommodation_project/accommodation_project/settings_local.py` là optional local override và không nên commit. Nếu máy khác dùng SQL Server instance khác, tạo file này để override `DATABASES["default"]`.

Ví dụ:

```python
DATABASE_OVERRIDES = {
    "HOST": r"YOUR_MACHINE\SQLEXPRESS",
    "OPTIONS": {
        "driver": "ODBC Driver 18 for SQL Server",
    },
}
```

## Giới Hạn Hiện Tại

- `chat_api` chỉ auto-ready khi đủ `area`, `budget`, `guest_count` và `location_status = "ok"`.
- Location resolver hiện chỉ hỗ trợ scope: TP HCM, Hà Nội, Thanh Hóa, Đồng Nai, An Giang, Bình Định.
- `preferred_type = "resort"` chưa bật vì model downstream chỉ có `hotel`, `homestay`, `hostel`, `apartment`.
- `GET /recommendations/<pref_id>/` hiện render HTML template, không phải JSON API.
- Dữ liệu seed hiện chủ yếu là demo ở TP HCM, nên kết quả recommendation phụ thuộc dữ liệu thật trong DB.
