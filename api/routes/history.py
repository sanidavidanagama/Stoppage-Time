# api/routes/history.py
from fastapi import APIRouter, HTTPException, Query

from service.db import get_bets_page, get_session, get_bet_by_session_id, get_logs_for_bet
from models.common import SessionOut, BetOut, LogEntryOut
from models.history import HistoryListResponse, HistoryDetailResponse

router = APIRouter(prefix="/api/history", tags=["history"])


@router.get("", response_model=HistoryListResponse)
def list_history(limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0)):
    rows, total = get_bets_page(limit=limit, offset=offset)
    return HistoryListResponse(items=[BetOut(**r) for r in rows], limit=limit, offset=offset, total=total)


@router.get("/{session_id}", response_model=HistoryDetailResponse)
def get_history_detail(session_id: str):
    session = get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="session not found")

    bet = get_bet_by_session_id(session_id)
    if bet is None:
        # History implies something concluded — the in-flight case is
        # what GET /api/fixture/{session_id} is for.
        raise HTTPException(status_code=404, detail="no bet recorded for this session yet")

    logs = get_logs_for_bet(bet["id"])

    return HistoryDetailResponse(
        session=SessionOut(**session),
        bet=BetOut(**bet),
        logs=[LogEntryOut(**l) for l in logs],
    )
