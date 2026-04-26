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

## Thêm một API mới 
Đưa terminal đến cùng cấp với file manage.py 
Gõ : python manage.py startapp TEN_API 
sau đó cập nhập một số setting cơ bản 

## Flow Tổng Quát

1. Frontend gửi câu user vào `POST /api/chat/parse/`.
2. Nếu thiếu core slots, API trả `follow_up_question`.
3. Frontend hỏi tiếp và gửi câu trả lời kèm `context_slots` cũ.
4. Khi đủ `area`, `budget`, `guest_count`, `trip_days` và `location_status = "ok"`, frontend hiển thị bảng xác nhận.
5. Khi user xác nhận, frontend gọi `POST /api/chat/submit/` với slots đã xác nhận.
6. `chat_api` tạo `UserPreference` và trả `pref_id`, `recommendation_url`.
7. Frontend mở hoặc gọi `GET /recommendations/<pref_id>/` để lấy trang kết quả recommendation.

Core slots bắt buộc:

- `area`
- `budget`
- `guest_count`
- `trip_days`

Optional slots parser có thể trả:

- `preferred_type`
- `required_amenities`
- `priorities`
- `special_requirements`

Lưu ý: `priorities`, `special_requirements`, `trip_days` hiện có trong parse response nhưng chưa được lưu vào `UserPreference` và chưa được dùng trực tiếp trong recommender.

## Cài Và Chạy Local

Từ repo root:

```powershell
cd accommodation_project
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python manage.py migrate
python seed.py
python manage.py runserver
```

Firebase Google login đọc cả client config và admin credentials từ `.env` cùng tầng với `manage.py`.

## Cấu Hình Nhận Diện Giọng Nói

Voice API đọc cấu hình từ `.env` và có STT router tự chọn model theo tình huống. Nếu request không gửi `feature_mode`, backend mặc định xem như `chat` và dùng `balanced`.

```env
VOICE_ASR_WEAK_MODEL=vinai/PhoWhisper-tiny
VOICE_ASR_BALANCED_MODEL=vinai/PhoWhisper-base
VOICE_ASR_STRONG_MODEL=vinai/PhoWhisper-small
VOICE_ASR_FALLBACK_MODEL=vinai/PhoWhisper-tiny
VOICE_ASR_LANGUAGE=vi
VOICE_ASR_TASK=transcribe
VOICE_DEVICE=auto
VOICE_MAX_NEW_TOKENS=96
VOICE_NUM_BEAMS=1
VOICE_CHUNK_LENGTH_S=0
VOICE_ASR_BATCH_SIZE=1
```

Các level model:

- `weak`: `vinai/PhoWhisper-tiny`, dùng cho lệnh ngắn, wake word, realtime preview, ưu tiên tốc độ.
- `balanced`: `vinai/PhoWhisper-base`, mặc định cho chat/casual voice.
- `strong`: `vinai/PhoWhisper-small`, dùng cho dịch thuật, ghi chú dài, dictation, code input, audio chất lượng kém hoặc cần độ chính xác cao.

Router có thể tự nâng model và retry nếu transcript rỗng, confidence thấp, audio dài nhưng transcript quá ngắn, hoặc transcript có nhiều ký tự lạ.

Ví dụ chọn model:

- `feature_mode=command`, audio 2 giây -> `weak`.
- `feature_mode=chat` -> `balanced`.
- `feature_mode=translation` -> `strong`.
- `feature_mode=chat`, audio 18 giây -> `strong`.
- Transcript lỗi sau `weak` -> retry bằng `balanced`.

Các alias cũ vẫn được hỗ trợ. Nếu muốn override balanced/default trực tiếp, thêm:

```env
VOICE_ASR_MODEL=vinai/PhoWhisper-base
```

Frontend hiện giới hạn ghi âm ngắn, nên `VOICE_CHUNK_LENGTH_S=0` để giảm độ trễ. Lần đầu chạy voice có thể chậm vì Hugging Face cần tải model vào cache; các lần sau sẽ nhanh hơn.

## Cài Đặt Firebase Google Login

Tạo file `.env` thật từ file mẫu, đặt cùng tầng với `manage.py`:

