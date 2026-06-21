from __future__ import annotations

import httpx
from typing import Any, Optional

from fastapi import APIRouter, Header, Request, Response
from fastapi.responses import JSONResponse

from app.api.v1.common import error_response, get_store, require_service_key
from app.core.base import ServiceError, iso, utcnow
from app.core.store import NeoMarketStore
from app.infrastructure.config.config import APP_CONFIG

b2b_events_router = APIRouter()
queue_router = APIRouter()
tickets_router = APIRouter()
blocking_reasons_router = APIRouter()


def _ticket_response(card: dict[str, Any]) -> dict[str, Any]:
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
        'blocking_reason_id': card.get('blocking_reason_id'),
        'moderator_comment': card.get('moderator_comment'),
        'field_reports': card.get('field_reports', []),
        'blocking_history': card.get('blocking_history'),
        'created_at': iso(card['date_created']),
        'updated_at': iso(card['date_updated']),
        'moderated_at': iso(card.get('date_moderation')),
    }


def _strip_private_fields(product_data: dict) -> dict:
    product_data = {**product_data}
    for sku in product_data.get('skus', []):
        sku.pop('cost_price', None)
        sku.pop('reserved_quantity', None)
    return product_data


def _compute_queue_priority(old_status: str, blocking_reason_id: Optional[str], total_active: int) -> int:
    if old_status == 'BLOCKED' and blocking_reason_id:
        return 2
    if old_status in ('MODERATED', 'APPROVED') and total_active > 0:
        return 3
    if old_status in ('MODERATED', 'APPROVED') and total_active == 0:
        return 4
    return 1


def _get_total_active(store: NeoMarketStore, product: dict) -> int:
    total = 0
    for sku_id in product.get('skus', []):
        sku = store.skus.get(sku_id)
        if sku:
            total += max(sku['stock_quantity'] - sku['reserved_quantity'], 0)
    return total


async def _send_to_b2b(request: Request, event: dict[str, Any]) -> None:
    transport = httpx.ASGITransport(app=request.app)
    async with httpx.AsyncClient(transport=transport, base_url=APP_CONFIG.B2B_BASE_URL, timeout=10.0) as client:
        resp = await client.post(
            '/api/v1/moderation/events',
            json=event,
            headers={'X-Service-Key': APP_CONFIG.B2B_SERVICE_KEY},
        )
        resp.raise_for_status()


def _find_card_by_ticket_id(store: NeoMarketStore, ticket_id: str) -> Optional[dict[str, Any]]:
    for card in store.moderation_cards.values():
        if card['product_id'] == ticket_id:
            return card
    return None


@b2b_events_router.post("/events")
async def moderation_receive_event(payload: dict[str, Any], request: Request, x_service_key: Optional[str] = Header(None)):
    store = get_store(request)
    try:
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
                'json_after': product,
                'blocking_reason_id': None,
                'moderator_id': None,
                'moderator_comment': None,
                'field_reports': [],
                'date_created': now,
                'date_updated': now,
                'date_moderation': None,
                'blocking_history': None,
            }
            return Response(status_code=202)

        elif event_type == 'PRODUCT_EDITED':
            if not card:
                raise ServiceError('BAD_REQUEST', 'PRODUCT_EDITED event for unknown product', 400)
            if card['status'] == 'HARD_BLOCKED':
                return Response(status_code=202)
            old_status = card['status']
            product = store.products.get(product_id)
            if not product:
                raise ServiceError('NOT_FOUND', 'Product not found in B2B', 404)
            total_active = _get_total_active(store, product)
            queue_priority = _compute_queue_priority(old_status, card.get('blocking_reason_id'), total_active)
            now = utcnow()
            card['json_before'] = card['json_after']
            card['json_after'] = product
            card['status'] = 'PENDING'
            card['queue_priority'] = queue_priority
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


@queue_router.post("/claim")
async def moderation_get_next(payload: dict[str, Any], request: Request, x_moderator_id: Optional[str] = Header(None)):
    store = get_store(request)
    try:
        moderator_id = x_moderator_id or 'unknown'
        for card in store.moderation_cards.values():
            if card['status'] == 'IN_REVIEW' and card['moderator_id'] == moderator_id:
                raise ServiceError('CONFLICT', 'Moderator already has a ticket in review', 409)

        candidates = []
        for pid, card in store.moderation_cards.items():
            if card['status'] != 'PENDING':
                continue
            candidates.append(card)
        if not candidates:
            return Response(status_code=204)
        candidates.sort(key=lambda c: c['date_updated'])
        card = candidates[0]
        card['status'] = 'IN_REVIEW'
        card['moderator_id'] = moderator_id
        card['date_updated'] = utcnow()
        return _ticket_response(card)
    except ServiceError as exc:
        return error_response(exc)


@tickets_router.post("/{ticket_id}/approve")
async def moderation_approve(ticket_id: str, payload: Optional[dict[str, Any]], request: Request, x_moderator_id: Optional[str] = Header(None)):
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

        product = store.products.get(ticket_id)
        if product and not product.get('skus'):
            raise ServiceError('CONFLICT', 'Product has no SKUs, cannot approve', 409)

        now = utcnow()
        comment = (payload or {}).get('moderator_comment')
        card['status'] = 'APPROVED'
        card['date_moderation'] = now
        card['moderator_comment'] = comment
        card['blocking_reason_id'] = None
        card['field_reports'] = []
        card['date_updated'] = now

        try:
            await _send_to_b2b(request, {
                'idempotency_key': store.new_id(),
                'product_id': ticket_id,
                'event_type': 'MODERATED',
                'occurred_at': iso(now),
            })
        except Exception:
            pass

        return _ticket_response(card)
    except ServiceError as exc:
        return error_response(exc)


@tickets_router.post("/{ticket_id}/block")
async def moderation_decline(ticket_id: str, payload: dict[str, Any], request: Request, x_moderator_id: Optional[str] = Header(None)):
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
            {'field_name': fr.get('field_path', fr.get('field_name', '')), 'comment': fr.get('message', fr.get('comment', ''))}
            for fr in field_reports
        ]
        card['date_updated'] = now

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


@blocking_reasons_router.get("")
async def moderation_blocking_reasons(request: Request, is_active: bool = True, hard_block: Optional[bool] = None):
    store = get_store(request)
    reasons = store.blocking_reasons
    if is_active:
        reasons = [r for r in reasons if r.get('is_active', True)]
    if hard_block is not None:
        reasons = [r for r in reasons if r.get('hard_block') == hard_block]
    return reasons
