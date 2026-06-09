"""
agent/tool_executor.py

Executes tool requests from the ReAct loop.
Maps tool names to actual function calls and returns clean summaries.

Called by the orchestrator when Gemini outputs a tool_request.
Returns a plain text summary — never raw JSON — back to the agent.
"""

from __future__ import annotations
import json
from agent.memory.stssm import STSSM, ToolCall


# --- Tool registry -----------------------------------------------------------

AVAILABLE_TOOLS = {
    "sportmonks.get_fixture":    "Fetch predictions, odds, xG for any WC2026 fixture",
    "sportmonks.get_team_form":  "Fetch recent match stats for any team",
    "polymarket.get_market":     "Fetch live Polymarket prices for any WC2026 match",
    "supabase.get_checkpoint":   "Fetch 2022 WC match stats for any team",
    "supabase.get_priors":       "Fetch historical stats for any country",
    "supabase.get_h2h":          "Fetch head to head record between two countries",
    "news.get_articles":         "Fetch latest news articles for any team or topic",
    "weather.get_match_weather": "Fetch weather forecast for a match venue",
    "tactics.analyse":           "Deep tactical analysis for a fixture",
}


# --- Main executor -----------------------------------------------------------

def execute(
    tool_name: str,
    params:    dict,
    stm:       STSSM,
    round_num: int,
) -> ToolCall:
    """
    Execute a tool request and return a ToolCall record.

    Args:
        tool_name: e.g. "supabase.get_h2h"
        params:    tool parameters from Gemini
        stm:       current session state (for identity map)
        round_num: current ReAct round number

    Returns:
        ToolCall with result_summary or error filled in.
    """
    tc = ToolCall(
        round  = round_num,
        tool   = tool_name,
        params = params,
        reason = params.pop("reason", ""),
    )

    if tool_name not in AVAILABLE_TOOLS:
        tc.error          = f"Unknown tool: {tool_name}"
        tc.result_summary = f"Tool '{tool_name}' does not exist. Available: {list(AVAILABLE_TOOLS.keys())}"
        return tc

    try:
        summary = _dispatch(tool_name, params, stm)
        tc.result_summary = summary
    except Exception as e:
        tc.error          = str(e)
        tc.result_summary = f"Tool '{tool_name}' failed: {e}"

    return tc


# --- Dispatcher --------------------------------------------------------------

def _dispatch(tool_name: str, params: dict, stm: STSSM) -> str:
    """Route tool_name to the correct function."""

    im = stm.identity_map

    if tool_name == "sportmonks.get_fixture":
        return _sportmonks_get_fixture(params, stm)

    elif tool_name == "sportmonks.get_team_form":
        return _sportmonks_get_team_form(params, stm)

    elif tool_name == "polymarket.get_market":
        return _polymarket_get_market(params, stm)

    elif tool_name == "supabase.get_checkpoint":
        return _supabase_get_checkpoint(params, stm)

    elif tool_name == "supabase.get_priors":
        return _supabase_get_priors(params, stm)

    elif tool_name == "supabase.get_h2h":
        return _supabase_get_h2h(params, stm)

    elif tool_name == "news.get_articles":
        return _news_get_articles(params)

    elif tool_name == "weather.get_match_weather":
        return _weather_get_match_weather(params, stm)

    elif tool_name == "tactics.analyse":
        return _tactics_analyse(params, stm)

    raise ValueError(f"No handler for tool: {tool_name}")


# --- Tool handlers -----------------------------------------------------------

