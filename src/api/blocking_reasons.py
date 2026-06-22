from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session
from typing import List
from src.database import get_db
from src.services.blocking_reason_service import BlockingReasonService, ReferencedReasonError
from src.schemas.blocking_reason import (
    BlockingReasonResponse,
    BlockingReasonCreateRequest,
    BlockingReasonUpdateRequest,
)

router = APIRouter(prefix="/api/v1", tags=["Blocking Reasons"])


@router.get("/product-blocking-reasons", response_model=List[BlockingReasonResponse])
def list_active_reasons(
    db: Session = Depends(get_db),
):
    """
    Получить список активных причин блокировки.
    
    Возвращает только is_active=True.
    """
    service = BlockingReasonService(db)
    return service.list_active()


@router.post("/product-blocking-reasons", response_model=BlockingReasonResponse, status_code=201)
def create_reason(
    data: BlockingReasonCreateRequest,
    db: Session = Depends(get_db),
):
    """Создать новую причину блокировки (для админки)."""
    service = BlockingReasonService(db)
    return service.create(data)


@router.put("/product-blocking-reasons/{reason_id}", response_model=BlockingReasonResponse)
def update_reason(
    reason_id: str,
    data: BlockingReasonUpdateRequest,
    db: Session = Depends(get_db),
):
    """Обновить причину блокировки (для админки)."""
    service = BlockingReasonService(db)
    reason = service.update(reason_id, data)
    if not reason:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "NOT_FOUND",
                "message": f"Blocking reason {reason_id} not found"
            }
        )
    return reason


@router.delete("/product-blocking-reasons/{reason_id}", status_code=204)
def delete_reason(
    reason_id: str,
    db: Session = Depends(get_db),
):
    """
    Удалить причину блокировки (мягкая деактивация).
    
    Если на причину ссылаются карточки модерации — 409 Conflict.
    """
    service = BlockingReasonService(db)
    try:
        success = service.delete(reason_id)
    except ReferencedReasonError as e:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "REFERENCED",
                "message": str(e),
                "reason_id": e.reason_id,
                "cards_count": e.cards_count,
            }
        )
    
    if not success:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "NOT_FOUND",
                "message": f"Blocking reason {reason_id} not found"
            }
        )
    
    return Response(status_code=204)