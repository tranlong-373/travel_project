# Accommodation Recommendation Project

Project Django quản lý dữ liệu chỗ ở và hỗ trợ gợi ý nơi ở từ nhu cầu nhập bằng text hoặc voice. Code chính nằm trong:

```text
travel_project/accommodation_project
```

Luồng chính hiện tại:

```text
user text/voice
-> chat_api parse slots
-> user xác nhận
-> chat_api submit / voice_api save
-> UserPreference
-> recommendations result
```

`chat_api` không tự recommend trực tiếp. App này chuẩn hóa câu tự nhiên thành slots có cấu trúc. `recommendations` đọc dữ liệu sạch qua `UserPreference` rồi tính điểm với dữ liệu `Accommodation`.

## App Chính

- `accommodations`: danh sách chỗ ở, chi tiết, phòng, review, favorite.
- `accounts`: đăng ký, đăng nhập, profile, Firebase token login, Google OAuth login.
- `chat_api`: parse text tự nhiên, quản lý core slots, tạo `UserPreference` qua API submit.
- `voice_api`: nhận audio upload, transcribe bằng Hugging Face ASR, cleanup transcript rồi đưa qua `chat_api`.
- `preferences`: model/form lưu nhu cầu người dùng.
- `recommendations`: lấy `pref_id`, chọn candidate accommodations, tính score và render kết quả HTML.

## Yêu Cầu Môi Trường

- Python 3.10+.
- SQL Server local hoặc remote, có database `AccommodationDB`.
- Microsoft ODBC Driver 18 for SQL Server.
- Các package Python trong `travel_project/accommodation_project/requirements.txt`.

Database mặc định trong `settings.py`:

```text
ENGINE: mssql
NAME: AccommodationDB
HOST: localhost
DRIVER: ODBC Driver 18 for SQL Server
```

Nếu máy dùng DB/instance khác, tạo file local override tại:

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

## Cài Và Chạy Web

Từ repo root:

```bash
cd travel_project/accommodation_project
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
cp .env.example .env
python -B manage.py migrate
python -B seed.py
python -B manage.py runserver
```

Trên Windows PowerShell:

```powershell
cd travel_project\accommodation_project
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
copy .env.example .env
python -B manage.py migrate
python -B seed.py
python -B manage.py runserver
```

Server mặc định:

```text
http://127.0.0.1:8000/
```

Lưu ý: `seed.py` xóa dữ liệu `Accommodation` hiện có rồi tạo dữ liệu demo. Chỉ chạy trên database local/demo.

## URL Và API Chính

Web pages:

- `GET /`: trang home.
- `GET /admin/`: Django admin.
- `GET /accounts/login/`: đăng nhập thường, Firebase client login và Google login.
- `GET /accounts/register/`: đăng ký tài khoản.
- `GET /accounts/profile/`: profile user.
- `GET /accommodations/`: danh sách chỗ ở.
- `GET /accommodations/<id>/`: chi tiết chỗ ở.
- `GET /recommendations/<pref_id>/`: kết quả gợi ý dạng HTML.

Chat API:

- `GET /api/chat/health/`
- `POST /api/chat/parse/`
- `POST /api/chat/submit/`

Voice API:

- `POST /api/voice/parse/` với multipart field `audio` hoặc `file`.

Auth API:

- `POST /api/auth/firebase-login/`
- `GET /auth/google/start`
- `GET /auth/google/callback`

## Flow Chat Recommendation

1. Frontend gửi câu user vào `POST /api/chat/parse/`.
2. API trả slots đã parse, `missing_slots`, `follow_up_question`, trạng thái location và bảng xác nhận nếu đủ dữ liệu.
3. Nếu còn thiếu dữ liệu, frontend hỏi tiếp và gửi câu trả lời kèm `context_slots` hoặc `current_slots`.
4. Khi user xác nhận, frontend gọi `POST /api/chat/submit/` với `slots` hoặc `confirmed_slots`.
5. API tạo `UserPreference`, trả `pref_id` và `recommendation_url`.
6. Frontend mở `GET /recommendations/<pref_id>/`.

Core slots:

- `area`
- `budget`
- `guest_count`
- `trip_days`

Optional slots:

- `preferred_type`
- `required_amenities`
- `priorities`
- `special_requirements`

Hiện `UserPreference` chỉ lưu `area`, `budget`, `guest_count`, `preferred_type`, `required_amenities`. Các field `trip_days`, `priorities`, `special_requirements` có trong response để phục vụ hội thoại/xác nhận nhưng chưa được lưu vào model downstream.

Request parse mẫu:

```json
{
  "text": "Khách sạn ở Sài Gòn cho 2 người, 2 ngày, budget 900k, có wifi",
  "locale": "vi",
  "context_slots": {}
}
```

