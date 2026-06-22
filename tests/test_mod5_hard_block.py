import pytest
from httpx import AsyncClient
from app.main import app
from app.core.store import NeoMarketStore
from app.core.base import utcnow
from app.infrastructure.config.config import APP_CONFIG  # ✅ Добавлен импорт


@pytest.fixture
def client():
    return AsyncClient(app=app, base_url="http://test")


@pytest.fixture
def store(client):
    """Создать и инициализировать store для тестов."""
    app.state.store = NeoMarketStore()
    # Добавляем тестовую причину блокировки с hard_block=True
    app.state.store.blocking_reasons.append({
        'id': 'reason-hard-1',
        'title': 'Counterfeit product',
        'comment': 'Hard block reason',
        'hard_block': True,
        'is_active': True
    })
    # Добавляем мягкую причину для сравнения
    app.state.store.blocking_reasons.append({
        'id': 'reason-soft-1',
        'title': 'Minor issue',
        'comment': 'Soft block reason',
        'hard_block': False,
        'is_active': True
    })
    return app.state.store


@pytest.fixture
def sample_card(store):
    """Создать тестовую карточку в статусе IN_REVIEW."""
    card = {
        'product_id': 'product-hard-123',
        'seller_id': 'seller-456',
        'status': 'IN_REVIEW',
        'queue_priority': 1,
        'json_before': None,
        'json_after': {'id': 'product-hard-123', 'skus': [{'id': 'sku-1'}]},
        'moderator_id': 'moderator-789',
        'moderator_comment': None,
        'blocking_reason_id': None,
        'field_reports': [],
        'date_created': utcnow(),
        'date_updated': utcnow(),
        'date_moderation': None,
        'blocking_history': None,
    }
    store.moderation_cards['product-hard-123'] = card
    store.products['product-hard-123'] = {'id': 'product-hard-123', 'skus': ['sku-1']}
    store.skus['sku-1'] = {
        'id': 'sku-1',
        'stock_quantity': 10,
        'reserved_quantity': 2
    }
    return card


# ============================================================
# Тест 1: Happy path — переход в HARD_BLOCKED + событие
# ============================================================
@pytest.mark.asyncio
async def test_hard_block_transitions_to_terminal_and_emits_event(client, store, sample_card, monkeypatch):
    """Happy path: жёсткая блокировка переводит карточку в HARD_BLOCKED и отправляет событие."""
    captured_events = []
    
    async def mock_send_to_b2b(request, event):
        captured_events.append(event)
    
    from app.api.v1 import moderation_service
    monkeypatch.setattr(moderation_service, '_send_to_b2b', mock_send_to_b2b)
    
    response = await client.post(
        "/api/v1/tickets/product-hard-123/block",
        headers={"X-Moderator-Id": "moderator-789"},
        json={
            "blocking_reason_ids": ["reason-hard-1"],
            "moderator_comment": "Counterfeit product",
            "field_reports": []
        }
    )
    
    assert response.status_code == 200
    data = response.json()
    
    # Проверяем ответ
    assert data["id"] == "product-hard-123"
    assert data["status"] == "HARD_BLOCKED"
    assert data["blocking_reason_id"] == "reason-hard-1"
    assert data["moderator_comment"] == "Counterfeit product"
    
    # Проверяем, что карточка обновлена в store
    card = store.moderation_cards["product-hard-123"]
    assert card["status"] == "HARD_BLOCKED"
    assert card["date_moderation"] is not None
    
    # Проверяем, что событие отправлено
    assert len(captured_events) == 1
    event = captured_events[0]
    assert event["event_type"] == "BLOCKED"
    assert event["product_id"] == "product-hard-123"


# ============================================================
# Тест 2: Флаг hard_block=true в событии
# ============================================================
@pytest.mark.asyncio
async def test_hard_block_event_carries_hard_block_true(client, store, sample_card, monkeypatch):
    """Флаг hard_block=true в событии корректный."""
    captured_events = []
    
    async def mock_send_to_b2b(request, event):
        captured_events.append(event)
    
    from app.api.v1 import moderation_service
    monkeypatch.setattr(moderation_service, '_send_to_b2b', mock_send_to_b2b)
    
    response = await client.post(
        "/api/v1/tickets/product-hard-123/block",
        headers={"X-Moderator-Id": "moderator-789"},
        json={
            "blocking_reason_ids": ["reason-hard-1"],
            "moderator_comment": "Counterfeit",
            "field_reports": []
        }
    )
    
    assert response.status_code == 200
    assert len(captured_events) == 1
    
    event = captured_events[0]
    assert event["event_type"] == "BLOCKED"
    assert event["hard_block"] is True  # ✅ Флаг hard_block=true
    assert event["product_id"] == "product-hard-123"
    assert event["blocking_reason_id"] == "reason-hard-1"


