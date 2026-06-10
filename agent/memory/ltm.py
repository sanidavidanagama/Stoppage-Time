"""
agent/memory/ltm.py

Long Term Memory (LTM).
Persists bet history and agent performance to local SQLite.
Read before each session to give Gemini context from past bets.
Updated after each bet resolves.

Database: bets.db (created automatically on first run)
"""

from __future__ import annotations
import sqlite3
import json
from datetime import datetime, timezone
from pathlib import Path
from config import settings

DB_PATH = Path("bets.db")


# --- Schema ------------------------------------------------------------------

SCHEMA = """
CREATE TABLE IF NOT EXISTS bets (
    id              TEXT PRIMARY KEY,
    session_id      TEXT NOT NULL,
    created_at      TEXT NOT NULL,

    -- Match context
    fixture_name    TEXT NOT NULL,
    kickoff         TEXT,
    stage           TEXT,
    home_team       TEXT NOT NULL,
    away_team       TEXT NOT NULL,

    -- Signals used
    ml_home_prob    REAL,
    ml_away_prob    REAL,
    ml_draw_prob    REAL,
    bk_home_prob    REAL,
    bk_away_prob    REAL,
    bk_draw_prob    REAL,
    pm_home_prob    REAL,
    pm_away_prob    REAL,
    pm_draw_prob    REAL,
    ml_market_gap   REAL,

    -- Agent decision
    predicted_outcome   TEXT,
    agent_probability   REAL,
    confidence_level    TEXT,
    should_bet          INTEGER,
    bet_outcome         TEXT,
    bet_direction       TEXT,
    bet_size_usdc       REAL,
    edge_pp             REAL,
    signals_used        TEXT,   -- JSON list

    -- Result (filled in after match)
    actual_outcome  TEXT,
    pnl             REAL,
    won             INTEGER,    -- 1=yes, 0=no, NULL=pending

    -- Metadata
    tool_calls_made INTEGER DEFAULT 0,
    rationale       TEXT,
    notes           TEXT
);

CREATE TABLE IF NOT EXISTS agent_stats (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    updated_at      TEXT NOT NULL,
    total_bets      INTEGER DEFAULT 0,
    winning_bets    INTEGER DEFAULT 0,
    total_pnl       REAL DEFAULT 0.0,
    win_rate        REAL DEFAULT 0.0,
    avg_edge_pp     REAL DEFAULT 0.0,
    best_signal     TEXT,
    worst_signal    TEXT
);
"""


# --- Connection --------------------------------------------------------------

