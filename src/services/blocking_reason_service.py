from sqlalchemy.orm import Session
from src.models.blocking_reason import BlockingReason
from src.models.moderation_card import ModerationCard
from src.schemas.blocking_reason import (
    BlockingReasonCreateRequest,
    BlockingReasonUpdateRequest,
)
from uuid import uuid4
from datetime import datetime, timezone


class ReferencedReasonError(Exception):
    """Выбрасывается при попытке удалить причину, на которую ссылаются карточки."""
    def __init__(self, reason_id: str, cards_count: int):
        self.reason_id = reason_id
        self.cards_count = cards_count
        super().__init__(
            f"Cannot delete reason {reason_id}: referenced by {cards_count} moderation cards"
        )


class BlockingReasonService:
    def __init__(self, db: Session):
        self.db = db

    def list_active(self) -> list[BlockingReason]:
        """
        Получить список активных причин блокировки.
        
        Возвращает только is_active=True.
        Используется в публичном API (GET /product-blocking-reasons).
        """
        return self.db.query(BlockingReason).filter(
            BlockingReason.is_active == True
        ).order_by(BlockingReason.title).all()

    def list_all(self, include_inactive: bool = False) -> list[BlockingReason]:
        """Получить список всех причин (для админки)."""
        query = self.db.query(BlockingReason)
        if not include_inactive:
            query = query.filter(BlockingReason.is_active == True)
        return query.order_by(BlockingReason.title).all()

    def get_by_id(self, reason_id: str) -> BlockingReason | None:
        """Получить причину по ID."""
        return self.db.query(BlockingReason).filter(
            BlockingReason.id == reason_id
        ).first()

    def create(self, data: BlockingReasonCreateRequest) -> BlockingReason:
        """Создать новую причину блокировки."""
        now = datetime.now(timezone.utc)
        reason = BlockingReason(
            id=str(uuid4()),
            title=data.title,
            description=data.description,
            hard_block=data.hard_block,
            is_active=True,
            created_at=now,
            updated_at=now,
        )
        self.db.add(reason)
        self.db.commit()
        self.db.refresh(reason)
        return reason

    def update(self, reason_id: str, data: BlockingReasonUpdateRequest) -> BlockingReason | None:
        """Обновить причину блокировки."""
        reason = self.get_by_id(reason_id)
        if not reason:
            return None
        
        if data.title is not None:
            reason.title = data.title
        if data.description is not None:
            reason.description = data.description
        if data.hard_block is not None:
            reason.hard_block = data.hard_block
        if data.is_active is not None:
            reason.is_active = data.is_active
        
        reason.updated_at = datetime.now(timezone.utc)
        self.db.commit()
        self.db.refresh(reason)
        return reason

    def delete(self, reason_id: str) -> bool:
        """
        Удалить причину блокировки (мягкая деактивация).
        
        Если на причину ссылаются карточки модерации — выбрасывает ReferencedReasonError.
        Иначе — мягкая деактивация (is_active=False).
        """
        reason = self.get_by_id(reason_id)
        if not reason:
            return False
        
        # Проверяем, есть ли ссылки из карточек модерации
        cards_count = self.db.query(ModerationCard).filter(
            ModerationCard.blocking_reason_id == reason_id
        ).count()
        
        if cards_count > 0:
            raise ReferencedReasonError(reason_id, cards_count)
        
        # Мягкая деактивация
        reason.is_active = False
        reason.updated_at = datetime.now(timezone.utc)
        self.db.commit()
        return True