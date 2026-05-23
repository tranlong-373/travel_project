# Accommodation Recommendation Project

Hệ thống Django gợi ý nơi lưu trú từ nhu cầu nhập bằng văn bản hoặc giọng nói. Code chính nằm trong:

```
travel_project/accommodation_project
```

Luồng chính:

```
user text / voice
  → chat_api parse slots
  → user xác nhận
  → chat_api submit / voice_api save
  → UserPreference
  → recommendations result
```

`chat_api` chuẩn hóa câu tự nhiên thành slots có cấu trúc. `recommendations` đọc `UserPreference` rồi tính điểm trên dữ liệu `Accommodation`.

---

## Các App

| App | Chức năng |
|---|---|
| `accommodations` | Danh sách, chi tiết, phòng, review, favorite |
| `accounts` | Đăng ký, đăng nhập, profile, Firebase token, Google OAuth |
| `chat_api` | Parse text tự nhiên, quản lý slots, tạo `UserPreference` qua API |
| `voice_api` | Nhận audio, transcribe bằng Hugging Face ASR, chuyển vào `chat_api` |
| `preferences` | Model và form lưu nhu cầu người dùng |
| `recommendations` | Lấy `pref_id`, chọn ứng viên, tính điểm, render kết quả HTML |

---

## Yêu Cầu Môi Trường

- Python 3.10+ (đã kiểm tra với 3.12.3)
- SQL Server local hoặc remote, có database `AccommodationDB`
- Microsoft ODBC Driver 18 for SQL Server
- `ffmpeg` cài ở cấp hệ điều hành (dùng cho voice API)
- Các package Python trong `requirements.txt`

Database mặc định trong `settings.py`:

```
ENGINE : mssql
NAME   : AccommodationDB
HOST   : localhost
DRIVER : ODBC Driver 18 for SQL Server
```

Nếu máy dùng instance khác, tạo file override tại:

```
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

---

## Cài Và Chạy

### WSL / Linux / macOS

```bash
cd travel_project/accommodation_project
python3 -m venv venv
source venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
cp .env.example .env
python manage.py makemigrations
python manage.py check
python manage.py migrate
python seed.py
python manage.py createsuperuser
python manage.py runserver
```

### Windows PowerShell

```powershell
cd travel_project\accommodation_project
py -3 -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
copy .env.example .env
python manage.py makemigrations
python manage.py check
python manage.py migrate
python seed.py
python manage.py createsuperuser
python manage.py runserver
```

Server mặc định: `http://127.0.0.1:8000/`

> `seed.py` xóa dữ liệu `Accommodation` hiện có rồi tạo dữ liệu demo. Chỉ chạy trên database local/demo.

---

## URL và API

### Web

| URL | Mô tả |
|---|---|
| `GET /` | Trang home |
| `GET /admin/` | Django admin |
| `GET /accounts/login/` | Đăng nhập (thường, Firebase, Google) |
| `GET /accounts/register/` | Đăng ký tài khoản |
| `GET /accounts/profile/` | Profile user |
| `GET /accommodations/` | Danh sách chỗ ở |
| `GET /accommodations/<id>/` | Chi tiết chỗ ở |
| `GET /recommendations/<pref_id>/` | Kết quả gợi ý (HTML) |

### Chat API

| Endpoint | Mô tả |
|---|---|
| `GET /api/chat/health/` | Health check |
| `POST /api/chat/parse/` | Parse câu nhập, trả slots |
| `POST /api/chat/submit/` | Tạo `UserPreference`, trả `pref_id` |

### Voice API

| Endpoint | Mô tả |
|---|---|
| `POST /api/voice/parse/` | Nhận field `audio` hoặc `file` (multipart) |

Flow: audio upload → WAV 16kHz mono → transcript → cleanup tiếng Việt → `chat_api` slots → `UserPreference`.

### Auth API

| Endpoint | Mô tả |
|---|---|
| `POST /api/auth/firebase-login/` | Firebase token login |
| `GET /auth/google/start` | Bắt đầu Google OAuth |
| `GET /auth/google/callback` | Callback Google OAuth |

---

## Flow Chat → Recommendation

1. Frontend gửi câu user vào `POST /api/chat/parse/`.
2. API trả slots, `missing_slots`, `follow_up_question` và bảng xác nhận nếu đủ dữ liệu.
3. Nếu thiếu dữ liệu, frontend hỏi tiếp, gửi lại kèm `context_slots`.
4. Khi user xác nhận, gọi `POST /api/chat/submit/` với `slots`.
5. API tạo `UserPreference`, trả `pref_id` và `recommendation_url`.
6. Frontend mở `GET /recommendations/<pref_id>/`.

**Core slots:** `area`, `budget`, `guest_count`, `trip_days`

