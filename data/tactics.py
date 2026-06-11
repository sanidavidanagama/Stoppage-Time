"""
agent/tactics_agent.py

Specialist tactical analysis agent.
Called on-demand by the main reasoning agent when tactical context
would help resolve uncertainty.

Separate Gemini call with a football analyst persona.
If data is insufficient, returns low confidence rather than fabricating.
"""

from __future__ import annotations
import json
import re
from google import genai
from google.genai import types
from config import settings
from pathlib import Path
from agent.reasoning_logger import log_tactics


# --- Gemini client -----------------------------------------------------------

_client = None

def _get_client() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client(api_key=settings.GEMINI_API_KEY)
    return _client


# --- System prompt -----------------------------------------------------------

_TACTICS_PROMPT_PATH = Path(__file__).parent.parent / "agent" / "prompts" / "tactics_prompt.md"

def _load_tactics_prompt() -> str:
    return _TACTICS_PROMPT_PATH.read_text(encoding="utf-8")


# --- Main analyser -----------------------------------------------------------

def analyse(
    home:            str,
    away:            str,
    sportmonks_data: dict | None = None,
    supabase_data:   dict | None = None,
    weather_data:    dict | None = None,
    kickoff_time:    str | None  = None,
) -> dict:
    """
    Run tactical analysis for a fixture.

    Args:
        home:            home team name e.g. "Mexico"
        away:            away team name e.g. "South Africa"
        sportmonks_data: from data/sportmonks.py get_all()
        supabase_data:   from data/supabase.py get_all()
        weather_data:    from data/weather.py get_match_weather()
        kickoff_time:    ISO kickoff string e.g. "2026-06-11 19:00:00"

    Returns:
        Tactical analysis dict with _available and _confidence keys.
    """
    payload = _build_payload(
        home, away, sportmonks_data, supabase_data, weather_data, kickoff_time
    )

    try:
        client   = _get_client()
        response = client.models.generate_content(
            model    = settings.GEMINI_MODEL,
            contents = json.dumps(payload, default=str),
            config   = types.GenerateContentConfig(
                system_instruction = _load_tactics_prompt(),
                max_output_tokens = 2000,
                thinking_config    = types.ThinkingConfig(
                    include_thoughts = True,
                    thinking_budget  = 512,
                ),
            ),
        )

        raw      = _extract_text(response)
        thinking = _extract_thinking(response)
        _log_tactics_exchange(payload, thinking, raw)
        result   = _parse_json(raw)

        if result is None:
            return _error("Gemini returned unparseable JSON", raw)

        result["_available"] = True
        result["_thinking"]  = thinking
        return result

    except Exception as e:
        _log_tactics_exchange(payload, "", f"EXCEPTION\n\n{e}")
        return _error(str(e))


# --- Payload builder ---------------------------------------------------------

