from datetime import datetime, timezone

from fastapi import APIRouter

router = APIRouter(tags=["public"])


@router.get("/stats")
async def public_stats():
    """Public performance summary. No auth required."""
    from agent.memory.ltm import get_agent_stats, get_bankroll_summary
    from config import settings
    from supabase import create_client

    stats = get_agent_stats()
    bankroll = get_bankroll_summary()

    sb = create_client(settings.ST_SUPABASE_URL, settings.ST_SUPABASE_SECRET_KEY)

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
    next_scheduled_run = pending.data[0]["scheduled_run_time"] if pending.data else None

    return {
        "bets_won": stats["winning_bets"] if stats else 0,
        "bets_lost": (stats["total_bets"] - stats["winning_bets"]) if stats else 0,
        "win_rate": round(stats["win_rate"] * 100, 1) if stats else 0.0,
        "total_pnl": bankroll["total_pnl"],
        "current_balance": bankroll["current_balance"],
        "agent_status": agent_status,
        "next_scheduled_run": next_scheduled_run,
    }