def _connect() -> sqlite3.Connection:
    """Open a connection and ensure schema exists."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    conn.commit()
    return conn


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
) -> str:
    """
    Save a bet decision to LTM.
    Called immediately after the agent makes a decision.
    actual_outcome, pnl, won are filled in later by update_outcome().

    Returns the bet id.
    """
    import uuid
    bet_id = str(uuid.uuid4())

    with _connect() as conn:
        conn.execute("""
            INSERT INTO bets (
                id, session_id, created_at,
                fixture_name, kickoff, stage, home_team, away_team,
                ml_home_prob, ml_away_prob, ml_draw_prob,
                bk_home_prob, bk_away_prob, bk_draw_prob,
                pm_home_prob, pm_away_prob, pm_draw_prob,
                ml_market_gap,
                predicted_outcome, agent_probability, confidence_level,
                should_bet, bet_outcome, bet_direction,
                bet_size_usdc, edge_pp, signals_used,
                tool_calls_made, rationale
            ) VALUES (
                ?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?
            )
        """, (
            bet_id, session_id, _now(),
            fixture_name, kickoff, stage, home_team, away_team,
            ml_home_prob, ml_away_prob, ml_draw_prob,
            bk_home_prob, bk_away_prob, bk_draw_prob,
            pm_home_prob, pm_away_prob, pm_draw_prob,
            ml_market_gap,
            predicted_outcome, agent_probability, confidence_level,
            int(should_bet), bet_outcome, bet_direction,
            bet_size_usdc, edge_pp, json.dumps(signals_used),
            tool_calls_made, rationale,
        ))

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
    with _connect() as conn:
        row = conn.execute(
            "SELECT predicted_outcome FROM bets WHERE id = ?", (bet_id,)
        ).fetchone()

        if not row:
            return

        won = 1 if row["predicted_outcome"] == actual_outcome else 0

        conn.execute("""
            UPDATE bets
            SET actual_outcome = ?, pnl = ?, won = ?
            WHERE id = ?
        """, (actual_outcome, pnl, won, bet_id))

    _refresh_agent_stats()


# --- Read --------------------------------------------------------------------

def get_recent_bets(limit: int = 10) -> list[dict]:
    """
    Fetch the most recent N bets.
    Used to populate LTM context for Gemini.
    """
    with _connect() as conn:
        rows = conn.execute("""
            SELECT * FROM bets
            ORDER BY created_at DESC
            LIMIT ?
        """, (limit,)).fetchall()

    return [dict(row) for row in rows]


def get_similar_bets(
    ml_market_gap: float,
    gap_tolerance: float = 10.0,
    limit: int = 5,
) -> list[dict]:
    """
    Fetch past bets where the ML vs market gap was similar.
    Helps Gemini understand how similar situations played out.
    """
    with _connect() as conn:
        rows = conn.execute("""
            SELECT * FROM bets
            WHERE ml_market_gap IS NOT NULL
              AND ABS(ml_market_gap - ?) <= ?
              AND won IS NOT NULL
            ORDER BY created_at DESC
            LIMIT ?
        """, (ml_market_gap, gap_tolerance, limit)).fetchall()

    return [dict(row) for row in rows]


def get_agent_stats() -> dict | None:
    """
    Fetch the latest agent performance stats.
    """
    with _connect() as conn:
        row = conn.execute("""
            SELECT * FROM agent_stats
            ORDER BY updated_at DESC
            LIMIT 1
        """).fetchone()

    return dict(row) if row else None


def get_ltm_context(ml_market_gap: float | None = None) -> str:
    """
    Build a plain text LTM summary for Gemini.
    Includes recent bets + similar past situations + overall stats.

    This is what gets fed into the reasoning prompt.
    """
    lines = ["--- Long Term Memory ---\n"]

    # Bankroll
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

    # Agent stats
    stats = get_agent_stats()
    if stats and stats["total_bets"] > 0:
        lines.append(
            f"Overall: {stats['total_bets']} bets | "
            f"win rate {stats['win_rate']:.1%} | "
            f"avg edge {stats['avg_edge_pp']:.1f}pp\n"
        )

    # Recent bets
    recent = get_recent_bets(limit=5)
    if recent:
        lines.append("Last 5 bets:")
        for b in recent:
            won_str = {1: "WON", 0: "LOST", None: "PENDING"}.get(b["won"], "?")
            size    = f"${b['bet_size_usdc']:.2f}" if b["bet_size_usdc"] else "skip"
            lines.append(
                f"  {b['fixture_name']} | predicted={b['predicted_outcome']} "
                f"| bet={size} | {won_str} | P&L={b['pnl'] or 'pending'} "
                f"| edge={b['edge_pp']}pp"
            )
        lines.append("")

    # Similar situations
    if ml_market_gap is not None:
        similar = get_similar_bets(ml_market_gap)
        if similar:
            lines.append(
                f"Past bets with similar ML/market gap (~{ml_market_gap:.0f}pp):"
            )
            for b in similar:
                won_str = {1: "WON", 0: "LOST"}.get(b["won"], "?")
                lines.append(
                    f"  {b['fixture_name']} | {won_str} | "
                    f"P&L={b['pnl']:+.2f}"
                )
            lines.append("")

    return "\n".join(lines)


def get_bankroll_summary(starting_balance: float = 100.0) -> dict:
    """
    Compute current bankroll state from all resolved bets.
    """
    with _connect() as conn:
        row = conn.execute("""
            SELECT
                COALESCE(SUM(bet_size_usdc), 0)        AS total_wagered,
                COALESCE(SUM(CASE WHEN pnl IS NOT NULL
                    THEN pnl ELSE 0 END), 0)           AS total_pnl,
                COALESCE(MIN(pnl), 0)                  AS largest_loss,
                COUNT(CASE WHEN won = 1 THEN 1 END)    AS wins,
                COUNT(CASE WHEN won = 0 THEN 1 END)    AS losses
            FROM bets
            WHERE should_bet = 1
        """).fetchone()

    total_pnl       = row["total_pnl"]
    current_balance = round(starting_balance + total_pnl, 2)
    peak_balance    = max(starting_balance, current_balance)
    drawdown        = round((peak_balance - current_balance) / peak_balance * 100, 1)

    return {
        "starting_balance": starting_balance,
        "total_wagered":    round(row["total_wagered"], 2),
        "total_pnl":        round(total_pnl, 2),
        "current_balance":  current_balance,
        "largest_loss":     round(row["largest_loss"], 2),
        "drawdown_pct":     drawdown,
        "wins":             row["wins"],
        "losses":           row["losses"],
    }

# --- Helpers -----------------------------------------------------------------

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _refresh_agent_stats() -> None:
    """Recompute and store agent performance stats."""
    with _connect() as conn:
        row = conn.execute("""
            SELECT
                COUNT(*)                        AS total_bets,
                SUM(CASE WHEN won=1 THEN 1 END) AS winning_bets,
                SUM(COALESCE(pnl, 0))           AS total_pnl,
                AVG(CASE WHEN won IS NOT NULL
                    THEN CAST(won AS FLOAT) END) AS win_rate,
                AVG(edge_pp)                    AS avg_edge_pp
            FROM bets
            WHERE should_bet = 1
        """).fetchone()

        conn.execute("""
            INSERT INTO agent_stats
                (updated_at, total_bets, winning_bets,
                 total_pnl, win_rate, avg_edge_pp)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            _now(),
            row["total_bets"] or 0,
            row["winning_bets"] or 0,
            row["total_pnl"] or 0.0,
            row["win_rate"] or 0.0,
            row["avg_edge_pp"] or 0.0,
        ))