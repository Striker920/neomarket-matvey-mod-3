from fastapi import APIRouter, HTTPException, Header, Request, Response
from typing import Optional, Any
from datetime import datetime
from app.models.store import Store, ModerationCard
from app.services.b2b_client import B2BClient

tickets_router = APIRouter()
queue_router = APIRouter()
b2b_events_router = APIRouter()

# In-memory store (для простоты, в проде использовать БД)
_store = Store()
_b2b_client = B2BClient()


def _get_store(request: Request) -> Store:
    """Получить store из request или создать новый."""
    if not hasattr(request.app.state, "store"):
        request.app.state.store = _store
    return request.app.state.store


def _get_b2b_client(request: Request) -> B2BClient:
    """Получить B2B клиент."""
    if not hasattr(request.app.state, "b2b_client"):
        request.app.state.b2b_client = _b2b_client
    return request.app.state.b2b_client


def _find_card_by_ticket_id(store: Store, ticket_id: str) -> Optional[ModerationCard]:
    """Найти карточку по ticket_id (product_id)."""
    return store.moderation_cards.get(ticket_id)


def _ticket_response(card: ModerationCard) -> dict:
    """Форматировать ответ для карточки."""
    return {
        "ticket_id": card.product_id,
        "product_id": card.product_id,
        "seller_id": card.seller_id,
        "status": card.status,
        "queue_priority": card.queue_priority,
        "moderator_id": card.moderator_id,
        "moderator_comment": card.moderator_comment,
        "blocking_reason_id": card.blocking_reason_id,
        "field_reports": card.field_reports,
        "date_created": card.date_created.isoformat(),
        "date_updated": card.date_updated.isoformat(),
        "date_moderation": card.date_moderation.isoformat() if card.date_moderation else None,
    }


# ==================== B2B Events ====================

@b2b_events_router.post("/events")
async def receive_b2b_event(
    payload: dict[str, Any],
    request: Request,
    x_service_key: Optional[str] = Header(None)
):
    """
    Приём событий от B2B:
    - PRODUCT_CREATED: создать карточку модерации
    - PRODUCT_EDITED: обновить карточку, сбросить в PENDING
    - PRODUCT_DELETED: удалить карточку
    """
    store = _get_store(request)
    
    event_type = payload.get("event_type")
    inner = payload.get("payload", {})
    product_id = inner.get("product_id")
    seller_id = inner.get("seller_id")
    
    if not product_id:
        raise HTTPException(status_code=400, detail="product_id is required")
    
    if event_type == "PRODUCT_CREATED":
        card = store.moderation_cards.get(product_id)
        if card:
            raise HTTPException(status_code=409, detail="Card already exists")
        
        now = datetime.utcnow()
        card = ModerationCard(
            product_id=product_id,
            seller_id=seller_id or "unknown",
            status="PENDING",
            json_after=inner.get("product_data"),
            date_created=now,
            date_updated=now
        )
        store.moderation_cards[product_id] = card
        return Response(status_code=202)
    
    elif event_type == "PRODUCT_EDITED":
        card = store.moderation_cards.get(product_id)
        if not card:
            raise HTTPException(status_code=400, detail="Card not found")
        
        if card.status == "HARD_BLOCKED":
            return Response(status_code=202)
        
        now = datetime.utcnow()
        card.json_before = card.json_after
        card.json_after = inner.get("product_data")
        card.status = "PENDING"
        card.moderator_id = None
        card.field_reports = []
        card.date_updated = now
        return Response(status_code=202)
    
    elif event_type == "PRODUCT_DELETED":
        if product_id in store.moderation_cards:
            del store.moderation_cards[product_id]
        return Response(status_code=202)
    
    else:
        raise HTTPException(status_code=400, detail=f"Unknown event_type: {event_type}")


# ==================== Queue ====================

@queue_router.post("/claim")
async def claim_next_ticket(
    request: Request,
    x_moderator_id: Optional[str] = Header(None),
    payload: Optional[dict[str, Any]] = None
):
    """
    Модератор забирает следующую карточку из очереди.
    Переход: PENDING -> IN_REVIEW
    """
    store = _get_store(request)
    moderator_id = x_moderator_id or "unknown"
    
    for card in store.moderation_cards.values():
        if card.status == "IN_REVIEW" and card.moderator_id == moderator_id:
            raise HTTPException(
                status_code=409,
                detail="Moderator already has a ticket in review"
            )
    
    pending_cards = [c for c in store.moderation_cards.values() if c.status == "PENDING"]
    if not pending_cards:
        return Response(status_code=204)
    
    pending_cards.sort(key=lambda c: (-c.queue_priority, c.date_updated))
    card = pending_cards[0]
    
    card.status = "IN_REVIEW"
    card.moderator_id = moderator_id
    card.date_updated = datetime.utcnow()
    
    return _ticket_response(card)


