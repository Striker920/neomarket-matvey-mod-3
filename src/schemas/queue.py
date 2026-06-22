from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
from datetime import datetime


class ClaimRequest(BaseModel):
    """Запрос на получение карточки из очереди."""
    queue_priority: Optional[int] = Field(None, ge=1, le=4, description="ID очереди (1-4)")


class TicketResponse(BaseModel):
    """Ответ с карточкой из очереди."""
    id: str
    product_id: str
    seller_id: str
    status: str
    queue_priority: int
    json_before: Optional[Dict[str, Any]] = None
    json_after: Optional[Dict[str, Any]] = None
    moderator_id: Optional[str] = None
    date_created: datetime
    date_updated: datetime
    
    model_config = {"from_attributes": True}