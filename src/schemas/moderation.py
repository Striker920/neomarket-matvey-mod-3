from pydantic import BaseModel
from typing import Optional


class GetNextRequest(BaseModel):
    queueId: Optional[int] = None