# ==================== Tickets ====================

@tickets_router.post("/{ticket_id}/approve")
async def approve_ticket(
    ticket_id: str,
    request: Request,
    payload: Optional[dict[str, Any]] = None,
    x_moderator_id: Optional[str] = Header(None)
):
    """
    US-MOD-03: Одобрение товара модератором.
    
    Проверки:
    1. Карточка существует
    2. Не HARD_BLOCKED
    3. Статус IN_REVIEW
    4. Закреплён за текущим модератором
    5. Есть SKU
    6. Не было EDITED во время review (json_before == None)
    
    Переход: IN_REVIEW -> MODERATED
    Отправка события MODERATED в B2B
    """
    store = _get_store(request)
    b2b_client = _get_b2b_client(request)
    
    card = _find_card_by_ticket_id(store, ticket_id)
    if not card:
        raise HTTPException(status_code=404, detail="Ticket not found")
    
    if card.status == "HARD_BLOCKED":
        raise HTTPException(status_code=403, detail="Cannot modify a hard-blocked ticket")
    
    if card.status != "IN_REVIEW":
        raise HTTPException(status_code=409, detail="Ticket is not in review")
    
    moderator_id = x_moderator_id or "unknown"
    if card.moderator_id != moderator_id:
        raise HTTPException(status_code=403, detail="This ticket is not assigned to you")
    
    product = store.products.get(ticket_id)
    if product and not product.get("skus"):
        raise HTTPException(status_code=409, detail="Product has no SKUs, cannot approve")
    
    if card.json_before is not None:
        raise HTTPException(
            status_code=409,
            detail="Product was edited during review, please re-claim the ticket"
        )
    
    now = datetime.utcnow()
    comment = (payload or {}).get("moderator_comment")
    
    card.status = "MODERATED"
    card.date_moderation = now
    card.moderator_comment = comment
    card.blocking_reason_id = None
    card.field_reports = []
    card.date_updated = now
    
    event_data = {
        "idempotency_key": store.new_id(),
        "product_id": ticket_id,
        "event_type": "MODERATED",
        "occurred_at": now.isoformat(),
        "moderator_id": moderator_id,
        "moderator_comment": comment
    }
    
    await b2b_client.send_event(event_data)
    
    return _ticket_response(card)


@tickets_router.post("/{ticket_id}/block")
async def block_ticket(
    ticket_id: str,
    request: Request,
    payload: dict[str, Any],
    x_moderator_id: Optional[str] = Header(None)
):
    """
    Блокировка товара модератором (US-MOD-04).
    """
    store = _get_store(request)
    b2b_client = _get_b2b_client(request)
    
    card = _find_card_by_ticket_id(store, ticket_id)
    if not card:
        raise HTTPException(status_code=404, detail="Ticket not found")
    
    if card.status == "HARD_BLOCKED":
        raise HTTPException(status_code=403, detail="Cannot modify a hard-blocked ticket")
    
    if card.status != "IN_REVIEW":
        raise HTTPException(status_code=409, detail="Ticket is not in review")
    
    moderator_id = x_moderator_id or "unknown"
    if card.moderator_id != moderator_id:
        raise HTTPException(status_code=403, detail="This ticket is not assigned to you")
    
    blocking_reason_ids = payload.get("blocking_reason_ids", [])
    if not blocking_reason_ids:
        raise HTTPException(status_code=400, detail="blocking_reason_ids is required")
    
    first_reason_id = blocking_reason_ids[0]
    reason = next((r for r in store.blocking_reasons if r["id"] == first_reason_id), None)
    if not reason:
        raise HTTPException(status_code=400, detail="Blocking reason not found")
    
    now = datetime.utcnow()
    is_hard_block = reason.get("hard_block", False)
    
    card.status = "HARD_BLOCKED" if is_hard_block else "BLOCKED"
    card.date_moderation = now
    card.blocking_reason_id = first_reason_id
    card.moderator_comment = payload.get("moderator_comment")
    card.field_reports = payload.get("field_reports", [])
    card.date_updated = now
    
    event_data = {
        "idempotency_key": store.new_id(),
        "product_id": ticket_id,
        "event_type": "BLOCKED",
        "blocking_reason_id": first_reason_id,
        "moderator_comment": card.moderator_comment,
        "field_reports": card.field_reports,
        "hard_block": is_hard_block,
        "occurred_at": now.isoformat()
    }
    
    await b2b_client.send_event(event_data)
    
    return _ticket_response(card)