**Optional slots:** `preferred_type`, `required_amenities`, `priorities`, `special_requirements`

> `UserPreference` hiện lưu `area`, `budget`, `guest_count`, `preferred_type`, `required_amenities`. Các field `trip_days`, `priorities`, `special_requirements` có trong response để phục vụ hội thoại nhưng chưa lưu vào model downstream.

### Ví dụ nhanh

Parse:

```bash
curl -X POST http://127.0.0.1:8000/api/chat/parse/ \
  -H "Content-Type: application/json" \
  -d '{"text":"Khách sạn ở Sài Gòn cho 2 người, 2 ngày, budget 900k, có wifi"}'
```

Submit sau xác nhận:

```bash
curl -X POST http://127.0.0.1:8000/api/chat/submit/ \
  -H "Content-Type: application/json" \
  -d '{"confirmed":true,"slots":{"area":"tp hcm","budget":900000,"guest_count":2,"preferred_type":"hotel","required_amenities":["wifi"]}}'
```

---

## Cấu Hình `.env`

```bash
cp .env.example .env
```

| Nhóm | Biến |
|---|---|
| Firebase client | `FIREBASE_API_KEY`, `FIREBASE_AUTH_DOMAIN`, `FIREBASE_PROJECT_ID`, `FIREBASE_STORAGE_BUCKET`, `FIREBASE_MESSAGING_SENDER_ID`, `FIREBASE_APP_ID`, `FIREBASE_MEASUREMENT_ID` |
| Firebase admin | Toàn bộ nhóm `FIREBASE_ADMIN_*` |
| Google OAuth | `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REDIRECT_URI`, `FRONTEND_URL`, `COOKIE_SECURE` |
| Chat parser | `CHAT_API_LLM_STRATEGY`, `CHAT_API_MODEL`, `CHAT_API_LIGHT_MODEL`, `CHAT_API_FALLBACK_MODEL`, `CHAT_API_STRONG_MODEL`, `CHAT_API_DEVICE`, `CHAT_API_TIMEOUT_SECONDS` |
| Voice | `STT_BACKEND`, `VOICE_WEAK_MODEL`, `VOICE_BALANCED_MODEL`, `VOICE_STRONG_MODEL`, `HF_TOKEN`, `HF_API_MODEL`, `VOICE_MAX_AUDIO_MB`, `VOICE_DEVICE` |

**Voice backend:**

| Trường hợp | Cấu hình |
|---|---|
| Demo / local, ưu tiên tiếng Việt | `STT_BACKEND=local` + `vinai/PhoWhisper-medium` hoặc `large` |
| API đơn giản / free | `STT_BACKEND=hf_api` + `HF_API_MODEL=openai/whisper-large-v3` + `HF_TOKEN` |
| Máy yếu | `vinai/PhoWhisper-base` hoặc `medium` |

Google OAuth local redirect mặc định: `http://127.0.0.1:8000/auth/google/callback` (không có dấu `/` cuối).

---

## Dependencies

| Nhóm | Package |
|---|---|
| Core | `Django`, `python-dotenv`, `requests` |
| Database | `mssql-django`, `pyodbc` |
| Auth | `firebase-admin`, `google-auth` |
| NLP / Fuzzy | `rapidfuzz`, `sentence-transformers` |
| AI / Voice | `transformers`, `torch`, `accelerate` |

Nếu local ASR báo thiếu audio runtime, kiểm tra thêm `librosa`, `soundfile`, `torchaudio` tùy máy.

---

## Test Nhanh

```bash
python -B manage.py check
python -B manage.py makemigrations --check --dry-run
python -B manage.py test chat_api
python -m pip check
```

---

## Bảo Mật

Không commit `.env`, private key JSON, token hoặc service account. Kiểm tra nhanh trước khi push:

```bash
git status --short
git check-ignore -v travel_project/accommodation_project/.env
rg --hidden -n "AIz[a-zA-Z0-9_-]{30,}|GOCSPX-[A-Za-z0-9_-]+|BEGIN[ ]PRIVATE[ ]KEY" \
  --glob '!**/.env' --glob '!**/.venv/**' --glob '!**/.git/**'
```

Nếu lỡ commit key thật, rotate lại trong Firebase / Google Cloud trước khi dùng tiếp.

---

## Giới Hạn Hiện Tại

- `GET /recommendations/<pref_id>/` render HTML, chưa phải JSON API.
- Dữ liệu seed là demo; kết quả gợi ý phụ thuộc dữ liệu thật trong DB.
- `preferred_type = "resort"` chưa được lưu vì model chỉ hỗ trợ `hotel`, `homestay`, `hostel`, `apartment`.
- HF model nặng, lần chạy đầu cần tải về.
- Voice API phụ thuộc chất lượng audio, `ffmpeg` và trạng thái Hugging Face Inference API.
