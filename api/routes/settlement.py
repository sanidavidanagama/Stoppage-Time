# api/routes/settlement.py
"""
api/routes/settlement.py

Checks every unsettled bet against Polymarket's real settlement data and
records the actual outcome + P&L on the matching agent_bets row. No money
moves here — this only records facts that already happened on-chain.
"""

from fastapi import APIRouter

from service.settlement import settle_all_pending
from models.settlement import SettlementResult, SettlementRunResponse

router = APIRouter(prefix="/api/settlement", tags=["settlement"])


@router.post("/run", response_model=SettlementRunResponse)
def run_settlement():
    results = settle_all_pending()
    settled = [r for r in results if r.get("status") == "settled"]
    return SettlementRunResponse(
        checked=len(results),
        settled=len(settled),
        results=[SettlementResult(**r) for r in results],
    )
