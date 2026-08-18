import os

class Settings:
    PROJECT_NAME: str = "VietCraft AI Analytics Worker"
    VERSION: str = "1.0.0"
    API_V1_STR: str = "/api/v1"
    DATABASE_URL: str = os.getenv("DATABASE_URL", "postgresql://vietcraft_user:vietcraft_password@localhost:5432/vietcraft_db")
    PORT: int = int(os.getenv("PORT", 8000))

settings = Settings()
