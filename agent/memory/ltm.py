"""
agent/memory/ltm.py

Long Term Memory (LTM).
Persists bet history to Supabase.
Read before each session to give context from past bets.
Updated after each bet resolves.
"""

from __future__ import annotations
import json
import uuid
from datetime import datetime, timezone
from config import settings
from supabase import create_client

# Lazily initialised so the module imports cleanly when credentials are absent
# (e.g. test runs).  All internal helpers call _client() instead of _sb directly,
# but _sb is the monkeypatch target used by tests.
_sb = None


def _client():
    global _sb
    if _sb is None:
        _sb = create_client(settings.ST_SUPABASE_URL, settings.ST_SUPABASE_SECRET_KEY)
    return _sb


# --- Helpers -----------------------------------------------------------------

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# --- Write -------------------------------------------------------------------

def save_bet(
    session_id:        str,
    fixture_name:      str,
    home_team:         str,
    away_team:         str,
    predicted_outcome: str,
    agent_probability: float,
    confidence_level:  str,
    should_bet:        bool,
    bet_outcome:       str | None,
    bet_direction:     str | None,
    bet_size_usdc:     float | None,
    edge_pp:           float | None,
    signals_used:      list[str],
    rationale:         str,
    kickoff:           str  = "",
    stage:             str  = "",
    ml_home_prob:      float | None = None,
    ml_away_prob:      float | None = None,
    ml_draw_prob:      float | None = None,
    bk_home_prob:      float | None = None,
    bk_away_prob:      float | None = None,
    bk_draw_prob:      float | None = None,
    pm_home_prob:      float | None = None,
    pm_away_prob:      float | None = None,
    pm_draw_prob:      float | None = None,
    ml_market_gap:     float | None = None,
    tool_calls_made:   int = 0,
    home_code:         str = "",
    away_code:         str = "",
) -> str:
    """
    Save a bet decision to LTM.
    Called immediately after the agent makes a decision.
    actual_outcome, pnl, won are filled in later by update_outcome().

    Returns the bet id.
    """
    bet_id = str(uuid.uuid4())
    record: dict = {
        "id":                bet_id,
        "session_id":        session_id,
        "created_at":        _now(),
        "fixture_name":      fixture_name,
        "kickoff":           kickoff,
        "stage":             stage,
        "home_team":         home_team,
        "away_team":         away_team,
        "ml_home_prob":      ml_home_prob,
        "ml_away_prob":      ml_away_prob,
        "ml_draw_prob":      ml_draw_prob,
        "bk_home_prob":      bk_home_prob,
        "bk_away_prob":      bk_away_prob,
        "bk_draw_prob":      bk_draw_prob,
        "pm_home_prob":      pm_home_prob,
        "pm_away_prob":      pm_away_prob,
        "pm_draw_prob":      pm_draw_prob,
        "ml_market_gap":     ml_market_gap,
        "predicted_outcome": predicted_outcome,
        "agent_probability": agent_probability,
        "confidence_level":  confidence_level,
        "should_bet":        int(should_bet),
        "bet_outcome":       bet_outcome,
        "bet_direction":     bet_direction,
        "bet_size_usdc":     bet_size_usdc,
        "edge_pp":           edge_pp,
        "signals_used":      json.dumps(signals_used),
        "tool_calls_made":   tool_calls_made,
        "rationale":         rationale,
        "home_code":         home_code,
        "away_code":         away_code,
    }
    if not should_bet:
        record["won"] = "no_bet"
        record["actual_outcome"] = "skip"
        record["bet_outcome"] = "skip"
        record["bet_size_usdc"] = 0
        record["pnl"] = 0
    _client().table("bets").insert(record).execute()
    return bet_id


