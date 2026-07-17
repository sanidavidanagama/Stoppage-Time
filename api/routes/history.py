# api/routes/history.py
"""
api/routes/history.py

History is scoped to concluded, ordered bets only (session status
"completed"). Anything still in flight lives at GET /api/fixture/{id};
decided-but-not-yet-ordered bets live at GET /api/orders/awaiting.
"""

from fastapi import APIRouter, HTTPException, Query

from service.db import get_bets_by_session_status, get_session, get_bet_by_session_id, get_logs_for_bet
from models.common import SessionOut, BetOut, LogEntryOut
from models.history import HistoryListResponse, HistoryDetailResponse

router = APIRouter(prefix="/api/history", tags=["history"])

HISTORY_STATUS = "completed"


@router.get("", response_model=HistoryListResponse)
def list_history(limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0)):
    rows, total = get_bets_by_session_status(HISTORY_STATUS, limit=limit, offset=offset)
    return HistoryListResponse(items=[BetOut(**r) for r in rows], limit=limit, offset=offset, total=total)


@router.get("/{session_id}", response_model=HistoryDetailResponse)
def get_history_detail(session_id: str):
    session = get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="session not found")

    if session.get("status") != HISTORY_STATUS:
        raise HTTPException(
            status_code=404,
            detail=f"session is not completed (status: {session.get('status')}) — "
                   f"use GET /api/fixture/{{id}} for in-flight status or "
                   f"GET /api/orders/awaiting for orders awaiting confirmation",
        )

    bet = get_bet_by_session_id(session_id)
    if bet is None:
        raise HTTPException(status_code=404, detail="no bet recorded for this session")

    logs = get_logs_for_bet(bet["id"])

    return HistoryDetailResponse(
        session=SessionOut(**session),
        bet=BetOut(**bet),
        logs=[LogEntryOut(**l) for l in logs],
    )