Request submit sau khi user xác nhận:

```json
{
  "confirmed": true,
  "slots": {
    "area": "tp hcm",
    "budget": 900000,
    "guest_count": 2,
    "trip_days": 2,
    "preferred_type": "hotel",
    "required_amenities": ["wifi"]
  },
  "locale": "vi"
}
```

## Cấu Hình `.env`

Tạo `.env` từ file mẫu:

```bash
cd travel_project/accommodation_project
cp .env.example .env
```

Nhóm biến chính:

- Firebase client: `FIREBASE_API_KEY`, `FIREBASE_AUTH_DOMAIN`, `FIREBASE_PROJECT_ID`, `FIREBASE_STORAGE_BUCKET`, `FIREBASE_MESSAGING_SENDER_ID`, `FIREBASE_APP_ID`, `FIREBASE_MEASUREMENT_ID`.
- Firebase admin: toàn bộ nhóm `FIREBASE_ADMIN_*`.
- Google OAuth: `GOOGLE_URL`, `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REDIRECT_URI`, `FRONTEND_URL`, `COOKIE_SECURE`.
- Chat/HF parser: `CHAT_API_ENABLE_HF_AGENT`, `CHAT_API_LLM_STRATEGY`, `CHAT_API_MODEL`, `CHAT_API_FALLBACK_MODEL`, `CHAT_API_DEVICE`, `CHAT_API_TIMEOUT_SECONDS`, `CHAT_API_USE_NER`, `CHAT_API_NER_MODEL`.
- Voice: `VOICE_ASR_MODEL`, `VOICE_DEVICE`, `VOICE_MAX_AUDIO_MB`, `VOICE_MAX_NEW_TOKENS`, `VOICE_CHUNK_LENGTH_S`.

Google OAuth local redirect mặc định:

```text
http://127.0.0.1:8000/auth/google/callback
```

Không thêm dấu `/` cuối callback. Nếu đổi sang `localhost` hoặc domain deploy, cập nhật đồng thời trong `.env` và Google Cloud Console.

## Requirements Đã Rà

`travel_project/accommodation_project/requirements.txt` là file dependency bắt buộc của project Django, nên giữ nguyên khi setup. Mình đã rà với code hiện tại:

- Core web: `Django`, `python-dotenv`, `requests`.
- SQL Server: `mssql-django`, `pyodbc`.
- Firebase/Google auth: `firebase-admin`; `google-auth` đang có qua dependency của Firebase Admin trong venv.
- Hugging Face text/voice parser: `transformers`, `torch`, `accelerate`.
- Các package cũ như `folium`, `overpy`, `google-generativeai`, `langchain*`, `chromadb` vẫn nằm trong requirements theo yêu cầu project, dù chưa thấy import trực tiếp trong code Django hiện tại.

Nếu dùng voice API mà môi trường mới báo thiếu audio runtime, kiểm tra thêm các package audio phụ thuộc của Hugging Face như `librosa`, `soundfile`, `torchaudio` hoặc cài `ffmpeg` ở cấp hệ điều hành.

## Test Nhanh

Chạy từ `travel_project/accommodation_project`:

```bash
python -B manage.py check
python -B manage.py makemigrations --check --dry-run
python -B manage.py test chat_api
```

Kiểm tra dependency trong venv:

```bash
python -m pip check
```

Nếu `makemigrations --check --dry-run` cảnh báo không kết nối được SQL Server, kiểm tra lại SQL Server, database `AccommodationDB`, ODBC Driver 18 và `settings_local.py`.

## Không Commit Secret

Không commit `.env`, private key JSON, token hoặc service account. Trước khi push có thể kiểm tra nhanh:

```bash
git status --short
git check-ignore -v travel_project/accommodation_project/.env
rg --hidden -n "AIz[a-zA-Z0-9_-]{30,}|GOCSPX-[A-Za-z0-9_-]+|BEGIN[ ]PRIVATE[ ]KEY|firebase-adminsdk-[A-Za-z0-9]+@" --glob '!**/.env' --glob '!**/.venv/**' --glob '!**/.git/**'
```

Nếu lỡ paste key thật vào git hoặc chat, rotate lại key trong Firebase/Google Cloud trước khi dùng tiếp.

## Giới Hạn Hiện Tại

- `GET /recommendations/<pref_id>/` render HTML template, chưa phải JSON API.
- Dữ liệu seed chủ yếu là demo, kết quả recommendation phụ thuộc dữ liệu thật trong DB.
- `preferred_type = "resort"` không lưu downstream vì model hiện chỉ hỗ trợ `hotel`, `homestay`, `hostel`, `apartment`.
- HF model mặc định có thể nặng và có thể cần tải model ở lần chạy đầu tiên.
- Voice API phụ thuộc chất lượng audio và runtime audio của máy local.