def _sportmonks_get_fixture(params: dict, stm: STSSM) -> str:
    from data.identity import find_fixture, _get_sportmonks_identities
    from data.sportmonks import get_all

    home = params.get("home", stm.identity_map.get("home", {}).get("name", ""))
    away = params.get("away", stm.identity_map.get("away", {}).get("name", ""))

    fixture = find_fixture(home, away)
    if not fixture:
        return f"No WC2026 fixture found for {home} vs {away}."

    # build a minimal identity map for this fixture
    sm_id = _get_sportmonks_identities(fixture["fixture_id"])
    mini_im = {
        "fixture_id": fixture["fixture_id"],
        "home": {**sm_id["home"], "has_polymarket": False,
                 "has_supabase": False, "has_sb_priors": False},
        "away": {**sm_id["away"], "has_polymarket": False,
                 "has_supabase": False, "has_sb_priors": False},
    }
    data = get_all(mini_im)

    lines = [f"Sportmonks data for {home} vs {away}:"]
    preds = data.get("predictions", {})
    if preds.get("available"):
        c = preds.get("consensus", {})
        lines.append(f"  ML consensus: home={c.get('home')}%  draw={c.get('draw')}%  away={c.get('away')}%")
    odds = data.get("odds", {})
    if odds.get("available"):
        c = odds.get("consensus", {})
        lines.append(
            f"  Bookmakers ({odds.get('bookmaker_count')}): "
            f"home={round((c.get('home') or 0)*100,1)}%  "
            f"draw={round((c.get('draw') or 0)*100,1)}%  "
            f"away={round((c.get('away') or 0)*100,1)}%"
        )
    return "\n".join(lines)


def _sportmonks_get_team_form(params: dict, stm: STSSM) -> str:
    from data.supabase import get_checkpoint_stats

    team = params.get("team", "")
    im   = stm.identity_map

    # find which side this team is
    if team.lower() == im.get("home", {}).get("name", "").lower():
        target_im = im
    else:
        return f"Team '{team}' not in current fixture — checkpoint data only available for fixture teams."

    result = get_checkpoint_stats(target_im)
    if not result.get("available"):
        return f"No checkpoint stats available for {team}."

    lines = [f"Recent match stats for {team}:"]
    for m in result.get("home_matches", []):
        lines.append(
            f"  {m.get('opponent'):20s} "
            f"goals={m.get('cum_goals')}  "
            f"shots={m.get('cum_shots_total')}  "
            f"poss={m.get('cum_possession_pct')}%"
        )
    return "\n".join(lines)


def _polymarket_get_market(params: dict, stm: STSSM) -> str:
    from data.polymarket import get_live_prices, get_market_meta

    home = params.get("home", stm.identity_map.get("home", {}).get("name", ""))
    away = params.get("away", stm.identity_map.get("away", {}).get("name", ""))

    # use current fixture's identity map
    prices = get_live_prices(stm.identity_map)
    meta   = get_market_meta(stm.identity_map)

    if not prices.get("available"):
        return f"No live Polymarket prices for {home} vs {away}."

    return (
        f"Polymarket for {home} vs {away}: "
        f"home={prices['home']}  draw={prices['draw']}  away={prices['away']}  "
        f"(sum={prices['sum']}, liquidity=${meta.get('liquidity', 0):,.0f})"
    )


def _supabase_get_checkpoint(params: dict, stm: STSSM) -> str:
    from data.supabase import get_checkpoint_stats

    result = get_checkpoint_stats(stm.identity_map)
    if not result.get("available"):
        return "No Supabase checkpoint stats available for this fixture."

    home_name = stm.identity_map.get("home", {}).get("name", "Home")
    lines     = [f"2022 WC stats for {home_name}:"]
    for m in result.get("home_matches", []):
        lines.append(
            f"  {m.get('opponent'):20s} "
            f"goals={m.get('cum_goals')}  "
            f"shots={m.get('cum_shots_total')}  "
            f"on_target={m.get('cum_shots_on_target')}  "
            f"poss={m.get('cum_possession_pct')}%"
        )
    return "\n".join(lines)


