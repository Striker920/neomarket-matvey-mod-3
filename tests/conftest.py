import sys
from pathlib import Path

root_path = str(Path(__file__).parent.parent)
if root_path not in sys.path:
    sys.path.insert(0, root_path)

import pytest
from jose import jwt
from uuid import uuid4
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

from src.database import Base, get_db
from src.main import app
from src.config import settings

# ✅ Импортируем модели, чтобы они зарегистрировались в Base.metadata
from src.models.moderation_card import ModerationCard
from src.models.event import ProcessedEvent


TEST_DATABASE_URL = "sqlite:///./test.db"


@pytest.fixture(scope="session")
def engine():
    """Создаём engine один раз для всей сессии."""
    engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def db_session(engine):
    """Создаёт сессию тестовой БД с очисткой таблиц между тестами."""
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        # ✅ Очистка таблиц между тестами — изоляция
        db.query(ModerationCard).delete()
        db.query(ProcessedEvent).delete()
        db.commit()
        db.rollback()
        db.close()


@pytest.fixture
def client(db_session):
    """Клиент, который использует ту же БД, что и фикстура."""
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def valid_jwt():
    payload = {"sub": str(uuid4())}
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


@pytest.fixture
def valid_jwt_with_fixed_id():
    expected_user_id = "123e4567-e89b-12d3-a456-426614174000"
    payload = {"sub": expected_user_id}
    token = jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    return token, expected_user_id


@pytest.fixture
def valid_service_headers():
    """Заголовки с валидным межсервисным ключом."""
    return {"X-Service-Key": settings.B2B_SERVICE_KEY}