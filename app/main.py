from fastapi import FastAPI
from app.api.v1.moderation_service import (
    tickets_router,
    queue_router,
    b2b_events_router,
    blocking_reasons_router
)
from app.core.store import NeoMarketStore
from app.infrastructure.config.config import APP_CONFIG

app = FastAPI(title="NeoMarket Moderation Service", version="1.0.0")

store = NeoMarketStore()
store.blocking_reasons = [
    {'id': 'reason-hard-1', 'name': 'Counterfeit', 'hard_block': True, 'is_active': True},
    {'id': 'reason-soft-1', 'name': 'Minor issue', 'hard_block': False, 'is_active': True},
]
app.state.store = store

app.include_router(tickets_router, prefix="/api/v1/tickets", tags=["Tickets"])
app.include_router(queue_router, prefix="/api/v1/queue", tags=["Queue"])
app.include_router(b2b_events_router, prefix="/api/v1/b2b", tags=["B2B Events"])
app.include_router(blocking_reasons_router, prefix="/api/v1/blocking-reasons", tags=["Blocking Reasons"])

@app.get("/")
def root():
    return {"message": "Moderation Service is running"}
