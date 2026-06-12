from fastapi import FastAPI
from src.database import Base, engine
from src.exceptions import register_exception_handlers
from src.api import events, moderation

app = FastAPI(title="NeoMarket Moderation Service")

Base.metadata.create_all(bind=engine)

register_exception_handlers(app)

app.include_router(events.router)
app.include_router(moderation.router)


@app.get("/")
def root():
    return {"message": "Moderation Service"}
