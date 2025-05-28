import os
from typing import Any, Dict, Optional
from pydantic import PostgresDsn, field_validator, model_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # API settings
    API_V1_STR: str = "/api"
    PROJECT_NAME: str = "FastAPI AI Chat Backend"
    
    # Security settings
    SECRET_KEY: str = os.getenv("SECRET_KEY", "b1c625c6ceaaccfec8b7e843c0b8dc25af2a5f660cd64a95b0d0b4b3746bf485")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24 hours
    REFRESH_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 days
    DEFAULT_RESET_PASSWORD: str = os.getenv("DEFAULT_RESET_PASSWORD", "Kunxiaozhi@123")  # 默认重置密码
    
    POSTGRES_HOST: str = os.getenv("PGHOST", "137.184.113.70")
    POSTGRES_PORT: str = os.getenv("PGPORT", "15432")
    POSTGRES_USER: str = os.getenv("PGUSER", "root")
    POSTGRES_PASSWORD: str = os.getenv("PGPASSWORD", "123456")
    POSTGRES_DB: str = os.getenv("PGDATABASE", "fastapi")
    DATABASE_URI: Optional[PostgresDsn] = os.getenv("DATABASE_URL")

    # Redis settings
    # REDIS_HOST: str = os.getenv("REDIS_HOST", "137.184.113.70")
    # REDIS_PORT: int = int(os.getenv("REDIS_PORT", "16379"))
    # REDIS_PASSWORD: str = os.getenv("REDIS_PASSWORD", "")
    # REDIS_DB: int = int(os.getenv("REDIS_DB", "0"))
    
    # Dify API settings
    DIFY_API_BASE_URL: str = os.getenv("DIFY_API_BASE_URL", "http://137.184.113.70/v1")
    DIFY_API_KEY: str = os.getenv("DIFY_API_KEY", "")
    
    # File storage settings
    FILE_STORAGE_PATH: str = os.getenv("FILE_STORAGE_PATH", "./uploads")
    MAX_UPLOAD_SIZE: int = int(os.getenv("MAX_UPLOAD_SIZE", str(10 * 1024 * 1024)))  # 10MB
    
    # Logging settings
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    LOG_FILE: str = os.getenv("LOG_FILE", "logs/app.log")
    
    @field_validator("DATABASE_URI", mode="before")
    def assemble_db_connection(cls, v: Optional[str], values: Dict[str, Any]) -> Any:
        if isinstance(v, str):
            return v
        
        # Build PostgreSQL connection string instead of PostgresDsn object to avoid type errors
        user = values.data.get("POSTGRES_USER")
        password = values.data.get("POSTGRES_PASSWORD")
        host = values.data.get("POSTGRES_HOST")
        port = values.data.get("POSTGRES_PORT")
        db = values.data.get("POSTGRES_DB") or ""
        
        return f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{db}"
    
    # @model_validator(mode="after")
    # def check_dify_api_key(self) -> "Settings":
    #     if not self.DIFY_API_KEY:
    #         # Log warning instead of raising error to allow app to start even if Dify API key is not set
    #         # The app should handle missing API key gracefully in the Dify service
    #         print("WARNING: DIFY_API_KEY not set. Dify API integration will not work.")
    #     return self


settings = Settings()
