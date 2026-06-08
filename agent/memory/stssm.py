"""
agent/memory/stm.py

Short Term Session State Memory (STSSM).
Holds all state for a single match analysis session.
Created fresh at the start of each session, cleared when done.

One STSSM per match. Never persists to disk.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class ToolCall:
    """Records a single tool request made by Gemini during the ReAct loop."""
    round:          int
    tool:           str
    params:         dict
    reason:         str
    result_summary: str | None = None
    error:          str | None = None


@dataclass
class STSSM:
    """
    Short Term Session State Memory for one match analysis run.

    Lifecycle:
        1. Created by orchestrator at session start
        2. Populated as data is fetched
        3. Read by reasoning agent
        4. Cleared after bet placed + ledger logged
    """

    # --- Session metadata ----------------------------------------------------
    session_id:   str       = field(default_factory=lambda: _new_id())
    created_at:   str       = field(default_factory=lambda: _now())
    fixture_name: str       = ""
    kickoff:      str       = ""

    # --- Identity map (set after identity resolution) ------------------------
    identity_map: dict      = field(default_factory=dict)

    # --- Raw data fetched from each source -----------------------------------
    sportmonks:   dict      = field(default_factory=dict)
    polymarket:   dict      = field(default_factory=dict)
    supabase:     dict      = field(default_factory=dict)
    news:         list      = field(default_factory=list)

    # --- ReAct loop state ----------------------------------------------------
    current_round:  int          = 0
    tool_history:   list[ToolCall] = field(default_factory=list)
    gemini_messages: list[dict]  = field(default_factory=list)

    # --- Agent outputs -------------------------------------------------------
    prediction:     dict | None  = None   # Gemini's final prediction
    strategy:       dict | None  = None   # bet sizing decision
    order_response: dict | None  = None   # Arena order response

    # --- Session status ------------------------------------------------------
    status: str = "created"
    # created | fetching | reasoning | acting | done | skipped | error


    # --- Helpers -------------------------------------------------------------

    def add_tool_call(self, tool_call: ToolCall) -> None:
        """Record a tool call made by Gemini."""
        self.tool_history.append(tool_call)

    def add_gemini_message(self, role: str, content: str) -> None:
        """Append a message to the Gemini conversation history."""
        self.gemini_messages.append({"role": role, "content": content})

    def tool_history_summary(self) -> str:
        """
        Returns a plain text summary of all tool calls so far.
        Fed back to Gemini at the start of each round.
        """
        if not self.tool_history:
            return "No tool calls made yet."

        lines = ["Tool calls made so far:\n"]
        for tc in self.tool_history:
            status = "OK" if tc.error is None else f"ERROR: {tc.error}"
            lines.append(
                f"  Round {tc.round} | {tc.tool}({tc.params}) | {status}\n"
                f"  Reason : {tc.reason}\n"
                f"  Result : {tc.result_summary or 'pending'}\n"
            )
        return "\n".join(lines)

    def data_availability_summary(self) -> str:
        """
        Returns a plain text summary of what data is available.
        Fed to Gemini at the start of the reasoning call.
        """
        sm = self.sportmonks
        pm = self.polymarket
        sb = self.supabase
        im = self.identity_map

        lines = [
            f"Data availability for {self.fixture_name}:",
            f"  Sportmonks predictions : {'yes' if sm.get('predictions', {}).get('available') else 'no'}",
            f"  Sportmonks odds        : {'yes' if sm.get('odds', {}).get('available') else 'no'}",
            f"  Sportmonks xG          : {'yes' if sm.get('xg', {}).get('available') else 'no'}",
            f"  Sportmonks lineups     : {'yes' if sm.get('lineups', {}).get('available') else 'no'}",
            f"  Polymarket prices      : {'yes' if pm.get('live_prices', {}).get('available') else 'no'}",
            f"  Supabase checkpoint    : {'yes' if sb.get('checkpoint_stats', {}).get('available') else 'no'}",
            f"  Supabase priors        : {'yes' if sb.get('country_style', {}).get('available') else 'no'}",
            f"  News articles          : {len(self.news)} articles",
            f"  Home has supabase      : {im.get('home', {}).get('has_supabase', False)}",
            f"  Away has supabase      : {im.get('away', {}).get('has_supabase', False)}",
        ]
        return "\n".join(lines)

    def to_dict(self) -> dict:
        """Serialize STM to a plain dict for logging."""
        return {
            "session_id":    self.session_id,
            "created_at":    self.created_at,
            "fixture_name":  self.fixture_name,
            "kickoff":       self.kickoff,
            "status":        self.status,
            "current_round": self.current_round,
            "tool_history":  [
                {
                    "round":          tc.round,
                    "tool":           tc.tool,
                    "params":         tc.params,
                    "reason":         tc.reason,
                    "result_summary": tc.result_summary,
                    "error":          tc.error,
                }
                for tc in self.tool_history
            ],
            "prediction":     self.prediction,
            "strategy":       self.strategy,
        }


# --- Helpers ------------------------------------------------------------------

def _new_id() -> str:
    import uuid
    return str(uuid.uuid4())


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_session(fixture_name: str = "", kickoff: str = "") -> STM:
    """
    Create a fresh STM for a new match session.
    Called by the orchestrator at the start of each run.
    """
    stm = STSSM(fixture_name=fixture_name, kickoff=kickoff)
    stm.status = "created"
    return stm