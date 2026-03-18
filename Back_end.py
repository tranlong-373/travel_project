from fastapi import FastAPI
from pydantic import BaseModel
from typing import Optional
from database import get_connection

app = FastAPI()
class SearchRequest(BaseModel):
    city: Optional[str] = None
    budget_max: Optional[float] = None
    type: Optional[str] = None


@app.get("/")
def root():
    return {"message": "Backend dang chay"}

@app.get("/test-db")
def test_db():
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        row = cursor.fetchone()

        cursor.close()
        conn.close()

        return {"message": "Ket noi database thanh cong", "result": row[0]}
    except Exception as e:
        return {"message": "Ket noi database that bai", "error": str(e)}

@app.get("/accommodations")
def get_accommodations():
    try:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT AccommodationID, Name, City, AccommodationType, PricePerNight, Rating, MaxPeople
            FROM dbo.Accommodations
        """)

        rows = cursor.fetchall()

        result = []
        for row in rows:
            result.append({
                "AccommodationID": row.AccommodationID,
                "Name": row.Name,
                "City": row.City,
                "AccommodationType": row.AccommodationType,
                "PricePerNight": float(row.PricePerNight),
                "Rating": float(row.Rating),
                "MaxPeople": row.MaxPeople
            })

        cursor.close()
        conn.close()

        return {"results": result}

    except Exception as e:
        return {"message": "Lay du lieu that bai", "error": str(e)}

    # xử lí đầu vào 
@app.post("/search")
def search_accommodations(request: SearchRequest):
    try:
        conn = get_connection()
        cursor = conn.cursor()

        query = """
            SELECT AccommodationID, Name, City, AccommodationType, PricePerNight, Rating, MaxPeople
            FROM dbo.Accommodations
            WHERE 1=1
        """
        params = []

        if request.city:
            query += " AND City = ?"
            params.append(request.city)

        if request.budget_max is not None:
            query += " AND PricePerNight <= ?"
            params.append(request.budget_max)

        if request.type:
            query += " AND AccommodationType = ?"
            params.append(request.type)

        cursor.execute(query, params)
        rows = cursor.fetchall()

        result = []
        for row in rows:
            result.append({
                "AccommodationID": row.AccommodationID,
                "Name": row.Name,
                "City": row.City,
                "AccommodationType": row.AccommodationType,
                "PricePerNight": float(row.PricePerNight),
                "Rating": float(row.Rating),
                "MaxPeople": row.MaxPeople
            })

        cursor.close()
        conn.close()

        return {
            "message": "Tim kiem thanh cong",
            "count": len(result),
            "results": result
        }

    except Exception as e:
        return {
            "message": "Tim kiem that bai",
            "error": str(e)
        }
# AI RECOMMENDATION  - 3 / xử lí đàu vào  / Đề cử (AI )   // Back end / # giao tiếp 