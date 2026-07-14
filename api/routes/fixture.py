# api/routes/fixture.py
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import JSONResponse

from api.deps import get_current_admin
from agents.unified_agent import run_unified_agent
from workflows.run_pipeline import run as run_multi_agent_pipeline
from service.db import get_session, get_bet_by_session_id, get_logs_for_session
from service.order_execution import execute_order
from models.common import SessionOut, BetOut, LogEntryOut
from models.fixture import FixtureCreateRequest, FixtureCreateResponse, FixtureStatusResponse, OrderResponse

router = APIRouter(prefix="/api/fixture", tags=["fixture"])


@router.post("", response_model=FixtureCreateResponse)
def create_fixture(payload: FixtureCreateRequest, background_tasks: BackgroundTasks):
    prefix = "unified" if payload.agent == "unified" else "live"
    session_id = f"{prefix}-{uuid.uuid4().hex[:8]}"

    if payload.agent == "unified":
        background_tasks.add_task(
            run_unified_agent,
            home_name=payload.home, away_name=payload.away, round_info=payload.stage,
            session_id=session_id, kickoff_hint=payload.kick_off_time,
        )
    else:
        background_tasks.add_task(
            run_multi_agent_pipeline,
            home=payload.home, away=payload.away, round_info=payload.stage,
            session_id=session_id, kickoff_hint=payload.kick_off_time,
        )

    return FixtureCreateResponse(session_id=session_id)


@router.get("/{session_id}", response_model=FixtureStatusResponse)
def get_fixture_status(session_id: str):
    session = get_session(session_id)
    if session is None:
        # May just be the ~100ms window before the background task's
        # create_session() call lands — client should tolerate one retry.
        raise HTTPException(status_code=404, detail="session not found")

    bet = get_bet_by_session_id(session_id)
    logs = get_logs_for_session(session_id)

    return FixtureStatusResponse(
        session=SessionOut(**session),
        bet=BetOut(**bet) if bet else None,
        logs=[LogEntryOut(**l) for l in logs],
    )


def _http_status_for(result: dict) -> int:
    if result.get("status") in ("completed", "already_ordered"):
        return 200
    reason = result.get("reason") or ""
    if reason == "bet_not_found":
        return 404
    if reason.startswith("nothing_to_order"):
        return 409
    return 502


@router.post("/{session_id}/order", response_model=OrderResponse)
def place_order_route(session_id: str, admin: str = Depends(get_current_admin)):
    session = get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="session not found")

    bet = get_bet_by_session_id(session_id)
    if bet is None:
        return JSONResponse(
            status_code=409,
            content=OrderResponse(status="error", reason="nothing_to_order_no_bet_yet").model_dump(),
        )

    result = execute_order(bet["id"])
    body = OrderResponse(
        status=result.get("status", "error"),
        decision=result.get("decision"),
        stake_usd=result.get("stake_usd"),
        order_id=result.get("order_id"),
        order_status=result.get("order_status"),
        fill_price=result.get("fill_price"),
        reason=result.get("reason"),
    )
    return JSONResponse(status_code=_http_status_for(result), content=body.model_dump())
