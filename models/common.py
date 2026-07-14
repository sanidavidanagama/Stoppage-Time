# models/common.py
"""Shared response schemas — a session/bet/log row, as read back from Supabase."""

from pydantic import BaseModel


class SessionOut(BaseModel):
    session_id: str
    created_at: str | None = None
    fixture_name: str | None = None
    home_team: str | None = None
    away_team: str | None = None
    status: str | None = None
    source: str | None = None


class BetOut(BaseModel):
    id: str
    session_id: str
    fixture_id: str | int | None = None
    fixture_name: str | None = None
    home_team: str | None = None
    home_code: str | None = None
    away_team: str | None = None
    away_code: str | None = None
    home_probability: float | None = None
    draw_probability: float | None = None
    away_probability: float | None = None
    confidence: str | None = None
    market_home_price: float | None = None
    market_draw_price: float | None = None
    market_away_price: float | None = None
    edge_pp: float | None = None
    decision: str | None = None
    stake_usd: float | None = None
    bet_reason: str | None = None
    actual_outcome: str | None = None
    pnl: float | None = None
    order_id: str | None = None
    order_status: str | None = None
    fill_price: float | None = None
    created_at: str | None = None
    settled_at: str | None = None


class LogEntryOut(BaseModel):
    id: str
    session_id: str
    step_type: str
    tool: str
    model: str | None = None
    prompt: str | None = None
    response: str | None = None
    created_at: str | None = None
