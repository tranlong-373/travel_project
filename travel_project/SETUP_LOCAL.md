# Setup Local

Tài liệu này áp dụng khi bạn đang đứng trong folder `travel_project/`. README đầy đủ nằm ở `../README.md`.

## Chạy Local

```bash
cd accommodation_project
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
cd accommodation_project
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

## Test Nhanh

```bash
cd accommodation_project
python -B manage.py check
python -B manage.py makemigrations --check --dry-run
python -B manage.py test chat_api
python -m pip check
```

Nếu cần đổi SQL Server instance, tạo `accommodation_project/accommodation_project/settings_local.py` và override `DATABASE_OVERRIDES`.
