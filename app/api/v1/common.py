from typing import Optional
from fastapi import Request
from fastapi.responses import JSONResponse
from app.core.base import ServiceError
from app.core.store import NeoMarketStore
from app.infrastructure.config.config import APP_CONFIG


def get_store(request: Request) -> NeoMarketStore:
    return request.app.state.store


def require_service_key(x_service_key: Optional[str]) -> None:
    if x_service_key != APP_CONFIG.B2B_SERVICE_KEY:
        raise ServiceError('UNAUTHORIZED', 'Invalid or missing service key', 401)


def error_response(exc: ServiceError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={
            'detail': {
                'code': exc.code,
                'message': exc.message
            }
        }
    )
