# api/routes/orders.py
"""
api/routes/orders.py

A run's reasoning and its order placement are two separate calls, possibly
made from two different places in a frontend at two different times — a
fixture gets analysed, then a user comes back later to decide whether to
actually place the order. This endpoint is that "come back later" view:
every session currently sitting at status "awaiting_order", with the same
full detail (session + bet + logs) as GET /api/history/{session_id}, so a
client can review the reasoning before calling POST /api/fixture/{id}/order.
"""

from fastapi import APIRouter

from service.db import get_sessions_by_status, get_bet_by_session_id, get_logs_for_session
from models.common import SessionOut, BetOut, LogEntryOut
from models.history import HistoryDetailResponse
from models.orders import AwaitingOrdersResponse

router = APIRouter(prefix="/api/orders", tags=["orders"])

AWAITING_STATUS = "awaiting_order"


@router.get("/awaiting", response_model=AwaitingOrdersResponse)
def list_awaiting_orders():
    sessions = get_sessions_by_status(AWAITING_STATUS)

    items = []
    for session in sessions:
        bet = get_bet_by_session_id(session["session_id"])
        if bet is None:
            # Shouldn't happen — a session only reaches awaiting_order once
            # a decision is made and saved — but skip defensively rather
            # than 500 the whole list over one inconsistent row.
            continue
        logs = get_logs_for_session(session["session_id"])
        items.append(HistoryDetailResponse(
            session=SessionOut(**session),
            bet=BetOut(**bet),
            logs=[LogEntryOut(**l) for l in logs],
        ))

    return AwaitingOrdersResponse(items=items, count=len(items))
