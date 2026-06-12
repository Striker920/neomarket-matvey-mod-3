import os
from dotenv import load_dotenv

load_dotenv()

class Settings:
    JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "moderation-secret-key-change-in-production")
    JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")

    B2B_SERVICE_URL = os.getenv("B2B_SERVICE_URL", "http://localhost:8000")
    B2B_SERVICE_KEY = os.getenv("B2B_SERVICE_KEY", "b2b-secret-key-123")

    DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./moderation.db")

    DEBUG = os.getenv("DEBUG", "True").lower() == "true"

settings = Settings()
