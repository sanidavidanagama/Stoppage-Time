# models/orders.py
from pydantic import BaseModel

from models.history import HistoryDetailResponse


class AwaitingOrdersResponse(BaseModel):
    items: list[HistoryDetailResponse]
    count: int


class DeleteAwaitingOrderResponse(BaseModel):
    session_id: str
    logs_deleted: int
    bets_deleted: int
    session_deleted: bool
