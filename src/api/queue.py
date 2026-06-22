from fastapi import APIRouter, Depends, HTTPException, Request, Body
from fastapi.responses import Response
from sqlalchemy.orm import Session
from typing import Optional
from src.database import get_db
from src.services.queue_service import QueueService
from src.schemas.queue import ClaimRequest, TicketResponse

router = APIRouter(prefix="/api/v1/queue", tags=["Queue"])


def get_moderator_id(request: Request) -> str:
    """Извлечь ID модератора из заголовка X-Moderator-Id."""
    moderator_id = request.headers.get("X-Moderator-Id")
    if not moderator_id:
        raise HTTPException(
            status_code=401,
            detail={
                "code": "UNAUTHORIZED",
                "message": "Missing X-Moderator-Id header"
            }
        )
    return moderator_id


@router.post("/claim", response_model=TicketResponse, status_code=200)
def claim_card(
    request: Request,
    body: Optional[ClaimRequest] = Body(None),
    moderator_id: str = Depends(get_moderator_id),
    db: Session = Depends(get_db),
):
    """
    Получить следующую карточку из очереди.
    """
    service = QueueService(db)
    
    queue_priority = body.queue_priority if body else None
    
    try:
        card = service.claim_card(moderator_id=moderator_id, queue_priority=queue_priority)
    except ValueError as e:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "CONFLICT",
                "message": str(e)
            }
        )
    
    if not card:
        # ✅ Пустая очередь → 204 No Content
        return Response(status_code=204)
    
    return card