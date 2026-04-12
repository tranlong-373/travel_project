# OpenWeatherAPI (Django app)

## 1. Giới thiệu

App Django tái sử dụng để lấy thời tiết hiện tại từ [OpenWeatherMap Current Weather API](https://openweathermap.org/current). Phần gọi HTTP nằm ở `services/`, chuẩn hoá dữ liệu ở `utils/`, còn `get_weather()` là điểm vào gọn nhất cho các app khác.

## 2. Cài đặt

1. Thêm app vào `INSTALLED_APPS`:

```python
INSTALLED_APPS = [
    # ...
    "OpenWeatherAPI",
]
```

2. Gắn URL (ví dụ trong `urls.py` của project):

```python
urlpatterns = [
    # ...
    path("api/", include("OpenWeatherAPI.urls")),
]
```

3. Cài dependency (khuyến nghị dùng virtualenv):

```bash
pip install -r requirements.txt
```

4. Tạo file `.env` (ở thư mục gốc repo hoặc cùng cấp với `manage.py`) và đặt key:

```env
OPENWEATHER_API_KEY=your_key_here
```

## 3. Cách sử dụng (từ code Python)

```python
from OpenWeatherAPI.services.openweather_service import get_weather

data = get_weather("Ho Chi Minh")
print(data)
```

Hoặc dùng service trực tiếp khi cần mở rộng (session, timeout, mock):

```python
from OpenWeatherAPI.services.openweather_service import OpenWeatherService
from OpenWeatherAPI.utils.formatter import format_weather

service = OpenWeatherService()
raw = service.get_current_weather("Da Nang")
clean = format_weather(raw)
```

## 4. Ví dụ output

```json
{
  "city": "Ho Chi Minh City",
  "temperature": 30.0,
  "description": "clear sky",
  "humidity": 65
}
```

`temperature` dùng đơn vị **°C** (OpenWeather được gọi với `units=metric`).

## 5. HTTP endpoint (optional)

Sau khi include URL như mục (2), gọi:

`GET /api/weather/?city=Hanoi`

## 6. Lưu ý

- Cần có biến môi trường `OPENWEATHER_API_KEY` (hoặc trong `.env`).
- Nên cài `python-dotenv` để tự động nạp `.env` khi chạy local (app sẽ tìm file `.env` ở các thư mục cha gần nhất).
- Không hardcode API key trong code.
- Hướng mở rộng: có thể thêm client forecast/7-day bằng cách bổ sung class/method mới trong `services/` và formatter riêng trong `utils/`.
