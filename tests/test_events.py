import pytest
from datetime import datetime, timezone
from uuid import uuid4
from src.models.moderation_card import ModerationCard
from src.models.event import ProcessedEvent


def _make_event(
    event_type: str,
    product_id: str,
    seller_id: str = "seller-1",
    idempotency_key: str = None,
    product_data: dict = None,
) -> dict:
    """Хелпер для создания тестового события."""
    return {
        "event_type": event_type,
        "idempotency_key": idempotency_key or str(uuid4()),
        "occurred_at": datetime.now(timezone.utc).isoformat(),
        "payload": {
            "product_id": product_id,
            "seller_id": seller_id,
            "product_data": product_data or {"title": "Test Product"},
        }
    }


class TestProductEvents:

    def test_created_pending(self, client, db_session, valid_service_headers):
        """Событие CREATED создаёт карточку в PENDING."""
        product_id = str(uuid4())
        idem_key = str(uuid4())
        
        response = client.post(
            "/api/v1/b2b/events",
            json=_make_event("PRODUCT_CREATED", product_id, idempotency_key=idem_key),
            headers=valid_service_headers,
        )
        
        assert response.status_code == 202
        data = response.json()
        assert data["status"] == "accepted"
        assert data["idempotency_key"] == idem_key
        assert data["product_id"] == product_id
        
        card = db_session.query(ModerationCard).filter(
            ModerationCard.product_id == product_id
        ).first()
        assert card is not None
        assert card.status == "PENDING"
        assert card.json_after is not None
        assert card.queue_priority == 1

    def test_edited_returns_to_review(self, client, db_session, valid_service_headers):
        """EDITED после MODERATED возвращает карточку в PENDING (в очередь)."""
        product_id = str(uuid4())
        
        card = ModerationCard(
            id=str(uuid4()),
            product_id=product_id,
            seller_id="seller-1",
            status="MODERATED",
            queue_priority=5,
            json_before=None,
            json_after={"title": "Old Title"},
            date_created=datetime.now(timezone.utc),
            date_updated=datetime.now(timezone.utc),
        )
        db_session.add(card)
        db_session.commit()
        
        response = client.post(
            "/api/v1/b2b/events",
            json=_make_event(
                "PRODUCT_EDITED",
                product_id,
                product_data={"title": "New Title"},
            ),
            headers=valid_service_headers,
        )
        
        assert response.status_code == 202
        
        db_session.refresh(card)
        assert card.status == "PENDING"
        assert card.json_before == {"title": "Old Title"}
        assert card.json_after == {"title": "New Title"}
        assert card.queue_priority == 1

    def test_edited_updates_in_review(self, client, db_session, valid_service_headers):
        """EDITED во время IN_REVIEW обновляет поля, но статус остаётся IN_REVIEW."""
        product_id = str(uuid4())
        
        card = ModerationCard(
            id=str(uuid4()),
            product_id=product_id,
            seller_id="seller-1",
            status="IN_REVIEW",
            queue_priority=1,
            json_before=None,
            json_after={"title": "Old Title"},
            moderator_id="moderator-1",
            date_created=datetime.now(timezone.utc),
            date_updated=datetime.now(timezone.utc),
        )
        db_session.add(card)
        db_session.commit()
        
        response = client.post(
            "/api/v1/b2b/events",
            json=_make_event(
                "PRODUCT_EDITED",
                product_id,
                product_data={"title": "Updated Title"},
            ),
            headers=valid_service_headers,
        )
        
        assert response.status_code == 202
        
        db_session.refresh(card)
        assert card.status == "IN_REVIEW"
        assert card.moderator_id == "moderator-1"
        assert card.json_before == {"title": "Old Title"}
        assert card.json_after == {"title": "Updated Title"}

    def test_deleted_archived(self, client, db_session, valid_service_headers):
        """DELETED удаляет карточку из очереди."""
        product_id = str(uuid4())
        
        card = ModerationCard(
            id=str(uuid4()),
            product_id=product_id,
            seller_id="seller-1",
            status="PENDING",
            queue_priority=1,
            json_before=None,
            json_after={"title": "Test"},
            date_created=datetime.now(timezone.utc),
            date_updated=datetime.now(timezone.utc),
        )
        db_session.add(card)
        db_session.commit()
        
        response = client.post(
            "/api/v1/b2b/events",
            json=_make_event("PRODUCT_DELETED", product_id),
            headers=valid_service_headers,
        )
        
        assert response.status_code == 202
        
        deleted_card = db_session.query(ModerationCard).filter(
            ModerationCard.product_id == product_id
        ).first()
        assert deleted_card is None

    def test_duplicate_event_no_side_effects(self, client, db_session, valid_service_headers):
        """
        Повторное событие с тем же idempotency_key → 409 без побочных эффектов.
        """
        product_id = str(uuid4())
        idem_key = str(uuid4())
        
        response1 = client.post(
            "/api/v1/b2b/events",
            json=_make_event("PRODUCT_CREATED", product_id, idempotency_key=idem_key),
            headers=valid_service_headers,
        )
        assert response1.status_code == 202
        
        processed = db_session.query(ProcessedEvent).filter(
            ProcessedEvent.idempotency_key == idem_key
        ).first()
        assert processed is not None
        
        response2 = client.post(
            "/api/v1/b2b/events",
            json=_make_event("PRODUCT_CREATED", product_id, idempotency_key=idem_key),
            headers=valid_service_headers,
        )
        assert response2.status_code == 409
        data = response2.json()
        # ✅ Адаптировано под формат ответа (без 'detail')
        assert data["code"] == "DUPLICATE_EVENT"
        
        cards = db_session.query(ModerationCard).filter(
            ModerationCard.product_id == product_id
        ).all()
        assert len(cards) == 1

    def test_missing_service_header_401(self, client):
        """Запрос без X-Service-Key → 401."""
        product_id = str(uuid4())
        
        response = client.post(
            "/api/v1/b2b/events",
            json=_make_event("PRODUCT_CREATED", product_id),
        )
        
        assert response.status_code == 401
        data = response.json()
        # ✅ Адаптировано под формат ответа (без 'detail')
        assert data["code"] == "UNAUTHORIZED"

    def test_invalid_service_key_401(self, client):
        """Неверный X-Service-Key → 401."""
        product_id = str(uuid4())
        
        response = client.post(
            "/api/v1/b2b/events",
            json=_make_event("PRODUCT_CREATED", product_id),
            headers={"X-Service-Key": "wrong-key"},
        )
        
        assert response.status_code == 401
        data = response.json()
        # ✅ Адаптировано под формат ответа (без 'detail')
        assert data["code"] == "UNAUTHORIZED"