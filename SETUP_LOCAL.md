# Setup Local

Tài liệu này dành cho thành viên mới pull repo về chạy trên máy local.

## Yêu Cầu Môi Trường

- Python 3.x. Project được tạo bằng Django 5.2.13.
- SQL Server local hoặc remote.
- Microsoft ODBC Driver 18 for SQL Server.
- Package Python tối thiểu theo code hiện tại:
  - `django`
  - `mssql-django`
  - `pyodbc`

Repo hiện chưa có `requirements.txt`, nên cần cài package thủ công hoặc team bổ sung file này sau.

## Clone Và Chạy Project

Từ repo root:

```powershell
cd accommodation_project
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install django mssql-django pyodbc
python manage.py check
python manage.py migrate
python seed.py
python manage.py runserver
```

Mặc định server chạy tại:

```text
http://127.0.0.1:8000/
```

## Database Local

`accommodation_project/accommodation_project/settings.py` đang cấu hình database mặc định:

```python
DATABASES = {
    "default": {
        "ENGINE": "mssql",
        "NAME": "AccommodationDB",
        "HOST": "localhost",
        "PORT": "",
        "OPTIONS": {
            "driver": "ODBC Driver 18 for SQL Server",
            "trusted_connection": "yes",
            "extra_params": "Encrypt=no;TrustServerCertificate=yes;",
        },
    }
}
```

Bạn cần tạo database `AccommodationDB` trong SQL Server trước khi chạy migrate, hoặc tạo local override nếu máy bạn dùng tên DB/instance khác.

## Optional `settings_local.py`

`settings.py` có import optional:

```python
try:
    from . import settings_local as local_settings
    ...
except ImportError:
    pass
```

Nghĩa là:

- Không có `settings_local.py`: Django dùng cấu hình mặc định trong `settings.py`.
- Có `settings_local.py`: file này có thể override DB local và static dir.
- File này là cấu hình máy cá nhân, không nên commit.

Ví dụ `accommodation_project/accommodation_project/settings_local.py`:

```python
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

DATABASE_OVERRIDES = {
    "NAME": "AccommodationDB",
    "HOST": r"YOUR_MACHINE\SQLEXPRESS",
    "PORT": "",
    "OPTIONS": {
        "driver": "ODBC Driver 18 for SQL Server",
        "trusted_connection": "yes",
        "extra_params": "Encrypt=no;TrustServerCertificate=yes;",
    },
}

STATIC_DIR = BASE_DIR / "static"
STATIC_DIR.mkdir(exist_ok=True)
STATICFILES_DIRS = [STATIC_DIR]
```

Nếu SQL Server của bạn chạy ở default instance, có thể dùng:

```python
DATABASE_OVERRIDES = {
    "HOST": "localhost",
}
```

## Seed Data

Chạy:

```powershell
python seed.py
```

Lưu ý: `seed.py` đang xóa toàn bộ `Accommodation` rồi insert dữ liệu demo. Không chạy lệnh này trên DB chứa dữ liệu thật nếu chưa backup.

## Test API Chat

Parse-only:

```powershell
Invoke-RestMethod -Method Post `
  -Uri http://127.0.0.1:8000/api/chat/parse/ `
  -ContentType "application/json" `
  -Body '{"text":"Khách sạn ở Sài Gòn cho 2 người, budget 900k, có wifi"}'
```

Submit và tạo `UserPreference`:

```powershell
Invoke-RestMethod -Method Post `
  -Uri http://127.0.0.1:8000/api/chat/submit/ `
  -ContentType "application/json" `
  -Body '{"text":"Khách sạn ở Sài Gòn cho 2 người, budget 900k, có wifi"}'
```

Nếu response có `recommendation_url`, mở URL đó trên browser, ví dụ:

```text
http://127.0.0.1:8000/recommendations/1/
```

## Test Nhanh Bằng Django

```powershell
python -B manage.py check
$env:DJANGO_SETTINGS_MODULE='accommodation_project.settings'; python -B -m unittest chat_api.tests
python -B manage.py makemigrations --check --dry-run
```

## Troubleshooting

### Lỗi ODBC Driver

Nếu gặp lỗi kiểu không tìm thấy `ODBC Driver 18 for SQL Server`, hãy cài Microsoft ODBC Driver 18 for SQL Server rồi chạy lại.

### Lỗi Không Kết Nối Được SQL Server

Nếu lỗi có nội dung `Server is not found or not accessible`, kiểm tra:

- SQL Server service đang chạy chưa.
- `HOST` trong `settings.py` hoặc `settings_local.py` đúng instance chưa.
- Database `AccommodationDB` đã tồn tại chưa.
- SQL Server cho phép trusted connection chưa.

### Lỗi Migrate

Chạy lại:

```powershell
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py migrate
```

Nếu vẫn lỗi ở DB connection, sửa DB config trước, không sửa parser/recommender.

### Không Có Kết Quả Recommendation

Kiểm tra:

- DB có dữ liệu `Accommodation` chưa.
- `seed.py` đã chạy chưa nếu đang dùng demo.
- `chat_api` trả `location_status = "ok"` chưa.
- `UserPreference.area` có khớp dữ liệu `Accommodation.area` không.

Hiện seed demo chủ yếu ở TP HCM, nên các area khác có thể parse đúng nhưng không có kết quả nếu DB chưa có dữ liệu tương ứng.
