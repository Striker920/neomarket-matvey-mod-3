import pytest
from datetime import datetime, timezone
from uuid import uuid4
from src.models.moderation_card import ModerationCard
from src.models.event import ProcessedEvent


# ============================================================
# Helper: создание тестового события
# ============================================================
def _make_event(
    event_type: str,
    product_id: str,
    seller_id: str = "seller-1",
    idempotency_key: str = None,
    json_after: dict = None,
    json_before: dict = None,
) -> dict:
    """
    Хелпер для создания тестового события.
    ✅ Использует json_after/json_before вместо product_data (по спецификации).
    """
    return {
        "event_type": event_type,
        "idempotency_key": idempotency_key or str(uuid4()),
        "occurred_at": datetime.now(timezone.utc).isoformat(),
        "payload": {
            "product_id": product_id,
            "seller_id": seller_id,
            "json_after": json_after or {"title": "Test Product", "price": 100},
            "json_before": json_before,  # может быть None
        }
    }


# ============================================================
# Тесты
# ============================================================
class TestProductEvents:
    """
    Покрытие сценариев канона flows/moderation-flows.md#receive-product-events:
    - created_pending
    - edited_returns_to_review
    - edited_updates_in_review
    - deleted_archived
    - duplicate_event_no_side_effects
    - missing_service_header_401
    """

    # --------------------------------------------------------
    # 1. created_pending — CREATED создаёт карточку в PENDING
    # --------------------------------------------------------
    def test_created_pending(self, client, db_session, valid_service_headers):
        """Событие CREATED создаёт карточку в статусе PENDING."""
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
        
        # Проверяем карточку в БД
        card = db_session.query(ModerationCard).filter(
            ModerationCard.product_id == product_id
        ).first()
        assert card is not None
        assert card.status == "PENDING"
        assert card.json_after == {"title": "Test Product", "price": 100}
        assert card.json_before is None
        assert card.seller_id == "seller-1"
        
        # Проверяем запись об идемпотентности
        processed = db_session.query(ProcessedEvent).filter(
            ProcessedEvent.idempotency_key == idem_key
        ).first()
        assert processed is not None
        assert processed.product_id == product_id

    # --------------------------------------------------------
    # 2. edited_returns_to_review — EDITED после APPROVED/BLOCKED
    #    возвращает карточку в очередь (PENDING)
    # --------------------------------------------------------
    def test_edited_returns_to_review(self, client, db_session, valid_service_headers):
        """EDITED после APPROVED возвращает карточку в PENDING."""
        product_id = str(uuid4())
        
        # 1. Создаём карточку через CREATED
        client.post(
            "/api/v1/b2b/events",
            json=_make_event("PRODUCT_CREATED", product_id),
            headers=valid_service_headers,
        )
        
        # 2. Вручную переводим в APPROVED (эмуляция модерации)
        card = db_session.query(ModerationCard).filter(
            ModerationCard.product_id == product_id
        ).first()
        card.status = "APPROVED"
        card.moderator_id = "moderator-1"
        card.moderator_comment = "Looks good"
        db_session.commit()
        
        # 3. Отправляем EDITED
        response = client.post(
            "/api/v1/b2b/events",
            json=_make_event(
                "PRODUCT_EDITED",
                product_id,
                json_before={"title": "Old Title"},
                json_after={"title": "New Title", "price": 200},
            ),
            headers=valid_service_headers,
        )
        
        assert response.status_code == 202
        
        # 4. Проверяем: статус сброшен в PENDING, модератор обнулён
        db_session.refresh(card)
        assert card.status == "PENDING"
        assert card.moderator_id is None
        assert card.moderator_comment is None
        assert card.json_after == {"title": "New Title", "price": 200}
        assert card.json_before == {"title": "Old Title"}

    # --------------------------------------------------------
    # 3. edited_updates_in_review — EDITED во время IN_REVIEW
    #    сбрасывает карточку в PENDING + обнуляет moderator_id
    # --------------------------------------------------------
    def test_edited_updates_in_review(self, client, db_session, valid_service_headers):
        """EDITED во время IN_REVIEW сбрасывает в PENDING и обнуляет moderator_id."""
        product_id = str(uuid4())
        
        # 1. Создаём карточку
        client.post(
            "/api/v1/b2b/events",
            json=_make_event("PRODUCT_CREATED", product_id),
            headers=valid_service_headers,
        )
        
        # 2. Переводим в IN_REVIEW (эмуляция взятия модератором)
        card = db_session.query(ModerationCard).filter(
            ModerationCard.product_id == product_id
        ).first()
        card.status = "IN_REVIEW"
        card.moderator_id = "moderator-2"
        db_session.commit()
        
        # 3. Отправляем EDITED
        response = client.post(
            "/api/v1/b2b/events",
            json=_make_event(
                "PRODUCT_EDITED",
                product_id,
                json_before={"title": "Old"},
                json_after={"title": "Updated", "price": 300},
            ),
            headers=valid_service_headers,
        )
        
        assert response.status_code == 202
        
        # 4. Проверяем: сброшен в PENDING, модератор обнулён
        db_session.refresh(card)
        assert card.status == "PENDING"
        assert card.moderator_id is None
        assert card.json_after == {"title": "Updated", "price": 300}
        assert card.json_before == {"title": "Old"}

    # --------------------------------------------------------
    # 4. deleted_archived — DELETED удаляет карточку из очереди
    # --------------------------------------------------------
    def test_deleted_archived(self, client, db_session, valid_service_headers):
        """Событие DELETED удаляет карточку из очереди модерации."""
        product_id = str(uuid4())
        
        # 1. Создаём карточку
        client.post(
            "/api/v1/b2b/events",
            json=_make_event("PRODUCT_CREATED", product_id),
            headers=valid_service_headers,
        )
        
        # Проверяем, что карточка создана
        card = db_session.query(ModerationCard).filter(
            ModerationCard.product_id == product_id
        ).first()
        assert card is not None
        
        # 2. Отправляем DELETED
        response = client.post(
            "/api/v1/b2b/events",
            json=_make_event("PRODUCT_DELETED", product_id),
            headers=valid_service_headers,
        )
        
        assert response.status_code == 202
        
        # 3. Проверяем: карточка удалена
        card = db_session.query(ModerationCard).filter(
            ModerationCard.product_id == product_id
        ).first()
        assert card is None

    # --------------------------------------------------------
    # 5. duplicate_event_no_side_effects — повторное событие
    #    с тем же idempotency_key → 409 без побочных эффектов
    # --------------------------------------------------------
    def test_duplicate_event_no_side_effects(self, client, db_session, valid_service_headers):
        """Повторное событие с тем же idempotency_key возвращает 409."""
        product_id = str(uuid4())
        idem_key = str(uuid4())
        
        # 1. Первое событие
        response1 = client.post(
            "/api/v1/b2b/events",
            json=_make_event("PRODUCT_CREATED", product_id, idempotency_key=idem_key),
            headers=valid_service_headers,
        )
        assert response1.status_code == 202
        
        # Считаем количество карточек
        count_before = db_session.query(ModerationCard).filter(
            ModerationCard.product_id == product_id
        ).count()
        
        # 2. Повторное событие с тем же idempotency_key
        response2 = client.post(
            "/api/v1/b2b/events",
            json=_make_event("PRODUCT_CREATED", product_id, idempotency_key=idem_key),
            headers=valid_service_headers,
        )
        
        # 3. Проверяем: 409 Conflict
        assert response2.status_code == 409
        data = response2.json()
        # ✅ ИСПРАВЛЕНО: кастомный handler возвращает JSON напрямую (без обёртки "detail")
        assert data["code"] == "DUPLICATE_EVENT"
        assert data["idempotency_key"] == idem_key
        
        # 4. Проверяем: никаких побочных эффектов (карточка та же самая)
        count_after = db_session.query(ModerationCard).filter(
            ModerationCard.product_id == product_id
        ).count()
        assert count_after == count_before

    # --------------------------------------------------------
    # 6. missing_service_header_401 — запрос без заголовка
    #    X-Service-Key → 401 Unauthorized
    # --------------------------------------------------------
    def test_missing_service_header_401(self, client, db_session):
        """Запрос без межсервисного заголовка возвращает 401."""
        product_id = str(uuid4())
        
        response = client.post(
            "/api/v1/b2b/events",
            json=_make_event("PRODUCT_CREATED", product_id),
            # ❌ Без заголовка X-Service-Key
        )
        
        assert response.status_code == 401
        data = response.json()
        # ✅ ИСПРАВЛЕНО: кастомный handler возвращает JSON напрямую
        assert data["code"] == "UNAUTHORIZED"
        
        # Проверяем, что карточка НЕ создана
        card = db_session.query(ModerationCard).filter(
            ModerationCard.product_id == product_id
        ).first()
        assert card is None

    # --------------------------------------------------------
    # 7. wrong_service_header_401 — неверный X-Service-Key → 401
    # --------------------------------------------------------
    def test_wrong_service_header_401(self, client, db_session):
        """Неверный X-Service-Key возвращает 401."""
        product_id = str(uuid4())
        
        response = client.post(
            "/api/v1/b2b/events",
            json=_make_event("PRODUCT_CREATED", product_id),
            headers={"X-Service-Key": "wrong-key"},
        )
        
        assert response.status_code == 401
        data = response.json()
        # ✅ ИСПРАВЛЕНО: кастомный handler возвращает JSON напрямую
        assert data["code"] == "UNAUTHORIZED"

    # --------------------------------------------------------
    # 8. hard_blocked_ignores_edited — HARD_BLOCKED игнорирует EDITED
    # --------------------------------------------------------
    def test_hard_blocked_ignores_edited(self, client, db_session, valid_service_headers):
        """Событие EDITED игнорируется для карточки в статусе HARD_BLOCKED."""
        product_id = str(uuid4())
        
        # 1. Создаём карточку
        client.post(
            "/api/v1/b2b/events",
            json=_make_event("PRODUCT_CREATED", product_id),
            headers=valid_service_headers,
        )
        
        # 2. Переводим в HARD_BLOCKED
        card = db_session.query(ModerationCard).filter(
            ModerationCard.product_id == product_id
        ).first()
        card.status = "HARD_BLOCKED"
        db_session.commit()
        
        # 3. Отправляем EDITED
        response = client.post(
            "/api/v1/b2b/events",
            json=_make_event(
                "PRODUCT_EDITED",
                product_id,
                json_before={"title": "Old"},
                json_after={"title": "New"},
            ),
            headers=valid_service_headers,
        )
        
        assert response.status_code == 202
        
        # 4. Проверяем: статус остался HARD_BLOCKED, данные не изменились
        db_session.refresh(card)
        assert card.status == "HARD_BLOCKED"
        # json_after не должен быть равен новому значению (т.к. событие проигнорировано)
        # Проверяем, что json_after НЕ содержит "New"
        if card.json_after:
            assert card.json_after.get("title") != "New"