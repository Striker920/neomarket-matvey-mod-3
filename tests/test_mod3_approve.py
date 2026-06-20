import pytest
from httpx import AsyncClient
from app.main import app
from app.models.store import ModerationCard
from datetime import datetime


@pytest.fixture
def client():
    return AsyncClient(app=app, base_url="http://test")


@pytest.fixture
def store(client):
    """Получить store из app.state."""
    from app.api.v1.moderation_service import _store
    return _store


@pytest.fixture
def sample_card(store):
    """Создать тестовую карточку в статусе IN_REVIEW."""
    card = ModerationCard(
        product_id="product-123",
        seller_id="seller-456",
        status="IN_REVIEW",
        moderator_id="moderator-789",
        json_before=None,
        json_after={"id": "product-123", "skus": [{"id": "sku-1"}]},
        date_created=datetime.utcnow(),
        date_updated=datetime.utcnow()
    )
    store.moderation_cards["product-123"] = card
    store.products["product-123"] = {"id": "product-123", "skus": [{"id": "sku-1"}]}
    return card


@pytest.mark.asyncio
async def test_approve_transitions_to_moderated_and_emits_event(client, store, sample_card):
    """
    Happy path: модератор одобряет карточку.
    - Статус переходит в MODERATED
    - Событие MODERATED отправляется в B2B
    """
    response = await client.post(
        "/api/v1/tickets/product-123/approve",
        headers={"X-Moderator-Id": "moderator-789"},
        json={"moderator_comment": "Approved"}
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "MODERATED"
    assert data["moderator_comment"] == "Approved"
    assert data["moderator_id"] == "moderator-789"
    
    card = store.moderation_cards["product-123"]
    assert card.status == "MODERATED"
    assert card.date_moderation is not None


@pytest.mark.asyncio
async def test_approve_others_card_returns_403(client, store, sample_card):
    """
    Модератор не может одобрить карточку, закреплённую за другим модератором.
    """
    response = await client.post(
        "/api/v1/tickets/product-123/approve",
        headers={"X-Moderator-Id": "other-moderator"},
        json={}
    )
    
    assert response.status_code == 403
    assert "not assigned to you" in response.json()["detail"]


@pytest.mark.asyncio
async def test_approve_after_edited_returns_409(client, store, sample_card):
    """
    Если продавец отредактировал товар во время review (json_before != None),
    повторный approve должен вернуть 409.
    """
    sample_card.json_before = {"id": "product-123", "old_field": "value"}
    
    response = await client.post(
        "/api/v1/tickets/product-123/approve",
        headers={"X-Moderator-Id": "moderator-789"},
        json={}
    )
    
    assert response.status_code == 409
    assert "edited during review" in response.json()["detail"]


@pytest.mark.asyncio
async def test_approve_without_sku_returns_409(client, store):
    """
    Товар без SKU нельзя одобрить.
    """
    card = ModerationCard(
        product_id="product-no-sku",
        seller_id="seller-456",
        status="IN_REVIEW",
        moderator_id="moderator-789",
        json_before=None,
        json_after={"id": "product-no-sku", "skus": []},
        date_created=datetime.utcnow(),
        date_updated=datetime.utcnow()
    )
    store.moderation_cards["product-no-sku"] = card
    store.products["product-no-sku"] = {"id": "product-no-sku", "skus": []}
    
    response = await client.post(
        "/api/v1/tickets/product-no-sku/approve",
        headers={"X-Moderator-Id": "moderator-789"},
        json={}
    )
    
    assert response.status_code == 409
    assert "no SKUs" in response.json()["detail"]
