from fastapi import FastAPI
from app.api.v1.moderation_service import (
    tickets_router,
    queue_router,
    b2b_events_router,
    blocking_reasons_router
)
from app.core.store import NeoMarketStore

app = FastAPI(title="NeoMarket Moderation Service")


@app.on_event("startup")
async def startup_event():
    """Инициализация store при старте приложения."""
    app.state.store = NeoMarketStore()


# Подключаем роутеры
app.include_router(tickets_router, prefix="/api/v1/tickets", tags=["Tickets"])
app.include_router(queue_router, prefix="/api/v1/queue", tags=["Queue"])
app.include_router(b2b_events_router, prefix="/api/v1/b2b", tags=["B2B Events"])
app.include_router(blocking_reasons_router, prefix="/api/v1", tags=["Blocking Reasons"])


@app.get("/")
def root():
    return {"message": "Moderation Service is running"}