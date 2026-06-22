import os


class Settings:
    """Настройки приложения."""
    
    # JWT настройки
    JWT_SECRET_KEY: str = os.getenv("JWT_SECRET_KEY", "test-secret-key")
    JWT_ALGORITHM: str = os.getenv("JWT_ALGORITHM", "HS256")
    
    # B2B настройки
    B2B_BASE_URL: str = os.getenv("B2B_BASE_URL", "http://localhost:8001")
    B2B_SERVICE_KEY: str = os.getenv("B2B_SERVICE_KEY", "moderation-service-secret-key")
    
    # База данных
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./test.db")
    
    # Moderation настройки
    MODERATION_SERVICE_KEY: str = os.getenv("MODERATION_SERVICE_KEY", "test-service-key")


settings = Settings()