import os
from dotenv import load_dotenv

load_dotenv()

class Settings:
    JWT_SECRET_KEY: str = "test-secret-key"
    JWT_ALGORITHM: str = "HS256"
    B2B_SERVICE_KEY: str = "test-b2b-service-key"
    DATABASE_URL: str = "sqlite:///./test.db"


settings = Settings()
