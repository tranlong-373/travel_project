# Setup Local

Tài liệu này là bản chạy nhanh. README chính có mô tả đầy đủ hơn tại `README.md`.

## Yêu Cầu

- Python 3.10+; local hiện tại đã kiểm tra với Python 3.12.3.
- SQL Server local hoặc remote.
- Microsoft ODBC Driver 18 for SQL Server.
- Package Python trong `travel_project/accommodation_project/requirements.txt`.

## Chạy Từ Repo Root

```bash
cd travel_project/accommodation_project
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
cp .env.example .env
python -B manage.py check
python -B manage.py migrate
python -B seed.py
python -B manage.py runserver
```

Windows PowerShell:

```powershell
cd travel_project\accommodation_project
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
copy .env.example .env
python -B manage.py check
python -B manage.py migrate
python -B seed.py
python -B manage.py runserver
```

Server mặc định:

```text
http://127.0.0.1:8000/
```

## Database Local

`settings.py` dùng SQL Server:

```text
database: AccommodationDB
host: localhost
driver: ODBC Driver 18 for SQL Server
```

Nếu máy bạn dùng SQL Server instance khác, tạo:

```text
travel_project/accommodation_project/accommodation_project/settings_local.py
```

Ví dụ:

```python
DATABASE_OVERRIDES = {
    "HOST": r"YOUR_MACHINE\SQLEXPRESS",
    "OPTIONS": {
        "driver": "ODBC Driver 18 for SQL Server",
        "trusted_connection": "yes",
        "extra_params": "Encrypt=no;TrustServerCertificate=yes;",
    },
}
```

## Test Nhanh

```bash
cd travel_project/accommodation_project
python -B manage.py check
python -B manage.py makemigrations --check --dry-run
python -B manage.py test chat_api
python -m pip check
```

Nếu `makemigrations` cảnh báo lỗi kết nối SQL Server, sửa DB config trước.

## API Chat Nhanh

```bash
curl -X POST http://127.0.0.1:8000/api/chat/parse/ \
  -H "Content-Type: application/json" \
  -d '{"text":"Khách sạn ở Sài Gòn cho 2 người, 2 ngày, budget 900k, có wifi"}'
```

Submit sau khi xác nhận:

```bash
curl -X POST http://127.0.0.1:8000/api/chat/submit/ \
  -H "Content-Type: application/json" \
  -d '{"confirmed":true,"slots":{"area":"tp hcm","budget":900000,"guest_count":2,"trip_days":2,"preferred_type":"hotel","required_amenities":["wifi"]}}'
```

Nếu response có `recommendation_url`, mở URL đó trên browser.

## Lưu Ý

- `seed.py` xóa dữ liệu `Accommodation` hiện có rồi insert dữ liệu demo.
- Không commit `.env`, service account JSON hoặc private key.
- Voice API cần thêm runtime audio phù hợp với máy local, thường là `ffmpeg` ngoài pip packages.
