# models/fixture.py
from typing import Literal

from pydantic import BaseModel

from models.common import SessionOut, BetOut, LogEntryOut


class FixtureCreateRequest(BaseModel):
    home: str
    away: str
    stage: str
    agent: Literal["multi-agent", "unified"]
    # Kept as a raw string, not datetime — best-effort disambiguation hint for
    # rematches, never a hard validation requirement. See find_fixture_by_teams.
    kick_off_time: str | None = None


class FixtureCreateResponse(BaseModel):
    session_id: str


class FixtureStatusResponse(BaseModel):
    session: SessionOut
    bet: BetOut | None = None
    logs: list[LogEntryOut] = []


class OrderResponse(BaseModel):
    status: str
    decision: str | None = None
    stake_usd: float | None = None
    order_id: str | None = None
    order_status: str | None = None
    fill_price: float | None = None
    reason: str | None = None
