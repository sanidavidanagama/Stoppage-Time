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

import httpx
from fastapi import APIRouter, Depends, HTTPException

from api.deps import get_current_admin
from service.db import (
    get_sessions_by_status, get_session, get_bet_by_session_id,
    get_logs_for_session, delete_session_cascade,
)
from models.common import SessionOut, BetOut, LogEntryOut
from models.history import HistoryDetailResponse
from models.orders import AwaitingOrdersResponse, DeleteAwaitingOrderResponse

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


@router.delete("/awaiting/{session_id}", response_model=DeleteAwaitingOrderResponse)
def delete_awaiting_order(session_id: str, admin: str = Depends(get_current_admin)):
    """Delete an awaiting_order session and everything temporary that was
    created for it — its agent_logs rows, its agent_bets row, and finally
    the session row itself, strictly in that order (see
    service/db.py::delete_session_cascade for why the order matters).
    Deliberately scoped to awaiting_order only — this is cleanup for a
    decision nobody acted on, not a general "delete any session" endpoint,
    so anything else refuses with 409 rather than silently deleting it."""
    session = get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="session not found")

    if session.get("status") != AWAITING_STATUS:
        raise HTTPException(
            status_code=409,
            detail=f"session is not awaiting_order (status: {session.get('status')}) — "
                   f"this endpoint only deletes awaiting orders, refusing to touch anything else",
        )

    try:
        result = delete_session_cascade(session_id)
    except httpx.HTTPStatusError as e:
        raise HTTPException(
            status_code=500,
            detail=f"delete failed partway through: {e.response.text}",
        )

    return DeleteAwaitingOrderResponse(session_id=session_id, **result)
