from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class BlockingReasonResponse(BaseModel):
    """Ответ для справочника причин блокировки (по OpenAPI)."""
    id: str
    title: str
    description: Optional[str] = None
    hard_block: bool
    is_active: bool
    
    model_config = {"from_attributes": True}


class BlockingReasonCreateRequest(BaseModel):
    """Запрос на создание причины блокировки (админка)."""
    title: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = Field(None, max_length=1000)
    hard_block: bool = False


class BlockingReasonUpdateRequest(BaseModel):
    """Запрос на обновление причины блокировки (админка)."""
    title: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = Field(None, max_length=1000)
    hard_block: Optional[bool] = None
    is_active: Optional[bool] = None