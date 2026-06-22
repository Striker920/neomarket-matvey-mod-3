from fastapi import FastAPI
from src.database import Base, engine
from src.exceptions import register_exception_handlers
from src.api import events, moderation, queue, blocking_reasons

# Импортируем модели ПЕРЕД create_all
from src.models import event, moderation_card, blocking_reason

app = FastAPI(title="NeoMarket Moderation Service")

Base.metadata.create_all(bind=engine)

register_exception_handlers(app)

app.include_router(events.router)
app.include_router(moderation.router)
app.include_router(queue.router)
app.include_router(blocking_reasons.router)  # ✅ Добавлено


@app.get("/")
def root():
    return {"message": "Moderation Service"}