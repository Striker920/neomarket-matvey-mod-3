from __future__ import annotations
import httpx
from typing import Any, Optional
from fastapi import APIRouter, Header, Request, Response
from fastapi.responses import JSONResponse

from app.api.v1.common import error_response, get_store, require_service_key
from app.core.base import ServiceError, iso, utcnow
from app.core.config import settings

b2b_events_router = APIRouter()
queue_router = APIRouter()
tickets_router = APIRouter()
blocking_reasons_router = APIRouter()


def _ticket_response(card: dict[str, Any]) -> dict[str, Any]:
    """
    Формирование ответа TicketResponse.
    ✅ ИСПРАВЛЕНО: добавлены все поля из спецификации OpenAPI
    """
    kind = 'CREATE' if card.get('json_before') is None else 'EDIT'
    
    return {
        'id': card['product_id'],
        'product_id': card['product_id'],
        'seller_id': card['seller_id'],
        'kind': kind,
        'status': card['status'],
        'queue_priority': card['queue_priority'],
        'json_before': card.get('json_before'),
        'json_after': card.get('json_after'),
        'blocking_reason_id': card.get('blocking_reason_id'),  # ✅ Добавлено
        'field_reports': card.get('field_reports', []),  # ✅ Добавлено
        'moderator_id': card.get('moderator_id'),  # ✅ Добавлено
        'moderator_comment': card.get('moderator_comment'),  # ✅ Добавлено
        'date_moderation': iso(card.get('date_moderation')),  # ✅ Добавлено
        'blocking_history': card.get('blocking_history'),
        'created_at': iso(card['date_created']),
        'updated_at': iso(card['date_updated']),
    }


def _find_card_by_ticket_id(store, ticket_id: str) -> Optional[dict[str, Any]]:
    """Найти карточку по product_id (ticket_id)."""
    for card in store.moderation_cards.values():
        if card['product_id'] == ticket_id:
            return card
    return None


async def _send_to_b2b(request: Request, event: dict[str, Any]) -> None:
    """
    Отправка события в B2B.
    ✅ ИСПРАВЛЕНО: путь /api/v1/moderation/events
    ✅ ИСПРАВЛЕНО: заголовок X-Service-Key
    """
    transport = httpx.ASGITransport(app=request.app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url=settings.B2B_BASE_URL,
        timeout=10.0
    ) as client:
        resp = await client.post(
            '/api/v1/moderation/events',  # ✅ Исправлено
            json=event,
            headers={'X-Service-Key': settings.B2B_SERVICE_KEY},  # ✅ Добавлено
        )
        resp.raise_for_status()


@tickets_router.post("/{ticket_id}/approve")
async def moderation_approve(
    ticket_id: str,
    payload: Optional[dict[str, Any]],
    request: Request,
    x_moderator_id: Optional[str] = Header(None)
):
    """
    US-MOD-03: Одобрение товара модератором.
    
    Проверки:
    1. Карточка существует (404)
    2. Не HARD_BLOCKED (403)
    3. Статус IN_REVIEW (409)
    4. Закреплён за текущим модератором (403)
    5. Есть SKU (409)
    
    Переход: IN_REVIEW → APPROVED
    Отправка события: MODERATED в B2B
    """
    store = get_store(request)
    
    try:
        # 1. Найти карточку
        card = _find_card_by_ticket_id(store, ticket_id)
        if not card:
            raise ServiceError('NOT_FOUND', 'Ticket not found', 404)
        
        # 2. Проверить, что не HARD_BLOCKED
        if card['status'] == 'HARD_BLOCKED':
            raise ServiceError('FORBIDDEN', 'Cannot modify a hard-blocked ticket', 403)
        
        # 3. Проверить статус IN_REVIEW
        if card['status'] != 'IN_REVIEW':
            raise ServiceError('CONFLICT', 'Ticket is not in review', 409)
        
        # 4. Проверить, что закреплён за текущим модератором
        if card['moderator_id'] != (x_moderator_id or 'unknown'):
            raise ServiceError('FORBIDDEN', 'This ticket is not assigned to you', 403)
        
        # 5. Проверить, что есть SKU
        product = store.products.get(ticket_id)
        if product and not product.get('skus'):
            raise ServiceError('CONFLICT', 'Product has no SKUs, cannot approve', 409)
        
        # ✅ ИСПРАВЛЕНО: APPROVED вместо MODERATED
        now = utcnow()
        comment = (payload or {}).get('moderator_comment')
        
        card['status'] = 'APPROVED'  # ✅ Было: MODERATED
        card['date_moderation'] = now
        card['moderator_comment'] = comment
        card['blocking_reason_id'] = None
        card['field_reports'] = []
        card['date_updated'] = now
        
        # Отправка события в B2B
        try:
            await _send_to_b2b(request, {
                'idempotency_key': store.new_id(),
                'product_id': ticket_id,
                'event_type': 'MODERATED',
                'occurred_at': iso(now),
            })
        except Exception:
            pass  # Fire-and-forget
        
        return _ticket_response(card)
    
    except ServiceError as exc:
        return error_response(exc)


