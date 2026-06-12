from pydantic import BaseModel
from datetime import datetime


class ProductEventRequest(BaseModel):
    product_id: str
    seller_id: str
    event: str
    date: datetime
