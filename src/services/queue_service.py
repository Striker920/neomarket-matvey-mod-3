from sqlalchemy.orm import Session
from sqlalchemy import and_, or_
from src.models.moderation_card import ModerationCard
from typing import Optional
import logging

logger = logging.getLogger(__name__)


class QueueService:
    def __init__(self, db: Session):
        self.db = db

    def claim_card(
        self,
        moderator_id: str,
        queue_priority: Optional[int] = None
    ) -> Optional[ModerationCard]:
        """
        Получить следующую карточку из очереди.
        
        Логика:
        1. Проверить, нет ли у модератора уже активной IN_REVIEW → 409
        2. Найти самую старую PENDING карточку
        3. Если queue_priority указан — искать только в этой очереди
        4. Если queue_priority = null — автоперебор 1→4
        5. Перевести в IN_REVIEW, закрепить за модератором
        
        Защита от race-conditions:
        - SQLite: BEGIN IMMEDIATE транзакция (в database.py)
        - PostgreSQL: SELECT ... FOR UPDATE SKIP LOCKED
        """
        # 1. Проверка: у модератора не должно быть активной IN_REVIEW
        existing_review = self.db.query(ModerationCard).filter(
            and_(
                ModerationCard.moderator_id == moderator_id,
                ModerationCard.status == "IN_REVIEW"
            )
        ).first()
        
        if existing_review:
            raise ValueError(f"Moderator {moderator_id} already has IN_REVIEW card")
        
        # 2. Найти самую старую PENDING карточку
        if queue_priority is not None:
            # Ищем в конкретной очереди
            card = self._find_oldest_pending(queue_priority)
        else:
            # Автоперебор очередей 1→4
            card = None
            for priority in [1, 2, 3, 4]:
                card = self._find_oldest_pending(priority)
                if card:
                    break
        
        if not card:
            return None
        
        # 3. Переводим в IN_REVIEW и закрепляем за модератором
        card.status = "IN_REVIEW"
        card.moderator_id = moderator_id
        self.db.commit()
        self.db.refresh(card)
        
        logger.info(f"Card {card.id} claimed by moderator {moderator_id}")
        return card

    def _find_oldest_pending(self, queue_priority: int) -> Optional[ModerationCard]:
        """
        Найти самую старую PENDING карточку в указанной очереди.
        
        Для PostgreSQL используется FOR UPDATE SKIP LOCKED (реализовано в postgres_database.py).
        Для SQLite используется BEGIN IMMEDIATE транзакция.
        """
        # Проверяем, используется ли PostgreSQL
        if self._is_postgres():
            return self._find_oldest_pending_postgres(queue_priority)
        else:
            return self._find_oldest_pending_sqlite(queue_priority)

    def _find_oldest_pending_sqlite(self, queue_priority: int) -> Optional[ModerationCard]:
        """SQLite: обычная выборка с блокировкой на уровне транзакции."""
        return self.db.query(ModerationCard).filter(
            and_(
                ModerationCard.status == "PENDING",
                ModerationCard.queue_priority == queue_priority
            )
        ).order_by(ModerationCard.date_updated.asc()).first()

    def _find_oldest_pending_postgres(self, queue_priority: int) -> Optional[ModerationCard]:
        """PostgreSQL: SELECT ... FOR UPDATE SKIP LOCKED."""
        from sqlalchemy import text
        
        # Используем raw SQL для FOR UPDATE SKIP LOCKED
        query = text("""
            SELECT id FROM moderation_cards
            WHERE status = 'PENDING' AND queue_priority = :priority
            ORDER BY date_updated ASC
            LIMIT 1
            FOR UPDATE SKIP LOCKED
        """)
        
        result = self.db.execute(query, {"priority": queue_priority}).fetchone()
        
        if not result:
            return None
        
        card_id = result[0]
        return self.db.query(ModerationCard).filter(ModerationCard.id == card_id).first()

    def _is_postgres(self) -> bool:
        """Проверить, используется ли PostgreSQL."""
        return "postgresql" in str(self.db.bind.url).lower()