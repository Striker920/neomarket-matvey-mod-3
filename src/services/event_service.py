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
        # Дедупликация по idempotency_key
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
        ✅ json_after берём из payload (не product_data)
        """
        existing = self.db.query(ModerationCard).filter(
            ModerationCard.product_id == product_id
        ).first()
        
        # ✅ ИСПРАВЛЕНО: json_after вместо product_data
        json_after = event.payload.json_after or {}
        now = datetime.now(timezone.utc)
        
        if existing:
            existing.status = "PENDING"
            existing.seller_id = seller_id or existing.seller_id
            existing.json_before = None
            existing.json_after = json_after
            existing.queue_priority = 1
            existing.moderator_id = None
            existing.moderator_comment = None
            existing.date_moderation = None
            existing.date_updated = now
        else:
            card = ModerationCard(
                id=str(uuid.uuid4()),
                product_id=product_id,
                seller_id=seller_id or "unknown",
                status="PENDING",
                queue_priority=1,
                json_before=None,
                json_after=json_after,
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
        
        ✅ json_before и json_after берём из payload (а не вычисляем из текущего состояния)
        Статус:
          * APPROVED/BLOCKED → сброс в PENDING (возврат в очередь)
          * IN_REVIEW → сброс в PENDING + обнуление moderator_id (по канону)
          * PENDING → просто обновляем поля
          * HARD_BLOCKED → игнорируем (терминальный статус)
        """
        card = self.db.query(ModerationCard).filter(
            ModerationCard.product_id == product_id
        ).first()
        
        if not card:
            return
        
        # HARD_BLOCKED — терминальный статус, игнорируем EDITED
        if card.status == "HARD_BLOCKED":
            return
        
        # ✅ ИСПРАВЛЕНО: берём json_before/json_after из payload
        now = datetime.now(timezone.utc)
        card.json_before = event.payload.json_before  # может быть None
        card.json_after = event.payload.json_after or {}
        card.seller_id = seller_id or card.seller_id
        card.date_updated = now
        
        # ✅ ИСПРАВЛЕНО: 'APPROVED' вместо 'MODERATED' (согласно TicketStatus enum)
        # APPROVED/BLOCKED → сброс в PENDING (возврат в очередь)
        if card.status in ('APPROVED', 'BLOCKED'):
            card.status = "PENDING"
            card.queue_priority = 1
            card.moderator_id = None
            card.moderator_comment = None
            card.date_moderation = None
        
        # ✅ ИСПРАВЛЕНО: IN_REVIEW → сброс в PENDING + обнуление moderator_id
        # Канон (moderation-flows.md:1027) явно требует это — иначе у модератора устаревшие данные
        elif card.status == "IN_REVIEW":
            card.status = "PENDING"
            card.queue_priority = 1
            card.moderator_id = None
            card.moderator_comment = None
            card.date_moderation = None
        
        # PENDING — просто обновляем поля (статус не меняем)
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