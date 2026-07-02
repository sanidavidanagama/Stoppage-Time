# tools/search_tool.py
from langchain_core.tools import tool
from agents.search import web_search


@tool
def search_web(query: str) -> dict:
    """
    Search the web for current, factual information — squad news, injuries,
    suspensions, team-selection reports, weather, or any other real-time
    context not available from Sportmonks or historical data. Returns a
    grounded answer with real source URLs, not a guess.
    """
    return web_search(query)