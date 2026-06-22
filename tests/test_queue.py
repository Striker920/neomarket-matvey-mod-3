import pytest
from datetime import datetime, timezone, timedelta
from uuid import uuid4
from src.models.moderation_card import ModerationCard


def _create_pending_card(
    db_session,
    product_id: str = None,
    seller_id: str = "seller-1",
    queue_priority: int = 1,
    date_updated: datetime = None,
) -> ModerationCard:
    """Хелпер для создания тестовой карточки."""
    card = ModerationCard(
        id=str(uuid4()),
        product_id=product_id or str(uuid4()),
        seller_id=seller_id,
        status="PENDING",
        queue_priority=queue_priority,
        json_before=None,
        json_after={"title": "Test Product"},
        date_created=date_updated or datetime.now(timezone.utc),
        date_updated=date_updated or datetime.now(timezone.utc),
    )
    db_session.add(card)
    db_session.commit()
    return card


class TestQueueClaim:

    def test_next_returns_oldest_pending(self, client, db_session):
        """Happy path: самая старая PENDING → IN_REVIEW, закреплена за модератором."""
        moderator_id = str(uuid4())
        
        old_card = _create_pending_card(
            db_session,
            date_updated=datetime.now(timezone.utc) - timedelta(hours=2)
        )
        middle_card = _create_pending_card(
            db_session,
            date_updated=datetime.now(timezone.utc) - timedelta(hours=1)
        )
        new_card = _create_pending_card(
            db_session,
            date_updated=datetime.now(timezone.utc)
        )
        
        response = client.post(
            "/api/v1/queue/claim",
            headers={"X-Moderator-Id": moderator_id}
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["id"] == old_card.id
        assert data["status"] == "IN_REVIEW"
        assert data["moderator_id"] == moderator_id
        
        db_session.refresh(old_card)
        assert old_card.status == "IN_REVIEW"
        assert old_card.moderator_id == moderator_id

    def test_concurrent_two_moderators_get_different_cards(self, client, db_session):
        """Два модератора получают разные карточки."""
        moderator_1 = str(uuid4())
        moderator_2 = str(uuid4())
        
        card_1 = _create_pending_card(db_session)
        card_2 = _create_pending_card(db_session)
        
        response_1 = client.post(
            "/api/v1/queue/claim",
            headers={"X-Moderator-Id": moderator_1}
        )
        assert response_1.status_code == 200
        claimed_1 = response_1.json()["id"]
        
        response_2 = client.post(
            "/api/v1/queue/claim",
            headers={"X-Moderator-Id": moderator_2}
        )
        assert response_2.status_code == 200
        claimed_2 = response_2.json()["id"]
        
        # ✅ Карточки должны быть разными и из созданных в этом тесте
        assert claimed_1 != claimed_2
        assert claimed_1 in [card_1.id, card_2.id]
        assert claimed_2 in [card_1.id, card_2.id]

    def test_empty_queue_returns_204(self, client, db_session):
        """Пустая очередь → 204 No Content."""
        moderator_id = str(uuid4())
        
        response = client.post(
            "/api/v1/queue/claim",
            headers={"X-Moderator-Id": moderator_id}
        )
        
        assert response.status_code == 204
        assert response.content == b""

    def test_moderator_already_has_in_review_returns_409(self, client, db_session):
        """Попытка взять вторую карточку с активной IN_REVIEW → 409."""
        moderator_id = str(uuid4())
        
        card = _create_pending_card(db_session)
        card.status = "IN_REVIEW"
        card.moderator_id = moderator_id
        db_session.commit()
        
        _create_pending_card(db_session)
        
        response = client.post(
            "/api/v1/queue/claim",
            headers={"X-Moderator-Id": moderator_id}
        )
        
        assert response.status_code == 409
        data = response.json()
        # ✅ Адаптировано под формат ответа (без 'detail')
        assert data["code"] == "CONFLICT"
        assert "already has IN_REVIEW" in data["message"]

    def test_queue_priority_filter(self, client, db_session):
        """Параметр queue_priority фильтрует очереди."""
        moderator_id = str(uuid4())
        
        card_q1 = _create_pending_card(db_session, queue_priority=1)
        card_q2 = _create_pending_card(db_session, queue_priority=2)
        card_q3 = _create_pending_card(db_session, queue_priority=3)
        
        response = client.post(
            "/api/v1/queue/claim",
            headers={"X-Moderator-Id": moderator_id},
            json={"queue_priority": 2}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == card_q2.id
        assert data["queue_priority"] == 2

    def test_auto_priority_scans_queues_1_to_4(self, client, db_session):
        """Автоприоритизация: перебор очередей 1→4."""
        moderator_id = str(uuid4())
        
        card_q3 = _create_pending_card(db_session, queue_priority=3)
        
        response = client.post(
            "/api/v1/queue/claim",
            headers={"X-Moderator-Id": moderator_id}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == card_q3.id
        assert data["queue_priority"] == 3

    def test_missing_moderator_id_returns_401(self, client):
        """Отсутствие заголовка X-Moderator-Id → 401."""
        response = client.post("/api/v1/queue/claim")
        
        assert response.status_code == 401
        data = response.json()
        # ✅ Адаптировано под формат ответа (без 'detail')
        assert data["code"] == "UNAUTHORIZED"

    def test_invalid_queue_priority_returns_422(self, client):
        """Невалидный queue_priority → 422."""
        moderator_id = str(uuid4())
        
        response = client.post(
            "/api/v1/queue/claim",
            headers={"X-Moderator-Id": moderator_id},
            json={"queue_priority": 5}
        )
        
        assert response.status_code == 422