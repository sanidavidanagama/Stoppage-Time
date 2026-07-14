# agents/news_agent.py
"""
agents/news_agent.py

Fixture-specific, angle-scoped grounded search via Gemini.
Unlike a generic web search, every query is explicitly date-anchored
and instructed to report only current/recent information with dates
attached — this exists specifically to avoid surfacing stale news
(e.g. an injury that's since resolved) as if it were current.
"""

from datetime import date
from google import genai
from google.genai import types

from config.settings import settings
from service.telemetry import record_thinking
from service.db import update_session_status

_client = None


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client(api_key=settings.GEMINI_API_KEY)
    return _client


ANGLE_TEMPLATES = {
    "injuries": (
        "{home} vs {away} World Cup 2026 — current squad injuries, fitness "
        "doubts, and suspensions for the match on {match_date}. Only report "
        "news from the last 14 days. For every item, state the publish date "
        "explicitly and note whether the player has since recovered or "
        "returned to training. Do not report old injuries as current status."
    ),
    "atmosphere": (
        "{home} vs {away} World Cup 2026 — stadium atmosphere, fan travel, "
        "crowd expectations, and any local conditions expected to affect "
        "the match on {match_date}."
    ),
    "pundits": (
        "{home} vs {away} World Cup 2026 — pundit predictions and expert "
        "analysis ahead of the match on {match_date}. Look for opinions "
        "from recognized former players or analysts."
    ),
    "sentiment": (
        "{home} vs {away} World Cup 2026 — fan sentiment, public confidence, "
        "and any notable criticism or controversy surrounding either squad "
        "ahead of {match_date}."
    ),
    "wildcard": (
        "{home} vs {away} World Cup 2026 — any unusual, superstitious, or "
        "offbeat storylines circulating ahead of the match on {match_date} "
        "(rituals, predictions, curses, mascots, etc). Treat playfully — "
        "this is color, not a serious signal."
    ),
}


def get_news(
    home_team: str,
    away_team: str,
    angle: str,
    match_date: str = "",
    session_id: str | None = None,
    bet_id: str | None = None,
) -> dict:
    """
    Get fixture-specific, recency-anchored news for a given angle.

    Args:
        home_team, away_team: team names.
        angle: one of "injuries", "atmosphere", "pundits", "sentiment", "wildcard".
        match_date: e.g. "2026-07-04" — helps ground recency instructions.
        session_id, bet_id: optional — when provided, this call gets logged
            to Supabase (v2_logs) and Stair AI's Reasoning Ledger.
    """
    template = ANGLE_TEMPLATES.get(angle)
    if template is None:
        return {
            "available": False,
            "error": f"Unknown angle '{angle}'. Valid: {list(ANGLE_TEMPLATES.keys())}",
        }

    if session_id:
        update_session_status(session_id, "searching")

    query = template.format(home=home_team, away=away_team, match_date=match_date or "the upcoming match")
    query += f"\n\nToday's date is {date.today().isoformat()} — weigh recency accordingly."

    client = _get_client()
    try:
        response = client.models.generate_content(
            model=settings.GEMINI_MODEL,
            contents=query,
            config=types.GenerateContentConfig(
                tools=[types.Tool(google_search=types.GoogleSearch())],
                thinking_config=types.ThinkingConfig(include_thoughts=True),
            ),
        )
    except Exception as e:
        return {"available": False, "error": str(e)}

    thinking_parts, answer_parts = [], []
    for part in response.candidates[0].content.parts:
        if not getattr(part, "text", None):
            continue
        (thinking_parts if part.thought else answer_parts).append(part.text)

    sources = []
    grounding = getattr(response.candidates[0], "grounding_metadata", None)
    if grounding and grounding.grounding_chunks:
        for chunk in grounding.grounding_chunks:
            if chunk.web:
                sources.append({"title": chunk.web.title, "url": chunk.web.uri})

    answer_text = "\n".join(answer_parts)
    thinking_text = "\n\n".join(thinking_parts)

    if session_id:
        record_thinking(
            session_id=session_id,
            bet_id=bet_id,
            tool="news",
            model=settings.GEMINI_MODEL,
            prompt=query,
            response=answer_text,
            internal_reasoning=thinking_text,
        )

    return {
        "available": True,
        "angle": angle,
        "answer": answer_text,
        "sources": sources,
        "internal_reasoning": thinking_text,
    }