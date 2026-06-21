import pytest
import app.api.v1.moderation_service as mod_service


@pytest.mark.asyncio
async def test_hard_block_transitions_to_terminal_and_emits_event(client, store, in_review_card):
    response = await client.post(
        "/api/v1/tickets/product-to-hard-block/block",
        headers={"X-Moderator-Id": "moderator-789"},
        json={
            "blocking_reason_ids": ["reason-hard-1"],
            "moderator_comment": "Counterfeit product"
        }
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "HARD_BLOCKED"
    assert data["blocking_reason_id"] == "reason-hard-1"
    
    card = store.moderation_cards["product-to-hard-block"]
    assert card["status"] == "HARD_BLOCKED"
    assert card["date_moderation"] is not None


@pytest.mark.asyncio
async def test_hard_block_event_carries_hard_block_true(client, store, in_review_card):
    sent_events = []
    
    async def mock_send_to_b2b(request, event):
        sent_events.append(event)
    
    original_send = mod_service._send_to_b2b
    mod_service._send_to_b2b = mock_send_to_b2b
    
    try:
        response = await client.post(
            "/api/v1/tickets/product-to-hard-block/block",
            headers={"X-Moderator-Id": "moderator-789"},
            json={
                "blocking_reason_ids": ["reason-hard-1"],
                "moderator_comment": "Counterfeit"
            }
        )
        
        assert response.status_code == 200
        assert len(sent_events) == 1
        
        event = sent_events[0]
        assert event["event_type"] == "BLOCKED"
        assert event["hard_block"] is True
        assert event["product_id"] == "product-to-hard-block"
        assert event["blocking_reason_id"] == "reason-hard-1"
    finally:
        mod_service._send_to_b2b = original_send


@pytest.mark.asyncio
async def test_any_modify_on_hard_blocked_returns_403(client, store, hard_blocked_card):
    response = await client.post(
        "/api/v1/tickets/product-hard-blocked/approve",
        headers={"X-Moderator-Id": "moderator-789"},
        json={}
    )
    assert response.status_code == 403
    assert "Cannot modify a hard-blocked ticket" in response.json()["detail"]["message"]
    
    response = await client.post(
        "/api/v1/tickets/product-hard-blocked/block",
        headers={"X-Moderator-Id": "moderator-789"},
        json={"blocking_reason_ids": ["reason-hard-1"]}
    )
    assert response.status_code == 403
    assert "Cannot modify a hard-blocked ticket" in response.json()["detail"]["message"]


@pytest.mark.asyncio
async def test_edited_event_on_hard_blocked_is_ignored(client, store, hard_blocked_card):
    response = await client.post(
        "/api/v1/b2b/events",
        json={
            "event_type": "PRODUCT_EDITED",
            "idempotency_key": "test-key-1",
            "payload": {
                "product_id": "product-hard-blocked",
                "seller_id": "seller-456"
            }
        },
        headers={"X-Service-Key": "test-service-key"}
    )
    
    assert response.status_code == 202
    
    card = store.moderation_cards["product-hard-blocked"]
    assert card["status"] == "HARD_BLOCKED"


@pytest.mark.asyncio
async def test_deleted_event_removes_hard_blocked(client, store, hard_blocked_card):
    assert "product-hard-blocked" in store.moderation_cards
    
    response = await client.post(
        "/api/v1/b2b/events",
        json={
            "event_type": "PRODUCT_DELETED",
            "idempotency_key": "test-key-2",
            "payload": {
                "product_id": "product-hard-blocked",
                "seller_id": "seller-456"
            }
        },
        headers={"X-Service-Key": "test-service-key"}
    )
    
    assert response.status_code == 202
    assert "product-hard-blocked" not in store.moderation_cards