```powershell
cd accommodation_project
copy .env.example .env
```

Trên Linux/macOS:

```bash
cd accommodation_project
cp .env.example .env
```

Trong Firebase Console:

1. Tạo hoặc mở Firebase project.
2. Vào `Authentication` -> `Sign-in method` -> bật provider `Google`.
3. Vào `Project settings` -> `General` -> tạo Web app nếu chưa có.
4. Copy web config vào các biến `FIREBASE_API_KEY`, `FIREBASE_AUTH_DOMAIN`, `FIREBASE_PROJECT_ID`, `FIREBASE_STORAGE_BUCKET`, `FIREBASE_MESSAGING_SENDER_ID`, `FIREBASE_APP_ID`, `FIREBASE_MEASUREMENT_ID`.
5. `FIREBASE_WEB_API_KEY` dùng cùng giá trị với `FIREBASE_API_KEY`.

Trong Firebase Admin:

1. Vào `Project settings` -> `Service accounts`.
2. Chọn `Generate new private key`.
3. Không commit file JSON private key lên git.
4. Copy từng field trong JSON vào nhóm biến `FIREBASE_ADMIN_*` trong `.env`.
5. Với `FIREBASE_ADMIN_PRIVATE_KEY`, giữ trong dấu nháy kép và để ký tự xuống dòng dạng `\n`.

Trong Google Cloud Console:

1. Vào `APIs & Services` -> `Credentials`.
2. Tạo hoặc mở OAuth Client loại `Web application`.
3. Thêm `Authorized JavaScript origins`:

```text
http://127.0.0.1:8000
http://localhost:8000
```

4. Thêm `Authorized redirect URIs` đúng y hệt `.env`:

```text
http://127.0.0.1:8000/auth/google/callback
```

Không thêm dấu `/` cuối URL callback. Nếu đổi sang `localhost` hoặc domain deploy thật, phải đổi cả `GOOGLE_REDIRECT_URI` trong `.env` và redirect URI trong Google Cloud cho trùng 100%.

Các biến Google cần có trong `.env`:

```env
GOOGLE_URL=http://127.0.0.1:8000/auth/google/start
GOOGLE_CLIENT_ID=YOUR_GOOGLE_CLIENT_ID
GOOGLE_CLIENT_SECRET=YOUR_GOOGLE_CLIENT_SECRET
GOOGLE_REDIRECT_URI=http://127.0.0.1:8000/auth/google/callback
FRONTEND_URL=http://127.0.0.1:8000
COOKIE_SECURE=false
```

Sau khi điền `.env`, chạy:

```powershell
python manage.py migrate
python manage.py runserver
```

Test tại:

```text
http://127.0.0.1:8000/accounts/login/
```

## Không Commit Secret

Các file secret/local đã được ignore: `.env`, `**/secrets/`, `*.json`, `__pycache__/`, `*.pyc`. Trước khi push nên kiểm tra:

```bash
git status --short
git check-ignore -v accommodation_project/.env
rg --hidden -n "AIz[a-zA-Z0-9_-]{30,}|GOCSPX-[A-Za-z0-9_-]+|BEGIN[ ]PRIVATE[ ]KEY|firebase-adminsdk-[A-Za-z0-9]+@" --glob '!**/.env' --glob '!**/.venv/**' --glob '!**/.git/**'
```

Nếu lỡ paste key thật vào git hoặc chat, hãy rotate lại key trong Firebase/Google Cloud trước khi dùng lâu dài.

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

- `chat_api` chỉ ready khi đủ `area`, `budget`, `guest_count`, `trip_days` và `location_status = "ok"`, sau đó cần user xác nhận trước khi submit.
- Location resolver hiện chỉ hỗ trợ scope: TP HCM, Hà Nội, Thanh Hóa, Đồng Nai, An Giang, Bình Định, Đà Lạt.
- `preferred_type = "resort"` chưa bật vì model downstream chỉ có `hotel`, `homestay`, `hostel`, `apartment`.
- `GET /recommendations/<pref_id>/` hiện render HTML template, không phải JSON API.
- Dữ liệu seed hiện chủ yếu là demo ở TP HCM, nên kết quả recommendation phụ thuộc dữ liệu thật trong DB.
