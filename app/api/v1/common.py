from fastapi import Request
from fastapi.responses import JSONResponse
from app.core.base import ServiceError
from app.core.config import settings


def error_response(exc: ServiceError) -> JSONResponse:
    """Формирует ответ с ошибкой в плоском формате {code, message}."""
    return JSONResponse(
        status_code=exc.status_code,
        content={"code": exc.code, "message": exc.message}
    )


def get_store(request: Request):
    """Получить store из app.state."""
    return request.app.state.store


def require_service_key(x_service_key: str):
    """Проверка X-Service-Key."""
    if not x_service_key or x_service_key != settings.B2B_SERVICE_KEY:
        raise ServiceError("UNAUTHORIZED", "Missing or invalid X-Service-Key", 401)