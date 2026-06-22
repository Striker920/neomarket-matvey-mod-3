import uuid
from typing import Any


class NeoMarketStore:
    """In-memory store для тестов (имитация БД)."""
    
    def __init__(self):
        self.moderation_cards: dict[str, dict[str, Any]] = {}
        self.products: dict[str, dict[str, Any]] = {}
        self.blocking_reasons: list[dict[str, Any]] = []
    
    def new_id(self) -> str:
        """Генерация нового UUID."""
        return str(uuid.uuid4())