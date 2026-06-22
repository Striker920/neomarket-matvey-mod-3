from sqlalchemy import Column, String, DateTime
from datetime import datetime, timezone
from src.database import Base


class ProcessedEvent(Base):
    """
    Таблица обработанных событий для дедупликации по idempotency_key.
    
    Если B2B повторит событие (сетевой сбой, retry), мы вернём 409
    и не изменим состояние системы.
    """
    __tablename__ = "processed_events"

    idempotency_key = Column(String, primary_key=True)
    product_id = Column(String, nullable=False, index=True)
    event_type = Column(String, nullable=False)
    processed_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))