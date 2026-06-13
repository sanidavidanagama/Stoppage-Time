"""Fixture-scoped human review logging — persisted to Supabase logs table."""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass, field
from threading import Lock

from agent.memory.ltm import _client


_LOCK = Lock()
_ACTIVE_LOGGER: "FixtureLogger | None" = None


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    return slug or "fixture"


def _sanitize_kickoff(kickoff: str | None) -> str:
    if not kickoff:
        return "unknown_time"
    cleaned = kickoff.strip().lower()
    cleaned = cleaned.replace("t", "_").replace("z", "")
    cleaned = cleaned.replace("-", "_").replace(":", "_")
    cleaned = re.sub(r"\.+", "_", cleaned)
    cleaned = re.sub(r"[^a-z0-9_]+", "_", cleaned)
    cleaned = re.sub(r"_+", "_", cleaned).strip("_")
    return cleaned or "unknown_time"


@dataclass
class FixtureLogger:
    reasoning_count: int = 0
    tactics_count: int = 0
    bet_written: bool = False
    metadata: dict = field(default_factory=dict)


def _insert_log(log_type: str, round_num: int, content: str) -> None:
    """Insert one row into the Supabase logs table. Never raises."""
    logger = get_active_logger()
    if logger is None:
        return
    try:
        _client().table("logs").insert({
            "session_id":   logger.metadata.get("session_id"),
            "fixture_name": logger.metadata.get("fixture_name"),
            "log_type":     log_type,
            "round":        round_num,
            "content":      content,
        }).execute()
    except Exception:
        pass


def start_fixture_log(
    home_code:    str,
    away_code:    str,
    kickoff:      str | None,
    fixture_name: str | None = None,
    session_id:   str | None = None,   
) -> FixtureLogger:
    """Create a new fixture logger and register it as the active logger."""
    folder_name = f"{_slugify(home_code)}_vs_{_slugify(away_code)}_{_sanitize_kickoff(kickoff)}"

    logger = FixtureLogger(
        metadata={
            "session_id":   session_id or str(uuid.uuid4()),
            "home_code":    home_code,
            "away_code":    away_code,
            "kickoff":      kickoff,
            "fixture_name": fixture_name or folder_name,
            "folder_name":  folder_name,
        },
    )

    global _ACTIVE_LOGGER
    with _LOCK:
        _ACTIVE_LOGGER = logger
    return logger


def get_active_logger() -> FixtureLogger | None:
    return _ACTIVE_LOGGER


def end_fixture_log() -> None:
    global _ACTIVE_LOGGER
    with _LOCK:
        _ACTIVE_LOGGER = None


def log_reasoning(prompt_text: str, response_text: str) -> None:
    logger = get_active_logger()
    if logger is None:
        return
    logger.reasoning_count += 1
    _insert_log("reasoning_prompt",   logger.reasoning_count, prompt_text)
    _insert_log("reasoning_response", logger.reasoning_count, response_text)


def log_bet(prompt_text: str, response_text: str) -> None:
    logger = get_active_logger()
    if logger is None:
        return
    _insert_log("bet_prompt",   1, prompt_text)
    _insert_log("bet_response", 1, response_text)


def log_tactics(prompt_text: str, response_text: str) -> None:
    logger = get_active_logger()
    if logger is None:
        return
    logger.tactics_count += 1
    _insert_log("tactics_prompt",   logger.tactics_count, prompt_text)
    _insert_log("tactics_response", logger.tactics_count, response_text)


def serialize_logger_state() -> str:
    logger = get_active_logger()
    if logger is None:
        return ""
    return json.dumps(logger.metadata, default=str)
