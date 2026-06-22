from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, Any, Dict
from datetime import datetime
from enum import Enum


class ProductEventType(str, Enum):
    """Типы событий о товаре от B2B (по moderation/openapi.yaml)."""
    PRODUCT_CREATED = "PRODUCT_CREATED"
    PRODUCT_EDITED = "PRODUCT_EDITED"
    PRODUCT_DELETED = "PRODUCT_DELETED"


class ProductEventPayload(BaseModel):
    """Обёртка payload события (по moderation/openapi.yaml:900, 916).
    
    Для CREATED: product_id, seller_id, json_after (обязательные)
    Для EDITED: product_id, seller_id, json_before (опц.), json_after (обязательное)
    Для DELETED: product_id, seller_id (опц.)
    """
    # ✅ extra='forbid' — Pydantic не будет молча отбрасывать поля
    model_config = ConfigDict(extra='forbid')
    
    product_id: str
    seller_id: Optional[str] = None
    # ✅ ИСПРАВЛЕНО: json_after + json_before вместо product_data
    json_after: Optional[Dict[str, Any]] = None   # обязательное для CREATED/EDITED
    json_before: Optional[Dict[str, Any]] = None  # для EDITED (предыдущий снимок)


class IncomingB2BEvent(BaseModel):
    """
    Схема входящего события от B2B (по moderation/openapi.yaml).
    
    Обязательные поля:
    - event_type: тип события
    - idempotency_key: ключ идемпотентности (UUID, генерирует B2B)
    - occurred_at: время возникновения события
    - payload: данные события
    """
    model_config = ConfigDict(extra='forbid')
    
    event_type: ProductEventType
    idempotency_key: str = Field(
        ...,
        min_length=1,
        max_length=255,
        # ✅ Валидация UUID по спецификации (format: uuid)
        pattern=r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
    )
    occurred_at: datetime
    payload: ProductEventPayload


class EventResponse(BaseModel):
    """Ответ при успешной обработке события."""
    status: str = "accepted"
    idempotency_key: str
    product_id: str