# models/settlement.py
from pydantic import BaseModel


class SettlementResult(BaseModel):
    bet_id: str
    status: str  # "still_pending" | "settled"
    actual_outcome: str | None = None
    pnl: float | None = None


class SettlementRunResponse(BaseModel):
    checked: int
    settled: int
    results: list[SettlementResult]
