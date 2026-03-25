from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from database import get_connection
from services.recommend import recommend_orchestrator

app = FastAPI(title="Travel Recommendation API", version="1.0")


class RecommendationRequest(BaseModel):
    city: Optional[str] = Field(None, description="Lọc theo thành phố")
    budget_max: Optional[float] = Field(None, ge=0, description="Ngân sách tối đa")
    type: Optional[str] = Field(None, description="Loại chỗ ở")
    user_lat: Optional[float] = Field(None, description="Vĩ độ người dùng")
    user_lon: Optional[float] = Field(None, description="Kinh độ người dùng")
    radius_km: Optional[float] = Field(None, gt=0, description="Bán kính tìm kiếm (km)")
    amenities: Optional[List[str]] = Field(None, description="Tiện nghi bắt buộc")
    user_profile: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Thông tin user cho scoring")
    top_n: int = Field(5, ge=1, le=20, description="Số lượng kết quả trả về")


@app.get("/")
def root() -> Dict[str, str]:
    return {"message": "Backend đang chạy"}


@app.get("/test-db")
def test_db() -> Dict[str, Any]:
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        row = cursor.fetchone()
        cursor.close()
        conn.close()
        return {"message": "Kết nối database thành công", "result": row[0]}
    except Exception as e:
        return {"message": "Kết nối database thất bại", "error": str(e)}


@app.get("/accommodations")
def get_accommodations() -> Dict[str, Any]:
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT AccommodationID, Name, City, AccommodationType, PricePerNight, Rating, MaxPeople, Amenities, Latitude, Longitude
            FROM dbo.Accommodations
        """)
        rows = cursor.fetchall()
        cursor.close()
        conn.close()

        items = []
        for row in rows:
            items.append({
                "id": row.AccommodationID,
                "name": row.Name,
                "city": row.City,
                "type": row.AccommodationType,
                "price": float(row.PricePerNight),
                "rating": float(row.Rating) if row.Rating is not None else 0.0,
                "max_people": int(row.MaxPeople) if row.MaxPeople is not None else 0,
                "amenities": [a.strip() for a in str(row.Amenities or "").split(",") if a.strip()],
                "lat": float(row.Latitude) if row.Latitude is not None else None,
                "lng": float(row.Longitude) if row.Longitude is not None else None,
                "description": f"{row.Name} in {row.City}",
            })

        return {"results": items}
    except Exception as e:
        raise HTTPException(status_code=500, detail={"message": "Lấy dữ liệu thất bại", "error": str(e)})


@app.post("/recommend")
def recommend(request: RecommendationRequest) -> Dict[str, Any]:
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT AccommodationID, Name, City, AccommodationType, PricePerNight, Rating, MaxPeople, Amenities, Latitude, Longitude
            FROM dbo.Accommodations
        """)
        rows = cursor.fetchall()

        data = []
        for row in rows:
            data.append({
                "id": row.AccommodationID,
                "name": row.Name,
                "city": row.City,
                "type": row.AccommodationType,
                "price": float(row.PricePerNight),
                "rating": float(row.Rating) if row.Rating is not None else 0.0,
                "max_people": int(row.MaxPeople) if row.MaxPeople is not None else 0,
                "amenities": [a.strip().lower() for a in str(row.Amenities or "").split(",") if a.strip()],
                "lat": float(row.Latitude) if row.Latitude is not None else None,
                "lng": float(row.Longitude) if row.Longitude is not None else None,
                "description": f"{row.Name} in {row.City}",
            })

        cursor.close()
        conn.close()

        if not data:
            raise HTTPException(status_code=404, detail="Không có dữ liệu để xử lý")

        filter_payload = {
            "budget": {"min": 0.0, "max": request.budget_max} if request.budget_max is not None else None,
            "location": {
                "lat": request.user_lat,
                "lng": request.user_lon,
                "radius_km": request.radius_km,
            } if request.user_lat is not None and request.user_lon is not None and request.radius_km is not None else None,
            "amenities": request.amenities or [],
        }

        payload = {
            "filters": filter_payload,
            "user_profile": request.user_profile or {},
            "limit": request.top_n,
        }

        response = recommend_orchestrator(data, payload)
        return response

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi hệ thống: {e}")
 

