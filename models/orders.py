# models/orders.py
from pydantic import BaseModel

from models.history import HistoryDetailResponse


class AwaitingOrdersResponse(BaseModel):
    items: list[HistoryDetailResponse]
    count: int
