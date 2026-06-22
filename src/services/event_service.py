from sqlalchemy.orm import Session
from src.models.event import ProcessedEvent
from src.models.moderation_card import ModerationCard
from src.schemas.event import IncomingB2BEvent, ProductEventType
from datetime import datetime, timezone
import uuid


class DuplicateEventError(Exception):
    """Выбрасывается при повторном событии с тем же idempotency_key."""
    def __init__(self, idempotency_key: str, product_id: str):
        self.idempotency_key = idempotency_key
        self.product_id = product_id
        super().__init__(f"Duplicate event: {idempotency_key}")


class EventService:
    def __init__(self, db: Session):
        self.db = db

    def process_event(self, event: IncomingB2BEvent) -> dict:
        """
        Обработка входящего события от B2B.
        
        1. Проверка идемпотентности по idempotency_key → 409 при дубликате
        2. Маршрутизация по event_type
        3. Сохранение idempotency_key после успешной обработки
        """
        # Дедупликация по idempotency_key (не по product_id!)
        existing = self.db.query(ProcessedEvent).filter(
            ProcessedEvent.idempotency_key == event.idempotency_key
        ).first()
        
        if existing:
            raise DuplicateEventError(
                idempotency_key=event.idempotency_key,
                product_id=existing.product_id
            )
        
        product_id = event.payload.product_id
        seller_id = event.payload.seller_id
        
        # Маршрутизация по типу события
        if event.event_type == ProductEventType.PRODUCT_CREATED:
            self._handle_created(product_id, seller_id, event)
        elif event.event_type == ProductEventType.PRODUCT_EDITED:
            self._handle_edited(product_id, seller_id, event)
        elif event.event_type == ProductEventType.PRODUCT_DELETED:
            self._handle_deleted(product_id, event)
        
        # Сохраняем idempotency_key ПОСЛЕ успешной обработки
        processed = ProcessedEvent(
            idempotency_key=event.idempotency_key,
            product_id=product_id,
            event_type=event.event_type.value,
            processed_at=datetime.now(timezone.utc)
        )
        self.db.add(processed)
        self.db.commit()
        
        return {
            "status": "accepted",
            "idempotency_key": event.idempotency_key,
            "product_id": product_id,
        }

    def _handle_created(self, product_id: str, seller_id: str, event: IncomingB2BEvent):
        """
        CREATED: создаём карточку модерации в статусе PENDING.
        """
        existing = self.db.query(ModerationCard).filter(
            ModerationCard.product_id == product_id
        ).first()
        
        product_data = event.payload.product_data or {}
        now = datetime.now(timezone.utc)
        
        if existing:
            existing.status = "PENDING"
            existing.seller_id = seller_id or existing.seller_id
            existing.json_before = None
            existing.json_after = product_data
            existing.queue_priority = 1
            existing.date_updated = now
        else:
            card = ModerationCard(
                id=str(uuid.uuid4()),
                product_id=product_id,
                seller_id=seller_id or "unknown",
                status="PENDING",
                queue_priority=1,
                json_before=None,
                json_after=product_data,
                blocking_reason_id=None,
                moderator_id=None,
                moderator_comment=None,
                date_created=now,
                date_updated=now,
                date_moderation=None,
            )
            self.db.add(card)

    def _handle_edited(self, product_id: str, seller_id: str, event: IncomingB2BEvent):
        """
        EDITED: обновляем карточку.
        
        - json_before ← json_after (предыдущий снапшот)
        - json_after ← новые данные
        - статус:
          * MODERATED/BLOCKED → возвращается в PENDING
          * IN_REVIEW → обновляются поля, остаётся в IN_REVIEW
          * HARD_BLOCKED → игнорируется (терминальный статус)
        """
        card = self.db.query(ModerationCard).filter(
            ModerationCard.product_id == product_id
        ).first()
        
        if not card:
            return
        
        if card.status == "HARD_BLOCKED":
            return
        
        product_data = event.payload.product_data or {}
        now = datetime.now(timezone.utc)
        
        card.json_before = card.json_after
        card.json_after = product_data
        card.date_updated = now
        
        if card.status in ("MODERATED", "BLOCKED"):
            card.status = "PENDING"
            card.queue_priority = 1
            card.moderator_id = None
            card.moderator_comment = None
            card.date_moderation = None
        elif card.status == "IN_REVIEW":
            pass
        elif card.status == "PENDING":
            pass

    def _handle_deleted(self, product_id: str, event: IncomingB2BEvent):
        """
        DELETED: удаляем карточку из очереди модерации.
        """
        card = self.db.query(ModerationCard).filter(
            ModerationCard.product_id == product_id
        ).first()
        
        if card:
            self.db.delete(card)