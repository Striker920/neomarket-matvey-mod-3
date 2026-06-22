import pytest
from uuid import uuid4
from datetime import datetime, timezone
from src.models.blocking_reason import BlockingReason
from src.models.moderation_card import ModerationCard


def _create_reason(
    db_session,
    title: str = None,
    hard_block: bool = False,
    is_active: bool = True,
) -> BlockingReason:
    """Хелпер для создания тестовой причины блокировки."""
    reason = BlockingReason(
        id=str(uuid4()),
        title=title or f"Reason {uuid4()}",
        hard_block=hard_block,
        is_active=is_active,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db_session.add(reason)
    db_session.commit()
    return reason


class TestBlockingReasons:

    def test_list_returns_active_reasons(self, client, db_session):
        """Happy path: возвращает только активные причины."""
        active_1 = _create_reason(db_session, title="Photo mismatch", hard_block=False)
        active_2 = _create_reason(db_session, title="Wrong category", hard_block=True)
        inactive = _create_reason(db_session, title="Old reason", is_active=False)
        
        response = client.get("/api/v1/product-blocking-reasons")
        
        assert response.status_code == 200
        data = response.json()
        
        # Должно быть 2 активных причины
        assert len(data) == 2
        
        ids = [item["id"] for item in data]
        assert active_1.id in ids
        assert active_2.id in ids
        assert inactive.id not in ids
        
        # Проверяем структуру ответа
        for item in data:
            assert "id" in item
            assert "title" in item
            assert "hard_block" in item
            assert "is_active" in item
            assert item["is_active"] == True

    def test_inactive_reasons_not_visible(self, client, db_session):
        """Деактивированные причины не отдаются API."""
        inactive = _create_reason(db_session, title="Hidden reason", is_active=False)
        
        response = client.get("/api/v1/product-blocking-reasons")
        
        assert response.status_code == 200
        data = response.json()
        
        # Список должен быть пустым
        assert len(data) == 0
        
        # Проверяем, что причина действительно есть в БД
        all_reasons = db_session.query(BlockingReason).all()
        assert len(all_reasons) == 1
        assert all_reasons[0].id == inactive.id

    def test_referenced_reason_cannot_be_deleted(self, client, db_session):
        """Попытка удалить причину, на которую ссылается карточка → 409."""
        reason = _create_reason(db_session, title="Referenced reason")
        
        # Создаём карточку модерации, ссылающуюся на эту причину
        card = ModerationCard(
            id=str(uuid4()),
            product_id=str(uuid4()),
            seller_id="seller-1",
            status="BLOCKED",
            queue_priority=1,
            json_before=None,
            json_after={"title": "Test"},
            blocking_reason_id=reason.id,
            moderator_id=str(uuid4()),
            date_created=datetime.now(timezone.utc),
            date_updated=datetime.now(timezone.utc),
        )
        db_session.add(card)
        db_session.commit()
        
        # Пытаемся удалить причину
        response = client.delete(f"/api/v1/product-blocking-reasons/{reason.id}")
        
        assert response.status_code == 409
        data = response.json()
        # ✅ Адаптировано под кастомный обработчик (без 'detail')
        assert data["code"] == "REFERENCED"
        assert data["cards_count"] == 1
        
        # Причина всё ещё активна
        db_session.refresh(reason)
        assert reason.is_active == True

    def test_unreferenced_reason_can_be_deactivated(self, client, db_session):
        """Причина без ссылок может быть деактивирована."""
        reason = _create_reason(db_session, title="Unused reason")
        
        response = client.delete(f"/api/v1/product-blocking-reasons/{reason.id}")
        
        # 204 No Content — успешная деактивация
        assert response.status_code == 204
        
        # Причина деактивирована (не удалена физически)
        db_session.refresh(reason)
        assert reason.is_active == False
        
        # Больше не возвращается в списке
        list_response = client.get("/api/v1/product-blocking-reasons")
        assert reason.id not in [item["id"] for item in list_response.json()]

    def test_create_reason(self, client, db_session):
        """Создание новой причины блокировки."""
        response = client.post(
            "/api/v1/product-blocking-reasons",
            json={
                "title": "New reason",
                "hard_block": True,
            }
        )
        
        assert response.status_code == 201
        data = response.json()
        assert data["title"] == "New reason"
        assert data["hard_block"] == True
        assert data["is_active"] == True
        assert "id" in data

    def test_hard_block_filter(self, client, db_session):
        """Причины имеют флаг hard_block для разделения MOD-04/MOD-05."""
        soft_reason = _create_reason(db_session, title="Soft reason", hard_block=False)
        hard_reason = _create_reason(db_session, title="Hard reason", hard_block=True)
        
        response = client.get("/api/v1/product-blocking-reasons")
        
        assert response.status_code == 200
        data = response.json()
        
        soft_item = next(item for item in data if item["id"] == soft_reason.id)
        hard_item = next(item for item in data if item["id"] == hard_reason.id)
        
        assert soft_item["hard_block"] == False
        assert hard_item["hard_block"] == True