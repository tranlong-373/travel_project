from typing import List, Optional
from pydantic import BaseModel, Field

class AccommodationLocation(BaseModel):
    city: Optional[str] = None
    lat: Optional[float] = None
    lng: Optional[float] = None

class RecommendationDetails(BaseModel):
    location: Optional[AccommodationLocation] = None
    amenities: List[str] = Field(default_factory=list)
    description: Optional[str] = None

class RecommendationItem(BaseModel):
    rank: int
    id: str | int
    name: str
    price: Optional[float] = None
    score: float
    reason: Optional[str] = Field(None, description="Lý do đề xuất (có thể sinh bởi rule hoặc AI)")
    reasoning: Optional[str] = Field(None, description="Lý do chi tiết từ AI (nếu dùng AI engine)")
    amenities: List[str] = Field(default_factory=list)
    location: Optional[AccommodationLocation] = None
    details: Optional[RecommendationDetails] = None

class RecommendationMetadata(BaseModel):
    total_matches: int
    returned_count: int

class RecommendationResponse(BaseModel):
    status: str = "success"
    metadata: RecommendationMetadata
    recommendations: List[RecommendationItem]

# Request Schema
class LocationFilter(BaseModel):
    lat: float
    lng: float
    radius_km: float

class RecommendationRequestFilters(BaseModel):
    budget_max: Optional[float] = None
    city: Optional[str] = None
    location: Optional[LocationFilter] = None
    amenities: Optional[List[str]] = None

class RecommendationRequest(BaseModel):
    filters: Optional[RecommendationRequestFilters] = Field(default_factory=RecommendationRequestFilters)
    user_profile: Optional[dict] = Field(default_factory=dict)
    limit: int = Field(default=5, ge=1, le=50)
