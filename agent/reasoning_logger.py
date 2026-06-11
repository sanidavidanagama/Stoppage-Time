"""Fixture-scoped human review logging for Gemini calls."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from threading import Lock


_ROOT = Path(__file__).resolve().parent.parent / "logs"
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
    base_dir: Path
    reasoning_count: int = 0
    bet_written: bool = False
    metadata: dict = field(default_factory=dict)

    def next_reasoning_paths(self) -> tuple[Path, Path]:
        self.reasoning_count += 1
        prompt_path = self.base_dir / f"reasoning_prompt_{self.reasoning_count}.md"
        response_path = self.base_dir / f"reasoning_response_{self.reasoning_count}.txt"
        return prompt_path, response_path

    def bet_paths(self) -> tuple[Path, Path]:
        return self.base_dir / "bet_prompt.md", self.base_dir / "bet_response.txt"


def start_fixture_log(home_code: str, away_code: str, kickoff: str | None, fixture_name: str | None = None) -> FixtureLogger:
    """Create the fixture folder used for human review artifacts."""
    folder_name = f"{_slugify(home_code)}_vs_{_slugify(away_code)}_{_sanitize_kickoff(kickoff)}"
    fixture_dir = _ROOT / folder_name
    suffix = 2
    while fixture_dir.exists():
        fixture_dir = _ROOT / f"{folder_name}_{suffix}"
        suffix += 1
    fixture_dir.mkdir(parents=True, exist_ok=True)

    logger = FixtureLogger(
        base_dir=fixture_dir,
        metadata={
            "home_code": home_code,
            "away_code": away_code,
            "kickoff": kickoff,
            "fixture_name": fixture_name,
            "folder_name": folder_name,
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


def log_reasoning(prompt_text: str, response_text: str) -> tuple[Path, Path] | None:
    logger = get_active_logger()
    if logger is None:
        return None

    prompt_path, response_path = logger.next_reasoning_paths()
    prompt_path.write_text(prompt_text, encoding="utf-8")
    response_path.write_text(response_text, encoding="utf-8")
    return prompt_path, response_path


def log_bet(prompt_text: str, response_text: str) -> tuple[Path, Path] | None:
    logger = get_active_logger()
    if logger is None:
        return None

    prompt_path, response_path = logger.bet_paths()
    if not logger.bet_written:
        prompt_path.write_text(prompt_text, encoding="utf-8")
        logger.bet_written = True
    else:
        prompt_path.write_text(prompt_text, encoding="utf-8")
    response_path.write_text(response_text, encoding="utf-8")
    return prompt_path, response_path


def serialize_logger_state() -> str:
    logger = get_active_logger()
    if logger is None:
        return ""
    return json.dumps(logger.metadata, default=str)
