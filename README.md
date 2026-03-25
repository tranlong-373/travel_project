# Travel Recommendation API

Dự án Backend cho hệ thống gọi ý chỗ ở (Accommodation Recommendation), được xây dựng bằng **FastAPI** và **Python**, kết nối với cơ sở dữ liệu để lọc, đánh giá, và gợi ý chỗ ở phù hợp cho người dùng dựa trên nhiều tiêu chí (ngân sách, khoảng cách, tiện ích, hồ sơ người dùng).

## Tính năng nổi bật
* **Lọc theo nhiều tiêu chí:** Tìm kiếm kết hợp theo ngân sách tối đa (budget), khoảng cách tính theo tọa độ người dùng thông qua bán kính (location/radius), và danh sách các tiện nghi mong muốn.
* **Gợi ý thông minh (Recommendation Orchestrator):** Đánh giá (Scoring) điểm phù hợp của chỗ ở dựa trên `user_profile` và các đặc trưng của từng địa điểm.
* **RESTful API:** Các endpoint rõ ràng, chuẩn HTTP state trả về JSON đầy đủ chi tiết với validation được quản lý chặt chẽ qua `Pydantic`.
* **Database Connection:** Kết nối trực tiếp để truy xuất và xử lý tập dữ liệu nhà ở (`Accommodations`).

## Tech Stack
* **Framework:** FastAPI
* **Ngôn ngữ:** Python 3
* **Validation:** Pydantic
* **Database:** SQL Server (sử dụng thư viện kết nối cơ sở dữ liệu qua ODBC)

## Cấu trúc dự án

```text
travel_project/
├── Back_end.py          # File chính khởi chạy FastAPI, định nghĩa các API Routes
├── database.py          # Quản lý cấu hình và chuỗi kết nối Database
├── services/
│   ├── recommend.py     # Luồng điều phối chính (Orchestrator), tích hợp Filter và Scoring
│   ├── filter.py        # Logic lọc dữ liệu sơ bộ 
│   ├── scoring.py       # Logic chấm điểm trọng số cho các chỗ ở
│   ├── ranking.py       # Phân loại và sắp xếp thứ hạng (rank) hiển thị dựa trên điểm số (scoring)
│   └── __init__.py
├── schemas/             # (Optional) Các Pydantic models bổ sung
├── mini_database.sql    # Script cơ sở dữ liệu dùng để khởi tạo
├── config/              # Chứa các file cấu hình thêm (nếu có)
└── README.md            # Tài liệu dự án
```

## ⚙️ Cài đặt & Chạy dự án

**1. Cài đặt các thư viện yêu cầu:**
Bạn cần đảm bảo `Python 3` đã được cài đặt, sau đó cài các dependencies cần thiết bằng pip (có thể thay đổi tuỳ vào file `requirements.txt` nếu có):
```bash
pip install fastapi uvicorn pydantic pyodbc
```

**2. Cấu hình Database:**
Vào file `database.py` để đảm bảo chuỗi kết nối (`connection string`) đang trỏ đến đúng local database SQL Server của bạn. Bạn có thể sử dụng `mini_database.sql` để thiết lập trước các table dữ liệu mẫu.

**3. Khởi chạy Server Backend:**
Tại thư mục gốc dự án (`travel_project`), mở terminal/cmd và chạy:
```bash
uvicorn Back_end:app --reload
```
Server sẽ chạy ở địa chỉ mặc định: `http://127.0.0.1:8000`

## 📖 Danh sách API Endpoints

### 1. Kiểm tra trạng thái hệ thống
* **GET** `/`
  * Request test mặc định để xác nhận FastAPI đã lên sóng thành công.

### 2. Kiểm tra Database
* **GET** `/test-db`
  * Thực thi query cơ bản (`SELECT 1`) giúp kiểm tra xem kết nối backend đến database đã thông chưa. 

### 3. Lấy toàn bộ danh sách chỗ ở (Accommodations)
* **GET** `/accommodations`
  * Fetch toàn bộ bản ghi `Accommodations`. Thích hợp để test dữ liệu thô.

### 4. Gợi ý chỗ ở (Recommendation)
* **POST** `/recommend`
  * API cốt lõi nhận yêu cầu gọi ý từ frontend.
  * **Payload body (JSON) mẫu:**
    ```json
    {
      "city": "Da Nang",
      "budget_max": 2000000,
      "type": "Hotel",
      "user_lat": 16.0544,
      "user_lon": 108.2022,
      "radius_km": 5.0,
      "amenities": ["wifi", "pool", "breakfast"],
      "user_profile": {
        "preferences": ["quiet", "beach_view"]
      },
      "top_n": 5
    }
    ```

## 🔍 Tài liệu API tự động (Swagger UI)
Do sử dụng `FastAPI`, sau khi chạy bạn có thể xem các schema và gửi test requests trực quan qua trình duyệt:
* **Mở trình duyệt truy cập Swagger UI:** `http://127.0.0.1:8000/docs` 
* **Redoc UI (Format theo dạng docs tĩnh):** `http://127.0.0.1:8000/redoc`
