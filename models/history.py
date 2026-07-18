# models/history.py
from pydantic import BaseModel

from models.common import SessionOut, BetOut, LogEntryOut


class HistoryListResponse(BaseModel):
    items: list[BetOut]
    limit: int
    offset: int
    total: int


class HistoryDetailResponse(BaseModel):
    session: SessionOut
    bet: BetOut
    logs: list[LogEntryOut] = []
