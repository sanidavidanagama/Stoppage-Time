# agents/search.py
"""
agents/search.py

Grounded web search using Gemini's built-in google_search tool.
Used for both general search and news — a news query is just a search
query aimed at recent events. Returns real source URLs so results are
verifiable, not hallucinated.
"""

from google import genai
from google.genai import types

from config.settings import settings

_client = None


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client(api_key=settings.GEMINI_API_KEY)
    return _client


def web_search(query: str) -> dict:
    """
    Run a grounded web search via Gemini.

    Args:
        query: e.g. "Belgium squad injury news World Cup 2026"

    Returns:
        {
            "available": bool,
            "answer": str,             # Gemini's grounded synthesis
            "sources": [{"title": str, "url": str}, ...],
            "internal_reasoning": str,
        }
    """
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

    return {
        "available": True,
        "answer": "\n".join(answer_parts),
        "sources": sources,
        "internal_reasoning": "\n\n".join(thinking_parts),
    }