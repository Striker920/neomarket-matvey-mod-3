from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from src.database import get_db
from src.schemas.event import IncomingB2BEvent
from src.services.event_service import EventService, DuplicateEventError
from src.config import settings

router = APIRouter(prefix="/api/v1/b2b", tags=["B2B Events"])


def verify_service_key(request: Request):
    """
    Межсервисная авторизация по X-Service-Key.
    """
    x_service_key = request.headers.get("X-Service-Key")
    if not x_service_key or x_service_key != settings.B2B_SERVICE_KEY:
        # ✅ Возвращаем структуру без 'detail' — соответствует кастомному обработчику
        raise HTTPException(
            status_code=401,
            detail={
                "code": "UNAUTHORIZED",
                "message": "Missing or invalid X-Service-Key"
            }
        )


@router.post("/events", status_code=202)
def receive_product_event(
    event: IncomingB2BEvent,
    db: Session = Depends(get_db),
    _: None = Depends(verify_service_key),
):
    """
    Приём событий о товаре от B2B.
    """
    service = EventService(db)
    
    try:
        result = service.process_event(event)
        return result
    except DuplicateEventError as e:
        # ✅ Возвращаем структуру без 'detail' — соответствует кастомному обработчику
        raise HTTPException(
            status_code=409,
            detail={
                "code": "DUPLICATE_EVENT",
                "message": f"Event with idempotency_key '{e.idempotency_key}' already processed",
                "idempotency_key": e.idempotency_key,
                "product_id": e.product_id,
            }
        )