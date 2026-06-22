from datetime import datetime, timezone


class ServiceError(Exception):
    """Доменная ошибка с кодом и сообщением."""
    
    def __init__(self, code: str, message: str, status_code: int = 400):
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


def utcnow() -> datetime:
    """Текущее время в UTC."""
    return datetime.now(timezone.utc)


def iso(dt: datetime) -> str:
    """Форматирование datetime в ISO 8601."""
    if dt is None:
        return None
    return dt.isoformat()