from __future__ import annotations
from typing import Any, Generic, List, Optional, TypeVar
from pydantic import BaseModel, Field
from pydantic.generics import GenericModel

T = TypeVar("T")

# Wrapper chuẩn cho response API
# Dùng để thống nhất format trả về cho toàn hệ thống
class APIResponse(GenericModel, Generic[T]):
    """Định dạng response chuẩn cho tất cả API."""

    success: bool = True
    message: Optional[str] = None
    data: Optional[T] = None
    error: Optional[str] = None


# Model dữ liệu chỗ ở lấy từ database
# Dùng để validate dữ liệu và đảm bảo đúng kiểu
class Accommodation(BaseModel):
    """Thông tin cơ bản của một chỗ lưu trú."""

    AccommodationID: int
    Name: str
    City: str
    AccommodationType: str
    PricePerNight: float
    Rating: float
    MaxPeople: int
    Amenities: Optional[List[str]] = None


# Model chỗ ở sau khi đã được chấm điểm
# Dùng trong kết quả recommendation
class ScoredAccommodation(Accommodation):
    """Chỗ ở sau khi đã được chấm điểm và có giải thích."""

    score: float
    reason: Optional[str] = None


# Model input cho tìm kiếm
# Nhận dữ liệu từ frontend hoặc chatbot
class SearchRequest(BaseModel):
    """Thông tin yêu cầu tìm kiếm của người dùng."""

    city: Optional[str] = None
    budget_max: Optional[float] = None
    type: Optional[str] = None
    people: Optional[int] = None
    amenities: Optional[List[str]] = None
    min_rating: Optional[float] = None


# Model input cho recommendation
# Kế thừa SearchRequest và thêm số lượng kết quả
class RecommendRequest(SearchRequest):
    """Payload cho API đề xuất chỗ ở."""

    limit: Optional[int] = Field(5, ge=1, le=20)


# Model input cho chatbot
# Chứa nội dung người dùng gửi lên
class ChatRequest(BaseModel):
    """Yêu cầu gửi từ người dùng tới chatbot."""

    message: str
    user_id: Optional[str] = None
    context: Optional[str] = None


# Model output của chatbot
# Trả về câu trả lời cho người dùng
class ChatResponse(BaseModel):
    """Phản hồi từ chatbot."""

    reply: str