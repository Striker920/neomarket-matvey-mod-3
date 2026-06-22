from dataclasses import dataclass, field
from typing import Optional, Any
from datetime import datetime
import uuid


@dataclass
class ModerationCard:
    product_id: str
    seller_id: str
    status: str  # PENDING, IN_REVIEW, MODERATED, BLOCKED, HARD_BLOCKED
    queue_priority: int = 1
    json_before: Optional[dict] = None
    json_after: Optional[dict] = None
    blocking_reason_id: Optional[str] = None
    moderator_id: Optional[str] = None
    moderator_comment: Optional[str] = None
    field_reports: list = field(default_factory=list)
    date_created: datetime = field(default_factory=datetime.utcnow)
    date_updated: datetime = field(default_factory=datetime.utcnow)
    date_moderation: Optional[datetime] = None


@dataclass
class Store:
    moderation_cards: dict[str, ModerationCard] = field(default_factory=dict)
    products: dict[str, dict] = field(default_factory=dict)
    blocking_reasons: list[dict] = field(default_factory=list)
    
    def new_id(self) -> str:
        return str(uuid.uuid4())
