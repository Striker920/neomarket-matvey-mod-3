import httpx
import structlog
from typing import Any

logger = structlog.get_logger(__name__)


class B2BClient:
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url
    
    async def send_event(self, event_data: dict[str, Any]) -> bool:
        """
        Отправка события в B2B.
        US-MOD-03: ADR - синхронный POST (fire-and-forget с логированием).
        """
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.post(
                    f"{self.base_url}/api/v1/b2b/events",
                    json=event_data,
                    headers={"Content-Type": "application/json"}
                )
                response.raise_for_status()
                logger.info("event_sent_to_b2b", event_type=event_data.get("event_type"))
                return True
        except Exception as e:
            logger.error("failed_to_send_event_to_b2b", error=str(e), event_data=event_data)
            return False
