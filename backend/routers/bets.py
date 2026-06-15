from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from backend.auth import get_current_user

router = APIRouter(tags=["bets"], dependencies=[Depends(get_current_user)])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _derive_result(won) -> str:
    if won is None:
        return "pending"
    if won == "no_bet":
        return "no_bet"
    return "won" if won == "won" else "lost"


def _market_price_for_prediction(row: dict) -> float | None:
    outcome = row.get("predicted_outcome")
    mapping = {
        "home": row.get("pm_home_prob"),
        "away": row.get("pm_away_prob"),
        "draw": row.get("pm_draw_prob"),
    }
    return mapping.get(outcome)


def _format_next_run_human(seconds: int | None) -> str | None:
    if seconds is None:
        return None
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        return f"{seconds // 60} min"
    h = seconds // 3600
    m = (seconds % 3600) // 60
    return f"{h}h {m}min" if m else f"{h}h"


# ---------------------------------------------------------------------------
# GET /api/stats
# ---------------------------------------------------------------------------

@router.get("/stats")
async def extended_stats():
    from datetime import datetime, timezone

    from agent.memory.ltm import get_agent_stats, get_bankroll_summary
    from config import settings
    from supabase import create_client

    stats = get_agent_stats()
    bankroll = get_bankroll_summary()

    sb = create_client(settings.ST_SUPABASE_URL, settings.ST_SUPABASE_SECRET_KEY)

    # skipped bets (won="no_bet")
    skipped_res = sb.table("bets").select("id", count="exact").eq("won", "no_bet").execute()
    skipped_bets = skipped_res.count or 0

    # highest profit
    profit_res = (
        sb.table("bets")
        .select("pnl")
        .eq("should_bet", 1)
        .not_.is_("pnl", "null")
        .order("pnl", desc=True)
        .limit(1)
        .execute()
    )
    highest_profit = profit_res.data[0]["pnl"] if profit_res.data else 0.0

    # agent status + next run (graceful if match_queue table not yet created)
    agent_status = "inactive"
    next_run_seconds = None
    next_run_human = None
    try:
        running = sb.table("match_queue").select("id").eq("status", "running").execute()
        agent_status = "active" if running.data else "inactive"

        pending = (
            sb.table("match_queue")
            .select("scheduled_run_time")
            .eq("status", "pending")
            .order("scheduled_run_time")
            .limit(1)
            .execute()
        )
        if pending.data:
            dt = datetime.fromisoformat(
                pending.data[0]["scheduled_run_time"].replace("Z", "+00:00")
            )
            secs = max(0, int((dt - datetime.now(timezone.utc)).total_seconds()))
            next_run_seconds = secs
            next_run_human = _format_next_run_human(secs)
    except Exception:
        pass  # match_queue table not yet created — return defaults

    return {
        "total_bets": stats["total_bets"] if stats else 0,
        "bets_won": stats["winning_bets"] if stats else 0,
        "bets_lost": stats["losing_bets"] if stats else 0,
        "skipped_bets": skipped_bets,
        "win_percentage": round(stats["win_rate"] * 100, 1) if stats else 0.0,
        "total_pnl": bankroll["total_pnl"],
        "highest_profit": highest_profit,
        "highest_loss": bankroll["largest_loss"],
        "wallet_balance": bankroll["current_balance"],
        "next_run_seconds": next_run_seconds,
        "next_run_human": next_run_human,
        "agent_status": agent_status,
    }


# ---------------------------------------------------------------------------
# GET /api/bets
# ---------------------------------------------------------------------------

@router.get("/bets")
async def list_bets(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    status: str | None = Query(None, description="active | resolved | no_bet"),
):
    from config import settings
    from supabase import create_client

    sb = create_client(settings.ST_SUPABASE_URL, settings.ST_SUPABASE_SECRET_KEY)

    def _apply_filter(q):
        if status == "active":
            return q.eq("should_bet", 1).is_("actual_outcome", "null")
        if status == "resolved":
            return q.eq("should_bet", 1).not_.is_("actual_outcome", "null")
        if status == "no_bet":
            return q.eq("won", "no_bet")
        return q

    # Get total count cheaply before attempting range
    total = _apply_filter(
        sb.table("bets").select("id", count="exact")
    ).execute().count or 0

    offset = (page - 1) * per_page
    total_pages = -(-total // per_page) if total else 0

    if total == 0 or offset >= total:
        return {"data": [], "total": total, "page": page, "per_page": per_page, "total_pages": total_pages}

    cols = (
        "id,home_team,away_team,won,pnl,predicted_outcome,"
        "pm_home_prob,pm_away_prob,pm_draw_prob,edge_pp,bet_size_usdc,actual_outcome"
    )
    res = _apply_filter(
        sb.table("bets").select(cols).order("created_at", desc=True)
    ).range(offset, offset + per_page - 1).execute()

    rows = []
    for row in (res.data or []):
        rows.append({
            "id": row["id"],
            "home": row["home_team"],
            "away": row["away_team"],
            "result": row.get("won"),
            "pnl": row.get("pnl"),
            "agent_prediction": row.get("predicted_outcome"),
            "market_price": _market_price_for_prediction(row),
            "edge": row.get("edge_pp"),
            "stake": row.get("bet_size_usdc"),
            "actual_outcome": row.get("actual_outcome"),
        })

    return {
        "data": rows,
        "total": total,
        "page": page,
        "per_page": per_page,
        "total_pages": total_pages,
    }


# ---------------------------------------------------------------------------
# GET /api/bets/{bet_id}
# ---------------------------------------------------------------------------

@router.get("/bets/{bet_id}")
async def get_bet(bet_id: str):
    from config import settings
    from supabase import create_client

    sb = create_client(settings.ST_SUPABASE_URL, settings.ST_SUPABASE_SECRET_KEY)
    res = sb.table("bets").select("*").eq("id", bet_id).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="Bet not found")
    return res.data[0]


# ---------------------------------------------------------------------------
# GET /api/bets/{bet_id}/logs
# ---------------------------------------------------------------------------

@router.get("/bets/{bet_id}/logs")
async def get_bet_logs(bet_id: str):
    from config import settings
    from supabase import create_client
    from backend.routers.logs import fetch_logs_by_session

    sb = create_client(settings.ST_SUPABASE_URL, settings.ST_SUPABASE_SECRET_KEY)

    bet_res = sb.table("bets").select("session_id").eq("id", bet_id).execute()
    if not bet_res.data:
        raise HTTPException(status_code=404, detail="Bet not found")

    session_id = bet_res.data[0]["session_id"]
    structured = fetch_logs_by_session(sb, session_id)

    return {
        "bet_id": bet_id,
        "session_id": session_id,
        "logs": structured,
    }


# ---------------------------------------------------------------------------
# PUT /api/bets/{bet_id}/outcome
# ---------------------------------------------------------------------------

class OutcomeUpdate(BaseModel):
    actual_outcome: Literal["home", "draw", "away"]
    pnl: float


@router.put("/bets/{bet_id}/outcome")
async def set_bet_outcome(bet_id: str, body: OutcomeUpdate):
    from agent.memory.ltm import update_outcome
    from config import settings
    from supabase import create_client

    sb = create_client(settings.ST_SUPABASE_URL, settings.ST_SUPABASE_SECRET_KEY)
    res = sb.table("bets").select("id").eq("id", bet_id).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="Bet not found")

    update_outcome(bet_id, body.actual_outcome, body.pnl)
    return {"ok": True, "bet_id": bet_id}