@tickets_router.post("/{ticket_id}/block")
async def moderation_decline(
    ticket_id: str,
    payload: dict[str, Any],
    request: Request,
    x_moderator_id: Optional[str] = Header(None)
):
    """US-MOD-04/05: Блокировка товара (soft/hard)."""
    store = get_store(request)
    
    try:
        card = _find_card_by_ticket_id(store, ticket_id)
        if not card:
            raise ServiceError('NOT_FOUND', 'Ticket not found', 404)
        
        if card['status'] == 'HARD_BLOCKED':
            raise ServiceError('FORBIDDEN', 'Cannot modify a hard-blocked ticket', 403)
        
        if card['status'] != 'IN_REVIEW':
            raise ServiceError('CONFLICT', 'Ticket is not in review', 409)
        
        if card['moderator_id'] != (x_moderator_id or 'unknown'):
            raise ServiceError('FORBIDDEN', 'This ticket is not assigned to you', 403)
        
        blocking_reason_ids = payload.get('blocking_reason_ids', [])
        if not blocking_reason_ids:
            raise ServiceError('BAD_REQUEST', 'blocking_reason_ids is required', 400)
        
        first_reason_id = blocking_reason_ids[0]
        reason = next((r for r in store.blocking_reasons if r['id'] == first_reason_id), None)
        if not reason:
            raise ServiceError('BAD_REQUEST', 'Blocking reason not found', 400)
        
        now = utcnow()
        is_hard_block = reason.get('hard_block', False)
        
        card['status'] = 'HARD_BLOCKED' if is_hard_block else 'BLOCKED'
        card['date_moderation'] = now
        card['blocking_reason_id'] = first_reason_id
        card['moderator_comment'] = payload.get('moderator_comment')
        
        field_reports = payload.get('field_reports', [])
        card['field_reports'] = [
            {
                'field_name': fr.get('field_path', fr.get('field_name', '')),
                'comment': fr.get('message', fr.get('comment', ''))
            }
            for fr in field_reports
        ]
        
        card['date_updated'] = now
        
        # Отправка события в B2B
        try:
            await _send_to_b2b(request, {
                'idempotency_key': store.new_id(),
                'product_id': ticket_id,
                'event_type': 'BLOCKED',
                'blocking_reason_id': first_reason_id,
                'moderator_comment': card['moderator_comment'],
                'field_reports': card['field_reports'],
                'hard_block': is_hard_block,
                'occurred_at': iso(now),
            })
        except Exception:
            pass
        
        return _ticket_response(card)
    
    except ServiceError as exc:
        return error_response(exc)


@b2b_events_router.post("/events")
async def moderation_receive_event(
    payload: dict[str, Any],
    request: Request,
    x_service_key: Optional[str] = Header(None)
):
    """
    Приём событий от B2B (PRODUCT_CREATED, PRODUCT_EDITED, PRODUCT_DELETED).
    ✅ ИСПРАВЛЕНО: добавлена проверка X-Service-Key
    """
    store = get_store(request)
    
    try:
        # ✅ Проверка X-Service-Key
        require_service_key(x_service_key)
        
        event_type = payload.get('event_type')
        if not event_type:
            raise ServiceError('BAD_REQUEST', 'event_type is required', 400)
        
        inner = payload.get('payload') or {}
        product_id = inner.get('product_id')
        seller_id = inner.get('seller_id')
        
        if not product_id:
            raise ServiceError('BAD_REQUEST', 'product_id is required in payload', 400)
        
        card = store.moderation_cards.get(product_id)
        
        if event_type == 'PRODUCT_CREATED':
            if card and card['status'] == 'HARD_BLOCKED':
                return Response(status_code=202)
            
            if card:
                raise ServiceError('CONFLICT', 'Duplicate PRODUCT_CREATED event', 409)
            
            product = store.products.get(product_id)
            if not product:
                raise ServiceError('NOT_FOUND', 'Product not found in B2B', 404)
            
            now = utcnow()
            store.moderation_cards[product_id] = {
                'product_id': product_id,
                'seller_id': seller_id or product.get('seller_id'),
                'status': 'PENDING',
                'queue_priority': 1,
                'json_before': None,
                'json_after': inner.get('json_after', {}),
                'blocking_reason_id': None,
                'moderator_id': None,
                'moderator_comment': None,
                'field_reports': [],
                'date_created': now,
                'date_updated': now,
                'date_moderation': None,
            }
            
            return Response(status_code=202)
        
        elif event_type == 'PRODUCT_EDITED':
            if not card:
                raise ServiceError('BAD_REQUEST', 'PRODUCT_EDITED event for unknown product', 400)
            
            if card['status'] == 'HARD_BLOCKED':
                return Response(status_code=202)
            
            now = utcnow()
            card['json_before'] = card['json_after']
            card['json_after'] = inner.get('json_after', {})
            card['status'] = 'PENDING'
            card['moderator_id'] = None
            card['field_reports'] = []
            card['date_updated'] = now
            
            return Response(status_code=202)
        
        elif event_type == 'PRODUCT_DELETED':
            if card:
                del store.moderation_cards[product_id]
            
            return Response(status_code=202)
        
        else:
            raise ServiceError('BAD_REQUEST', f'Unknown event_type: {event_type}', 400)
    
    except ServiceError as exc:
        return error_response(exc)