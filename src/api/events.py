from fastapi import APIRouter, Depends, Header
from sqlalchemy.orm import Session
from src.database import get_db
from src.schemas.event import ProductEventRequest
from src.services.event_service import EventService
from src.dependencies.service_key import verify_service_key
from typing import Optional


router = APIRouter(prefix="/api/v1/events", tags=["Events"])


@router.post("/product")
def handle_product_event(
    payload: ProductEventRequest,
    db: Session = Depends(get_db),
    _: bool = Depends(verify_service_key)
):
    service = EventService(db)
    result = service.handle_product_event(payload.model_dump())
    return {"accepted": True}
