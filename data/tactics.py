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


# --- Gemini client -----------------------------------------------------------

_client = None

def _get_client() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client(api_key=settings.GEMINI_API_KEY)
    return _client


# --- System prompt -----------------------------------------------------------

TACTICS_SYSTEM_PROMPT = """
You are a specialist football tactics analyst.
Sharp, specific, grounded in data. You do not generalise. You do not fabricate.

You will receive a data payload about a fixture. Some fields may be null or missing.

## Critical rule on data quality

If the payload contains a "data_quality_warning" field — read it carefully.
It means some of the numbers may be from the wrong dataset (e.g. women's football
mixed in with men's data). Do NOT use unreliable figures to draw conclusions.

If you do not have enough reliable data to form a confident tactical opinion:
  - Set confidence to "low"
  - Set overall_advantage to "neutral"
  - Explain clearly in analyst_verdict what data is missing and why you cannot decide
  - Do NOT guess or fill gaps with assumptions

A low confidence neutral verdict is far more valuable than a confident wrong verdict.

## Your output (return ONLY this JSON — no prose, no code fences)

{
  "home_style":          "brief description based only on available data, or 'insufficient data'",
  "away_style":          "brief description based only on available data, or 'insufficient data'",
  "formation_matchup":   "formation analysis if available, or 'lineups not yet published'",
  "pressing_edge":       "home | away | neutral | unknown",
  "pressing_reason":     "one sentence — or 'no pressing data available'",
  "defensive_edge":      "home | away | neutral | unknown",
  "defensive_reason":    "one sentence — or 'no defensive data available'",
  "weather_impact":      "weather effect on this matchup — or 'weather data unavailable'",
  "time_impact":         "kickoff time effect — evening/afternoon/etc",
  "overall_advantage":   "home | away | neutral",
  "advantage_strength":  "strong | moderate | slight | none",
  "confidence":          "high | medium | low",
  "confidence_reason":   "one sentence explaining why confidence is at this level",
  "key_battlegrounds":   ["2-3 specific areas if data allows — empty list if not"],
  "analyst_verdict":     "2-3 sentences. If data is sufficient: name teams, be specific, say WHY. If data is insufficient: say so clearly and explain what is missing.",
  "data_gaps":           ["list every missing field that would have changed this analysis"]
}
"""


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
                system_instruction = TACTICS_SYSTEM_PROMPT,
                max_output_tokens = 2000,
                thinking_config    = types.ThinkingConfig(
                    include_thoughts = True,
                    thinking_budget  = 512,
                ),
            ),
        )

        raw      = _extract_text(response)
        thinking = _extract_thinking(response)
        result   = _parse_json(raw)

        if result is None:
            return _error("Gemini returned unparseable JSON", raw)

        result["_available"] = True
        result["_thinking"]  = thinking
        return result

    except Exception as e:
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