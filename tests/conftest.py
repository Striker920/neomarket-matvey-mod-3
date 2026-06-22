import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.core.base import utcnow


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.fixture
def store():
    return app.state.store


@pytest.fixture
def hard_blocked_card(store):
    product_id = "product-hard-blocked"
    seller_id = "seller-456"
    
    store.products[product_id] = {
        'id': product_id,
        'seller_id': seller_id,
        'skus': ['sku-1'],
        'title': 'Hard Blocked Product',
        'status': 'HARD_BLOCKED'
    }
    
    store.skus['sku-1'] = {
        'id': 'sku-1',
        'product_id': product_id,
        'sku_code': 'SKU001',
        'price': 10000,
        'stock_quantity': 10,
        'reserved_quantity': 0
    }
    
    if not any(r['id'] == 'reason-hard-1' for r in store.blocking_reasons):
        store.blocking_reasons.append({
            'id': 'reason-hard-1',
            'name': 'Counterfeit',
            'hard_block': True,
            'is_active': True
        })
    
    now = utcnow()
    store.moderation_cards[product_id] = {
        'product_id': product_id,
        'seller_id': seller_id,
        'status': 'HARD_BLOCKED',
        'queue_priority': 1,
        'json_before': None,
        'json_after': {
            'id': product_id,
            'title': 'Hard Blocked Product',
            'skus': [{'id': 'sku-1', 'sku_code': 'SKU001', 'price': 10000}]
        },
        'blocking_reason_id': 'reason-hard-1',
        'moderator_id': 'moderator-789',
        'moderator_comment': 'Counterfeit product',
        'field_reports': [],
        'date_created': now,
        'date_updated': now,
        'date_moderation': now,
        'blocking_history': None
    }
    
    yield store.moderation_cards[product_id]
    
    # Очистка после теста
    if product_id in store.moderation_cards:
        del store.moderation_cards[product_id]
    if product_id in store.products:
        del store.products[product_id]
    if 'sku-1' in store.skus:
        del store.skus['sku-1']


@pytest.fixture
def in_review_card(store):
    product_id = "product-to-hard-block"
    seller_id = "seller-456"
    
    store.products[product_id] = {
        'id': product_id,
        'seller_id': seller_id,
        'skus': ['sku-2'],
        'title': 'Product to Hard Block',
        'status': 'IN_REVIEW'
    }
    
    store.skus['sku-2'] = {
        'id': 'sku-2',
        'product_id': product_id,
        'sku_code': 'SKU002',
        'price': 20000,
        'stock_quantity': 5,
        'reserved_quantity': 0
    }
    
    if not any(r['id'] == 'reason-hard-1' for r in store.blocking_reasons):
        store.blocking_reasons.append({
            'id': 'reason-hard-1',
            'name': 'Counterfeit',
            'hard_block': True,
            'is_active': True
        })
    
    now = utcnow()
    store.moderation_cards[product_id] = {
        'product_id': product_id,
        'seller_id': seller_id,
        'status': 'IN_REVIEW',
        'queue_priority': 1,
        'json_before': None,
        'json_after': {
            'id': product_id,
            'title': 'Product to Hard Block',
            'skus': [{'id': 'sku-2', 'sku_code': 'SKU002', 'price': 20000}]
        },
        'blocking_reason_id': None,
        'moderator_id': 'moderator-789',
        'moderator_comment': None,
        'field_reports': [],
        'date_created': now,
        'date_updated': now,
        'date_moderation': None,
        'blocking_history': None
    }
    
    yield store.moderation_cards[product_id]
    
    # Очистка после теста
    if product_id in store.moderation_cards:
        del store.moderation_cards[product_id]
    if product_id in store.products:
        del store.products[product_id]
    if 'sku-2' in store.skus:
        del store.skus['sku-2']
