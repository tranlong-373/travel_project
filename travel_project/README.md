# Accommodation Recommendation Project

Tài liệu chính của repo nằm ở:

```text
../README.md
```

Folder này chứa source chính của project. Nếu bạn đang đứng trong `travel_project/`, chạy local bằng:

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

Trên Windows PowerShell:

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
