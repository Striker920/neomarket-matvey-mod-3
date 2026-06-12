import pytest
from uuid import uuid4
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock
import httpx

from src.models.product_moderation import ProductModeration
from src.config import settings


MOCK_B2B_PRODUCT = {
    "id": "product-1",
    "title": "iPhone 15",
    "description": "Smartphone",
    "status": "ON_MODERATION",
    "deleted": False,
    "blocked": False,
    "category": {"id": "cat-1", "name": "Electronics"},
    "images": [],
    "characteristics": [],
    "skus": []
}


class TestGetNext:

    def test_next_returns_oldest_pending(self, client, db_session):
        """Happy path: oldest PENDING → IN_REVIEW"""
        db_session.query(ProductModeration).delete()
        db_session.commit()

        card1 = ProductModeration(
            id=str(uuid4()),
            product_id="product-1",
            seller_id=str(uuid4()),
            status="PENDING",
            queue_priority=1,
            json_after=MOCK_B2B_PRODUCT,
            date_updated=datetime(2026, 1, 1, tzinfo=timezone.utc)
        )
        card2 = ProductModeration(
            id=str(uuid4()),
            product_id="product-2",
            seller_id=str(uuid4()),
            status="PENDING",
            queue_priority=1,
            json_after=MOCK_B2B_PRODUCT,
            date_updated=datetime(2026, 1, 2, tzinfo=timezone.utc)
        )
        db_session.add_all([card1, card2])
        db_session.commit()

        response = client.post(
            "/api/v1/product-moderation/get-next",
            json={"queueId": 1},
            headers={"X-Service-Key": settings.B2B_SERVICE_KEY, "X-Moderator-Id": "mod-1"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["product_id"] == "product-1"
        assert data["status"] == "IN_REVIEW"

    def test_empty_queue_returns_204(self, client, db_session):
        """Empty queue → 204"""
        db_session.query(ProductModeration).delete()
        db_session.commit()

        response = client.post(
            "/api/v1/product-moderation/get-next",
            json={"queueId": 1},
            headers={"X-Service-Key": settings.B2B_SERVICE_KEY}
        )

        assert response.status_code == 204

    def test_invalid_queue_returns_400(self, client, db_session):
        """Invalid queueId → 400"""
        response = client.post(
            "/api/v1/product-moderation/get-next",
            json={"queueId": 5},
            headers={"X-Service-Key": settings.B2B_SERVICE_KEY}
        )

        assert response.status_code == 400

    def test_autoprioritization(self, client, db_session):
        """queueId=null → autoprioritization 1→4"""
        db_session.query(ProductModeration).delete()
        db_session.commit()

        card = ProductModeration(
            id=str(uuid4()),
            product_id="product-1",
            seller_id=str(uuid4()),
            status="PENDING",
            queue_priority=3,
            json_after=MOCK_B2B_PRODUCT,
            date_updated=datetime(2026, 1, 1, tzinfo=timezone.utc)
        )
        db_session.add(card)
        db_session.commit()

        response = client.post(
            "/api/v1/product-moderation/get-next",
            json={},
            headers={"X-Service-Key": settings.B2B_SERVICE_KEY}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["queue_priority"] == 3

    def test_missing_service_header_401(self, client):
        """No X-Service-Key → 401"""
        response = client.post(
            "/api/v1/product-moderation/get-next",
            json={"queueId": 1}
        )
        assert response.status_code == 401
