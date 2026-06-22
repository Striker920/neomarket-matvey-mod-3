from sqlalchemy import Column, String, Boolean, DateTime
from datetime import datetime, timezone
from src.database import Base


class BlockingReason(Base):
    """
    Справочник причин блокировки товара.
    
    Не удаляется физически — только деактивируется (is_active=False),
    чтобы сохранить ссылки из исторических BLOCKED-карточек.
    
    Связи:
    - US-MOD-04 (мягкая блокировка) использует причины с hard_block=False
    - US-MOD-05 (жёсткая блокировка) использует причины с hard_block=True
    """
    __tablename__ = "blocking_reasons"

    id = Column(String, primary_key=True)
    title = Column(String, nullable=False, unique=True)
    description = Column(String, nullable=True)
    hard_block = Column(Boolean, nullable=False, default=False)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))