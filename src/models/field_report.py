from sqlalchemy import Column, String, DateTime, Text
from sqlalchemy.sql import func
from src.database import Base


class ProductModerationFieldReport(Base):
    __tablename__ = "product_moderation_field_report"

    id = Column(String(36), primary_key=True)
    product_moderation_id = Column(String(36), nullable=False, index=True)
    field_name = Column(String(50), nullable=False)
    sku_id = Column(String(36), nullable=True)
    comment = Column(Text, nullable=False)
    date_created = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
