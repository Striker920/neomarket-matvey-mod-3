from fastapi import APIRouter, Depends, HTTPException, Header
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from src.database import get_db
from src.schemas.moderation import GetNextRequest
from src.services.moderation_service import ModerationService
from src.dependencies.service_key import verify_service_key
from typing import Optional


router = APIRouter(prefix="/api/v1/product-moderation", tags=["Moderation"])


@router.post("/get-next")
def get_next_card(
    request: GetNextRequest,
    db: Session = Depends(get_db),
    _: bool = Depends(verify_service_key),
    x_moderator_id: Optional[str] = Header(None, alias="X-Moderator-Id")
):
    service = ModerationService(db)
    result = service.get_next_card(
        queue_id=request.queueId,
        moderator_id=x_moderator_id
    )

    if result.get("status") == "empty":
        return JSONResponse(status_code=204, content=None)

    if result.get("code") == "INVALID_QUEUE":
        raise HTTPException(status_code=400, detail={"code": result["code"], "message": result["message"]})

    return result