def _build_payload(
    home:            str,
    away:            str,
    sportmonks_data: dict | None,
    supabase_data:   dict | None,
    weather_data:    dict | None,
    kickoff_time:    str | None,
) -> dict:
    """Assemble the data payload sent to the tactics agent."""

    payload: dict = {
        "fixture":      f"{home} vs {away}",
        "home":         home,
        "away":         away,
        "kickoff_time": kickoff_time or "unknown",
    }

    # --- lineups + formations ------------------------------------------------
    if sportmonks_data:
        lineups = sportmonks_data.get("lineups", {})
        home_lineup = lineups.get("home") or {}
        away_lineup = lineups.get("away") or {}
        payload["home_formation"]    = home_lineup.get("formation")
        payload["away_formation"]    = away_lineup.get("formation")
        payload["lineups_available"] = lineups.get("available", False)

    # --- supabase: PPDA, defensive line, playing style -----------------------
    if supabase_data:
        ck    = supabase_data.get("checkpoint_stats", {})
        style = supabase_data.get("country_style", {})

        # PPDA and defensive line from checkpoint matches
        home_ppda = []
        home_def  = []
        for match in (ck.get("home_matches") or []):
            if match.get("seg_avg_ppda") is not None:
                home_ppda.append(match["seg_avg_ppda"])
            if match.get("seg_avg_def_line_height_m") is not None:
                home_def.append(match["seg_avg_def_line_height_m"])

        payload["home_avg_ppda"]       = round(sum(home_ppda) / len(home_ppda), 2) if home_ppda else None
        payload["home_avg_def_line_m"] = round(sum(home_def)  / len(home_def),  2) if home_def  else None
        payload["home_checkpoint_matches"] = len(ck.get("home_matches") or [])

        # playing style priors — with explicit availability flags
        home_style = style.get("home") or {}
        away_style = style.get("away") or {}

        payload["home_group_gpg"]        = home_style.get("group_gpg")
        payload["home_conversion_rate"]  = home_style.get("conversion_rate")
        payload["away_group_gpg"]        = away_style.get("group_gpg")
        payload["away_conversion_rate"]  = away_style.get("conversion_rate")
        payload["home_priors_available"] = bool(home_style)
        payload["away_priors_available"] = bool(away_style)

        # --- data quality warning --------------------------------------------
        # Flag mixed dataset issue so agent doesn't over-trust the numbers
        warnings = []
        if away_style and not supabase_data.get("checkpoint_stats", {}).get("available"):
            warnings.append(
                f"{away} has no 2022 WC checkpoint data — "
                f"they did not qualify for the 2022 men's World Cup."
            )
        if away_style:
            warnings.append(
                f"The priors dataset (ads_a_country_style) mixes men's and women's "
                f"tournament data. {away}'s group_gpg ({away_style.get('group_gpg')}) "
                f"and conversion_rate ({away_style.get('conversion_rate')}) "
                f"likely include women's football — treat with extreme caution."
            )
        if warnings:
            payload["data_quality_warning"] = " ".join(warnings)

    # --- weather -------------------------------------------------------------
    if weather_data and weather_data.get("available"):
        payload["weather"] = {
            "venue":     weather_data.get("venue"),
            "city":      weather_data.get("city"),
            "temp_c":    weather_data.get("temp_c"),
            "condition": weather_data.get("condition"),
            "wind_kph":  weather_data.get("wind_kph"),
            "precip_mm": weather_data.get("precip_mm"),
            "summary":   weather_data.get("summary"),
        }
    else:
        payload["weather"] = None

    return payload


# --- Helpers -----------------------------------------------------------------

def _extract_text(response) -> str:
    parts = []
    for part in response.candidates[0].content.parts:
        if not getattr(part, "thought", False):
            parts.append(getattr(part, "text", "") or "")
    return "\n".join(parts)


def _extract_thinking(response) -> str:
    parts = []
    for part in response.candidates[0].content.parts:
        if getattr(part, "thought", False):
            parts.append(getattr(part, "text", "") or "")
    return "\n".join(parts)


def _build_prompt_snapshot(payload: dict) -> str:
    return (
        "# System Prompt\n\n"
        + _load_tactics_prompt()
        + "\n\n# User Payload\n\n```json\n"
        + json.dumps(payload, indent=2, default=str)
        + "\n```\n"
    )


def _format_response_snapshot(thinking: str, raw: str) -> str:
    return (
        "# Thinking\n\n"
        + (thinking or "")
        + "\n\n# Raw Response\n\n"
        + (raw or "")
    )


def _log_tactics_exchange(payload: dict, thinking: str, raw: str) -> None:
    try:
        log_tactics(
            _build_prompt_snapshot(payload),
            _format_response_snapshot(thinking, raw),
        )
    except Exception:
        pass

def _parse_json(raw: str) -> dict | None:
    # strip markdown code fences if present
    clean = re.sub(r"```json\s*", "", raw)
    clean = re.sub(r"```\s*", "", clean)

    m = re.search(r"\{.*\}", clean, re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return None

def _error(reason: str, raw: str = "") -> dict:
    return {
        "_available":        False,
        "_error":            reason,
        "_raw":              raw,
        "overall_advantage": "neutral",
        "advantage_strength": "none",
        "confidence":        "low",
        "confidence_reason": f"Tactics agent failed: {reason}",
        "analyst_verdict":   f"Tactical analysis unavailable: {reason}",
        "data_gaps":         ["tactics agent failed to run"],
    }