def update_outcome(bet_id: str, actual_outcome: str, pnl: float) -> None:
    """
    Update a bet with the actual match outcome and P&L.
    Called after the match result is known.

    Args:
        bet_id:         the id returned by save_bet()
        actual_outcome: "home" | "draw" | "away"
        pnl:            profit/loss in USDC
    """
    res = _client().table("bets").select("predicted_outcome").eq("id", bet_id).execute()
    if not res.data:
        return
    won = "won" if res.data[0]["predicted_outcome"] == actual_outcome else "lost"
    _client().table("bets").update({
        "actual_outcome": actual_outcome,
        "pnl":            pnl,
        "won":            won,
    }).eq("id", bet_id).execute()


# --- Read --------------------------------------------------------------------

def get_recent_bets(limit: int = 10) -> list[dict]:
    """
    Fetch the most recent N bets.
    Used to populate LTM context for the agent.
    """
    res = (
        _client().table("bets")
        .select("*")
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    return res.data or []


def get_similar_bets(
    ml_market_gap: float,
    gap_tolerance: float = 10.0,
    limit: int = 5,
) -> list[dict]:
    """
    Fetch past bets where the ML vs market gap was similar.
    Helps the agent understand how similar situations played out.
    ABS() is unavailable in PostgREST, so gap filtering is done in Python.
    """
    res = _client().table("bets").select("*").execute()
    rows = [
        r for r in (res.data or [])
        if r.get("ml_market_gap") is not None
        and r.get("won") in ("won", "lost")
        and abs(r["ml_market_gap"] - ml_market_gap) <= gap_tolerance
    ]
    rows.sort(key=lambda r: r["created_at"], reverse=True)
    return rows[:limit]


def get_agent_stats() -> dict | None:
    """
    Compute agent performance stats from the bets table.
    Returns None when no bets exist.
    """
    res = _client().table("bets").select("*").eq("should_bet", 1).execute()
    rows = res.data or []
    if not rows:
        return None

    resolved     = [r for r in rows if r.get("won") in ("won", "lost")]
    total_bets   = len(resolved)
    winning_bets = sum(1 for r in resolved if r["won"] == "won")
    losing_bets  = total_bets - winning_bets
    total_pnl    = sum(r["pnl"] or 0.0 for r in resolved)
    win_rate     = winning_bets / total_bets if total_bets else 0.0
    edges        = [r["edge_pp"] for r in rows if r.get("edge_pp") is not None]
    avg_edge_pp  = sum(edges) / len(edges) if edges else 0.0

    return {
        "total_bets":   total_bets,
        "winning_bets": winning_bets,
        "losing_bets":  losing_bets,
        "total_pnl":    total_pnl,
        "win_rate":     win_rate,
        "avg_edge_pp":  avg_edge_pp,
    }


def get_ltm_context(ml_market_gap: float | None = None) -> str:
    """
    Build a plain text LTM summary for the agent.
    Includes recent bets + similar past situations + overall stats.
    """
    lines = ["--- Long Term Memory ---\n"]

    bankroll = get_bankroll_summary()
    lines.append(
        f"Bankroll:\n"
        f"  Starting balance : ${bankroll['starting_balance']:.2f}\n"
        f"  Current balance  : ${bankroll['current_balance']:.2f}\n"
        f"  Total P&L        : {bankroll['total_pnl']:+.2f} USDC\n"
        f"  Total wagered    : ${bankroll['total_wagered']:.2f}\n"
        f"  Largest loss     : ${bankroll['largest_loss']:.2f}\n"
        f"  Drawdown         : {bankroll['drawdown_pct']}%\n"
        f"  W/L              : {bankroll['wins']}W / {bankroll['losses']}L\n"
    )

    stats = get_agent_stats()
    if stats and stats["total_bets"] > 0:
        lines.append(
            f"Overall: {stats['total_bets']} bets | "
            f"win rate {stats['win_rate']:.1%} | "
            f"avg edge {stats['avg_edge_pp']:.1f}pp\n"
        )

    recent = get_recent_bets(limit=5)
    if recent:
        lines.append("Last 5 bets:")
        for b in recent:
            won_str = {"won": "WON", "lost": "LOST", "no_bet": "NO BET", None: "PENDING"}.get(b["won"], "?")
            size    = f"${b['bet_size_usdc']:.2f}" if b["bet_size_usdc"] else "skip"
            lines.append(
                f"  {b['fixture_name']} | predicted={b['predicted_outcome']} "
                f"| bet={size} | {won_str} | P&L={b['pnl'] or 'pending'} "
                f"| edge={b['edge_pp']}pp"
            )
        lines.append("")

    if ml_market_gap is not None:
        similar = get_similar_bets(ml_market_gap)
        if similar:
            lines.append(
                f"Past bets with similar ML/market gap (~{ml_market_gap:.0f}pp):"
            )
            for b in similar:
                won_str = {"won": "WON", "lost": "LOST"}.get(b["won"], "?")
                lines.append(
                    f"  {b['fixture_name']} | {won_str} | "
                    f"P&L={b['pnl']:+.2f}"
                )
            lines.append("")

    return "\n".join(lines)


def get_active_bets() -> list[dict]:
    """Return pending bets (should_bet=1, won IS NULL) ordered by kickoff."""
    res = _client().table("bets").select("*").eq("should_bet", 1).execute()
    rows = [r for r in (res.data or []) if r.get("won") is None]
    rows.sort(key=lambda r: r.get("kickoff") or "")
    return rows


def get_all_orders(limit: int = 50) -> list[dict]:
    """Return all entries ordered by created_at DESC (includes no-bets)."""
    res = (
        _client().table("bets")
        .select("*")
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    return res.data or []


def get_balance_map(starting_balance: float = 100.0) -> dict:
    """
    Compute the wallet balance immediately after each should_bet=1 bet was placed.
    Returns dict mapping bet_id -> balance_after.
    """
    res = (
        _client().table("bets")
        .select("id, created_at, bet_size_usdc, won, pnl")
        .eq("should_bet", 1)
        .order("created_at")
        .execute()
    )
    rows = res.data or []

    balance = starting_balance
    result: dict = {}
    for row in rows:
        size          = row["bet_size_usdc"] or 0.0
        balance_after = round(balance - size, 2)
        result[row["id"]] = balance_after
        if row.get("won") in ("won", "lost"):
            balance = round(balance_after + size + (row["pnl"] or 0.0), 2)
        else:
            balance = balance_after
    return result


def already_bet(session_id: str) -> bool:
    """Return True if a bet record already exists for this session_id."""
    res = (
        _client().table("bets")
        .select("id")
        .eq("session_id", session_id)
        .execute()
    )
    return len(res.data) > 0


def get_bankroll_summary(starting_balance: float = 100.0) -> dict:
    """
    Compute current bankroll state from all resolved bets.
    """
    res = (
        _client().table("bets")
        .select("bet_size_usdc, pnl, won")
        .eq("should_bet", 1)
        .execute()
    )
    rows = res.data or []

    total_wagered = sum(r["bet_size_usdc"] or 0.0 for r in rows)
    pnl_values    = [r["pnl"] for r in rows if r.get("pnl") is not None]
    total_pnl     = sum(pnl_values)
    largest_loss  = min(pnl_values) if pnl_values else 0.0
    wins          = sum(1 for r in rows if r.get("won") == "won")
    losses        = sum(1 for r in rows if r.get("won") == "lost")

    current_balance = round(starting_balance + total_pnl, 2)
    peak_balance    = max(starting_balance, current_balance)
    drawdown        = round((peak_balance - current_balance) / peak_balance * 100, 1)

    return {
        "starting_balance": starting_balance,
        "total_wagered":    round(total_wagered, 2),
        "total_pnl":        round(total_pnl, 2),
        "current_balance":  current_balance,
        "largest_loss":     round(largest_loss, 2),
        "drawdown_pct":     drawdown,
        "wins":             wins,
        "losses":           losses,
    }
