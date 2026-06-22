from sqlalchemy import Column, String, DateTime, JSON, Integer
from datetime import datetime, timezone
from src.database import Base


class ModerationCard(Base):
    """
    Карточка модерации товара.
    
    Состояния: PENDING → IN_REVIEW → MODERATED / BLOCKED / HARD_BLOCKED
    """
    __tablename__ = "moderation_cards"

    id = Column(String, primary_key=True)
    product_id = Column(String, nullable=False, index=True, unique=True)
    seller_id = Column(String, nullable=False, index=True)
    status = Column(String, nullable=False, default="PENDING")
    queue_priority = Column(Integer, nullable=False, default=1)
    json_before = Column(JSON, nullable=True)
    json_after = Column(JSON, nullable=True)
    blocking_reason_id = Column(String, nullable=True)
    moderator_id = Column(String, nullable=True)
    moderator_comment = Column(String, nullable=True)
    date_created = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    date_updated = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    date_moderation = Column(DateTime(timezone=True), nullable=True)