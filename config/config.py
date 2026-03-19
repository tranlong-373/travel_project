from __future__ import annotations
from typing import Optional
from pydantic import BaseSettings, Field


# Class chứa toàn bộ cấu hình của ứng dụng
# Tự động đọc giá trị từ file .env hoặc biến môi trường
class Settings(BaseSettings):
    """Application settings loaded from environment."""

    # Thông tin chung của ứng dụng
    app_name: str = "Travel Recommendation API"
    debug: bool = False

    # Cài đặt kết nối database
    # Dùng để build connection string tới SQL Server
    database_driver: str = Field("ODBC Driver 17 for SQL Server", env="DATABASE_DRIVER")
    database_server: str = Field("localhost", env="DATABASE_SERVER")
    database_name: str = Field("MiniSmartStayDB", env="DATABASE_NAME")
    database_trusted_connection: str = Field("yes", env="DATABASE_TRUSTED_CONNECTION")
    database_user: Optional[str] = Field(None, env="DATABASE_USER")
    database_password: Optional[str] = Field(None, env="DATABASE_PASSWORD")
    database_timeout: int = Field(30, env="DATABASE_TIMEOUT")

    # Cấu hình API bên ngoài 
    # Dùng cho chatbot/NLP nếu tích hợp sau này
    # openai_api_key: Optional[str] = Field(None, env="OPENAI_API_KEY")
    # openai_model: str = Field("gpt-3.5-turbo", env="OPENAI_MODEL")

    # Cấu hình mặc định cho recommendation
    # Số lượng kết quả trả về nếu user không chỉ định
    recommend_top_n: int = Field(5, env="RECOMMEND_TOP_N")

    # Cấu hình đọc file .env
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


# Khởi tạo object settings để dùng toàn hệ thống
settings = Settings()