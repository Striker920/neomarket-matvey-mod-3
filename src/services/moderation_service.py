from sqlalchemy.orm import Session
from src.models.product_moderation import ProductModeration
from datetime import datetime


class ModerationService:
    def __init__(self, db: Session):
        self.db = db

    def get_next_card(self, queue_id: int = None, moderator_id: str = None) -> dict:
        if queue_id is not None and (queue_id < 1 or queue_id > 4):
            return {"code": "INVALID_QUEUE", "message": "queueId must be 1-4"}

        queues_to_check = [queue_id] if queue_id else [1, 2, 3, 4]

        for q in queues_to_check:
            card = self.db.query(ProductModeration).filter(
                ProductModeration.status == "PENDING",
                ProductModeration.queue_priority == q
            ).order_by(ProductModeration.date_updated.asc()).first()

            if card:
                card.status = "IN_REVIEW"
                card.moderator_id = moderator_id
                card.date_updated = datetime.utcnow()
                self.db.commit()

                return {
                    "product_moderation_id": card.id,
                    "product_id": card.product_id,
                    "seller_id": card.seller_id,
                    "status": card.status,
                    "queue_priority": card.queue_priority,
                    "json_before": card.json_before,
                    "json_after": card.json_after,
                    "date_created": str(card.date_created) if card.date_created else None,
                    "date_updated": str(card.date_updated) if card.date_updated else None
                }

        return {"status": "empty"}
