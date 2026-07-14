# api/routes/stats.py
from fastapi import APIRouter

from config.settings import settings
from service.db import get_all_bets
from service.wallet import get_available_balance
from models.stats import StatsResponse

router = APIRouter(prefix="/api/agent", tags=["stats"])


@router.get("/stats", response_model=StatsResponse)
def get_stats():
    bets = get_all_bets()

    placed = [b for b in bets if b.get("decision") in ("home", "draw", "away") and b.get("order_id")]
    settled = [b for b in placed if b.get("actual_outcome") is not None]
    won = [b for b in settled if (b.get("pnl") or 0) > 0]
    lost = [b for b in settled if (b.get("pnl") or 0) <= 0]
    skipped = [b for b in bets if b.get("decision") == "skip"]

    win_percentage = round(len(won) / len(settled) * 100, 1) if settled else None

    total_pnl = sum(b["pnl"] for b in settled)
    total_stake = sum(b["stake_usd"] for b in settled if b.get("stake_usd"))
    roi_percentage = round(total_pnl / total_stake * 100, 1) if total_stake else None

    settled_pnls = [b["pnl"] for b in settled]
    biggest_profit = max(settled_pnls) if settled_pnls else None
    biggest_loss = min(settled_pnls) if settled_pnls else None

    return StatsResponse(
        wallet_balance_usd=round(get_available_balance(), 2),
        starting_balance_usd=settings.STARTING_BALANCE_USD,
        bets_placed=len(placed),
        bets_won=len(won),
        bets_lost=len(lost),
        bets_skipped=len(skipped),
        win_percentage=win_percentage,
        roi_percentage=roi_percentage,
        biggest_profit_usd=biggest_profit,
        biggest_loss_usd=biggest_loss,
    )
