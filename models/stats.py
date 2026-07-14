# models/stats.py
from pydantic import BaseModel


class StatsResponse(BaseModel):
    wallet_balance_usd: float
    starting_balance_usd: float
    bets_placed: int
    bets_won: int
    bets_lost: int
    bets_skipped: int
    win_percentage: float | None = None
    roi_percentage: float | None = None
    biggest_profit_usd: float | None = None
    biggest_loss_usd: float | None = None