# ============================================================
# Тест 3: Любая правка HARD_BLOCKED → 403
# ============================================================
@pytest.mark.asyncio
async def test_any_modify_on_hard_blocked_returns_403(client, store, sample_card):
    """Любая попытка правки HARD_BLOCKED карточки → 403."""
    # Сначала блокируем
    await client.post(
        "/api/v1/tickets/product-hard-123/block",
        headers={"X-Moderator-Id": "moderator-789"},
        json={
            "blocking_reason_ids": ["reason-hard-1"],
            "moderator_comment": "Counterfeit",
            "field_reports": []
        }
    )
    
    # Пытаемся одобрить → 403
    response_approve = await client.post(
        "/api/v1/tickets/product-hard-123/approve",
        headers={"X-Moderator-Id": "moderator-789"},
        json={}
    )
    assert response_approve.status_code == 403
    data = response_approve.json()
    # ✅ Проверяем плоский формат (без обёртки detail)
    assert data["code"] == "FORBIDDEN"
    assert "hard-blocked" in data["message"]
    
    # Пытаемся заблокировать снова → 403
    response_block = await client.post(
        "/api/v1/tickets/product-hard-123/block",
        headers={"X-Moderator-Id": "moderator-789"},
        json={
            "blocking_reason_ids": ["reason-hard-1"],
            "moderator_comment": "Test",
            "field_reports": []
        }
    )
    assert response_block.status_code == 403
    data = response_block.json()
    assert data["code"] == "FORBIDDEN"
    assert "hard-blocked" in data["message"]


# ============================================================
# Тест 4: EDITED игнорируется для HARD_BLOCKED
# ============================================================
@pytest.mark.asyncio
async def test_edited_event_on_hard_blocked_is_ignored(client, store, sample_card):
    """Событие EDITED от B2B не выводит из терминального статуса."""
    # Сначала блокируем
    await client.post(
        "/api/v1/tickets/product-hard-123/block",
        headers={"X-Moderator-Id": "moderator-789"},
        json={
            "blocking_reason_ids": ["reason-hard-1"],
            "moderator_comment": "Counterfeit",
            "field_reports": []
        }
    )
    
    # Проверяем, что карточка HARD_BLOCKED
    card_before = store.moderation_cards["product-hard-123"]
    assert card_before["status"] == "HARD_BLOCKED"
    
    # ✅ ИСПРАВЛЕНО: используем APP_CONFIG.B2B_SERVICE_KEY вместо хардкода
    response = await client.post(
        "/api/v1/b2b/events",
        headers={"X-Service-Key": APP_CONFIG.B2B_SERVICE_KEY},
        json={
            "event_type": "PRODUCT_EDITED",
            "payload": {
                "product_id": "product-hard-123",
                "seller_id": "seller-456",
                "json_before": {},
                "json_after": {"title": "Updated"}
            }
        }
    )
    
    assert response.status_code == 202
    
    # Проверяем, что статус остался HARD_BLOCKED
    card_after = store.moderation_cards["product-hard-123"]
    assert card_after["status"] == "HARD_BLOCKED"


# ============================================================
# Тест 5: DELETED удаляет запись
# ============================================================
@pytest.mark.asyncio
async def test_deleted_event_removes_hard_blocked(client, store, sample_card):
    """Событие DELETED удаляет запись из Moderation."""
    # Сначала блокируем
    await client.post(
        "/api/v1/tickets/product-hard-123/block",
        headers={"X-Moderator-Id": "moderator-789"},
        json={
            "blocking_reason_ids": ["reason-hard-1"],
            "moderator_comment": "Counterfeit",
            "field_reports": []
        }
    )
    
    # Проверяем, что карточка есть
    assert "product-hard-123" in store.moderation_cards
    
    # ✅ ИСПРАВЛЕНО: используем APP_CONFIG.B2B_SERVICE_KEY вместо хардкода
    response = await client.post(
        "/api/v1/b2b/events",
        headers={"X-Service-Key": APP_CONFIG.B2B_SERVICE_KEY},
        json={
            "event_type": "PRODUCT_DELETED",
            "payload": {
                "product_id": "product-hard-123",
                "seller_id": "seller-456"
            }
        }
    )
    
    assert response.status_code == 202
    
    # Проверяем, что карточка удалена
    assert "product-hard-123" not in store.moderation_cards