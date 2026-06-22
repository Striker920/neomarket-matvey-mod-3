from pydantic import BaseModel, Field
from typing import Optional, Any, Dict
from datetime import datetime
from enum import Enum


class ProductEventType(str, Enum):
    """Типы событий о товаре от B2B (по moderation/openapi.yaml)."""
    PRODUCT_CREATED = "PRODUCT_CREATED"
    PRODUCT_EDITED = "PRODUCT_EDITED"
    PRODUCT_DELETED = "PRODUCT_DELETED"


class ProductEventPayload(BaseModel):
    """Обёртка payload события."""
    product_id: str
    seller_id: Optional[str] = None
    product_data: Optional[Dict[str, Any]] = None


class IncomingB2BEvent(BaseModel):
    """
    Схема входящего события от B2B (по moderation/openapi.yaml).
    
    Обязательные поля:
    - event_type: тип события (PRODUCT_CREATED / PRODUCT_EDITED / PRODUCT_DELETED)
    - idempotency_key: ключ идемпотентности (генерирует B2B)
    - occurred_at: время возникновения события
    - payload: данные события
    """
    event_type: ProductEventType
    idempotency_key: str = Field(..., min_length=1, max_length=255)
    occurred_at: datetime
    payload: ProductEventPayload


class EventResponse(BaseModel):
    """Ответ при успешной обработке события."""
    status: str = "accepted"
    idempotency_key: str
    product_id: str