def _supabase_get_priors(params: dict, stm: STSSM) -> str:
    from data.supabase import get_country_style, get_stage_record

    team = params.get("team", "")
    im   = stm.identity_map

    style  = get_country_style(im)
    stage  = get_stage_record(im)

    lines = [f"Historical priors for {team}:"]

    # determine which side
    side = "home" if team.lower() == im.get("home", {}).get("name", "").lower() else "away"

    s = (style.get(side) or {})
    if s:
        lines.append(
            f"  Style: group_gpg={s.get('group_gpg')}  "
            f"conversion={s.get('conversion_rate')}"
        )

    r = (stage.get(side) or {})
    if r and "group" in r:
        g = r["group"]
        lines.append(
            f"  Stage record (group): "
            f"W{g.get('wins')} D{g.get('draws')} L{g.get('losses')} "
            f"win_rate={g.get('win_rate'):.1%}"
        )

    return "\n".join(lines) if len(lines) > 1 else f"No priors data for {team}."


def _supabase_get_h2h(params: dict, stm: STSSM) -> str:
    from data.supabase import get_h2h

    result = get_h2h(stm.identity_map)
    if not result.get("available"):
        home = stm.identity_map.get("home", {}).get("name", "Home")
        away = stm.identity_map.get("away", {}).get("name", "Away")
        return f"No head-to-head record found for {home} vs {away} in this dataset."

    return (
        f"H2H: {result.get('matches')} matches, "
        f"home win rate={result.get('home_win_rate')}, "
        f"last meeting={result.get('last_meeting')}"
    )


def _news_get_articles(params: dict) -> str:
    from data.news.fetcher  import fetch_news
    from data.news.embedder import embed_articles
    from data.news.store    import store_articles, clear_collection
    from data.news.query    import get_news_context

    query = params.get("query", "World Cup 2026")

    # extract team names from query for fetcher
    words      = query.split()
    home_guess = words[0] if words else "World Cup"
    away_guess = words[1] if len(words) > 1 else "2026"

    articles = fetch_news(home_guess, away_guess)
    if not articles:
        return f"No recent news found for query: {query}"

    embedded = embed_articles(articles)
    clear_collection()
    store_articles(embedded)

    context = get_news_context(home_guess, away_guess)
    return context


def _weather_get_match_weather(params: dict, stm: STSSM) -> str:
    from data.weather import get_match_weather
    from data.sportmonks import get_fixture_meta

    meta    = get_fixture_meta(stm.identity_map)
    venue_id = meta.get("venue_id")
    kickoff  = stm.kickoff[:10] if stm.kickoff else None

    result = get_match_weather(venue_id=venue_id, kickoff_date=kickoff)
    return result.get("summary", "Weather data unavailable.")


def _tactics_analyse(params: dict, stm: STSSM) -> str:
    from data.tactics import analyse
    from data.sportmonks import get_all as sm_all
    from data.supabase   import get_all as sb_all
    from data.weather    import get_match_weather
    from data.sportmonks import get_fixture_meta

    home = stm.identity_map.get("home", {}).get("name", "")
    away = stm.identity_map.get("away", {}).get("name", "")

    sm   = sm_all(stm.identity_map)
    sb   = sb_all(stm.identity_map)
    meta = get_fixture_meta(stm.identity_map)
    wx   = get_match_weather(
        venue_id     = meta.get("venue_id"),
        kickoff_date = stm.kickoff[:10] if stm.kickoff else None,
    )

    result = analyse(
        home            = home,
        away            = away,
        sportmonks_data = sm,
        supabase_data   = sb,
        weather_data    = wx,
        kickoff_time    = stm.kickoff,
    )

    if not result.get("_available"):
        return f"Tactical analysis unavailable: {result.get('_error', 'unknown error')}"

    return (
        f"Tactical analysis: {home} vs {away}\n"
        f"  Overall advantage : {result.get('overall_advantage')} "
        f"({result.get('advantage_strength')})\n"
        f"  Confidence        : {result.get('confidence')}\n"
        f"  Verdict           : {result.get('analyst_verdict')}\n"
        f"  Key battlegrounds : {result.get('key_battlegrounds')}"
    )