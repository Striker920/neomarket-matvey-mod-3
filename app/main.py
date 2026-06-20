from fastapi import FastAPI
from app.api.v1 import moderation_service

app = FastAPI(title="NeoMarket Moderation Service", version="1.0.0")

app.include_router(moderation_service.tickets_router, prefix="/api/v1/tickets", tags=["Tickets"])
app.include_router(moderation_service.queue_router, prefix="/api/v1/queue", tags=["Queue"])
app.include_router(moderation_service.b2b_events_router, prefix="/api/v1/b2b", tags=["B2B Events"])

@app.get("/")
def root():
    return {"message": "Moderation Service is running"}
