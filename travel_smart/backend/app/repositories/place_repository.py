from typing import List, Dict, Any

class PlaceRepository:
    def __init__(self):
        # Nơi này thường inject Database Session (như SQLAlchemy Session hoặc MongoDB Client)
        pass

    def get_all_accommodations(self) -> List[Dict[str, Any]]:
        """Mock truy vấn dữ liệu từ CSDL."""
        # Thực tế sẽ là: return self.db.query(AccommodationModel).all()
        return [
            {
                "id": "1",
                "name": "Khách sạn Mường Thanh",
                "price": 1000000,
                "city": "Hà Nội",
                "lat": 21.028511,
                "lng": 105.804817,
                "amenities": ["wifi", "pool", "breakfast"],
                "description": "Khách sạn 5 sao cao cấp.",
                "rating": 4.5
            },
            # ... Thêm mock data khác nếu cần test
        ]
