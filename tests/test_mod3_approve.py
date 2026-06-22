import pytest
from httpx import AsyncClient
from app.main import app
from app.core.store import NeoMarketStore
from app.core.base import utcnow


@pytest.fixture
def client():
    return AsyncClient(app=app, base_url="http://test")


@pytest.fixture
def store(client):
    """Создать и инициализировать store для тестов."""
    # Инициализируем store в app.state
    app.state.store = NeoMarketStore()
    return app.state.store


@pytest.fixture
def sample_card(store):
    """Создать тестовую карточку в статусе IN_REVIEW."""
    card = {
        'product_id': 'product-123',
        'seller_id': 'seller-456',
        'status': 'IN_REVIEW',
        'queue_priority': 1,
        'json_before': None,  # Не редактировался
        'json_after': {'id': 'product-123', 'skus': [{'id': 'sku-1'}]},
        'moderator_id': 'moderator-789',
        'moderator_comment': None,
        'blocking_reason_id': None,
        'field_reports': [],
        'date_created': utcnow(),
        'date_updated': utcnow(),
        'date_moderation': None,
    }
    store.moderation_cards['product-123'] = card
    store.products['product-123'] = {'id': 'product-123', 'skus': [{'id': 'sku-1'}]}
    return card


@pytest.mark.asyncio
async def test_approve_transitions_to_approved_and_emits_event(client, store, sample_card):
    """Happy path: модератор одобряет карточку."""
    response = await client.post(
        "/api/v1/tickets/product-123/approve",
        headers={"X-Moderator-Id": "moderator-789"},
        json={"moderator_comment": "Approved"}
    )
    
    assert response.status_code == 200
    data = response.json()
    
    # Проверяем правильные имена полей
    assert data["id"] == "product-123"
    assert data["kind"] == "CREATE"
    assert data["status"] == "APPROVED"
    assert data["created_at"] is not None
    assert data["moderator_comment"] == "Approved"
    
    # Проверить, что карточка обновлена в store
    card = store.moderation_cards["product-123"]
    assert card["status"] == "APPROVED"
    assert card["date_moderation"] is not None


@pytest.mark.asyncio
async def test_approve_others_card_returns_403(client, store, sample_card):
    """Модератор не может одобрить карточку, закреплённую за другим модератором."""
    response = await client.post(
        "/api/v1/tickets/product-123/approve",
        headers={"X-Moderator-Id": "other-moderator"},
        json={}
    )
    
    assert response.status_code == 403
    data = response.json()
    assert data["code"] == "FORBIDDEN"
    assert "not assigned to you" in data["message"]


@pytest.mark.asyncio
async def test_approve_after_edited_returns_409(client, store, sample_card):
    """Если продавец отредактировал товар во время review, повторный approve должен вернуть 409."""
    # Имитируем редактирование товара во время review
    sample_card["json_before"] = {"old": "data"}
    sample_card["status"] = "PENDING"  # После редактирования статус сбрасывается
    
    response = await client.post(
        "/api/v1/tickets/product-123/approve",
        headers={"X-Moderator-Id": "moderator-789"},
        json={}
    )
    
    assert response.status_code == 409
    data = response.json()
    assert data["code"] == "CONFLICT"
    assert "not in review" in data["message"]


@pytest.mark.asyncio
async def test_approve_without_sku_returns_409(client, store, sample_card):
    """Товар без SKU нельзя одобрить."""
    # Удаляем SKU из продукта
    store.products["product-123"] = {"id": "product-123", "skus": []}
    
    response = await client.post(
        "/api/v1/tickets/product-123/approve",
        headers={"X-Moderator-Id": "moderator-789"},
        json={}
    )
    
    assert response.status_code == 409
    data = response.json()
    assert data["code"] == "CONFLICT"
    assert "no SKUs" in data["message"]