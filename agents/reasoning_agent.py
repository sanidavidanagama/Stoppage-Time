# agents/reasoning_agent.py
import json
import re
from pathlib import Path

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage

from config.settings import settings
from tools.tactics_tool import consult_tactics
from tools.news_tool import get_fixture_news
from tools.h2h_tool import get_head_to_head
from service.telemetry import record_thinking

TOOLS = [consult_tactics, get_fixture_news, get_head_to_head]
TOOLS_BY_NAME = {t.name: t for t in TOOLS}

TOOL_BUDGETS = {
    "consult_tactics":    settings.MAX_TACTICS_CALLS,
    "get_fixture_news":   settings.MAX_NEWS_CALLS,
    "get_head_to_head":   settings.MAX_H2H_CALLS,
}

_PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "reasoning_prompt.md"


def _load_prompt() -> str:
    return _PROMPT_PATH.read_text(encoding="utf-8")


def _fill_template(template: str, **kwargs) -> str:
    for key, value in kwargs.items():
        template = template.replace("{" + key + "}", str(value))
    return template


def _model():
    return ChatAnthropic(
        model=settings.ANTHROPIC_MODEL,
        max_tokens=settings.ANTHROPIC_REASONING_MAX_TOKENS,
        thinking={"type": "enabled", "budget_tokens": settings.ANTHROPIC_THINKING_BUDGET},
    ).bind_tools(TOOLS)


def _extract(response) -> tuple[str, str]:
    if isinstance(response.content, str):
        return "", response.content

    thinking_parts, text_parts = [], []
    for block in response.content:
        if isinstance(block, dict):
            if block.get("type") == "thinking":
                thinking_parts.append(block.get("thinking", ""))
            elif block.get("type") == "text":
                text_parts.append(block.get("text", ""))
    return "\n\n".join(thinking_parts), "\n\n".join(text_parts)


def _parse_json(text: str) -> dict | None:
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return None


def run_reasoning(
    home_name: str,
    away_name: str,
    round_info: str,
    kick_off_time: str = "Unknown",
    stadium: str = "Unknown venue",
    weather: str = "Unknown conditions",
    session_id: str | None = None,
    bet_id: str | None = None,
) -> dict:
    system_prompt = _fill_template(
        _load_prompt(),
        home_name=home_name,
        away_name=away_name,
        round_info=round_info,
        kick_off_time=kick_off_time,
        stadium=stadium,
        weather=weather,
    )

    model = _model()
    messages = [HumanMessage(system_prompt)]
    all_thinking = []
    call_counts = {name: 0 for name in TOOL_BUDGETS}

    for round_num in range(1, settings.MAX_TOOL_ROUNDS + 1):
        response = model.invoke(messages)
        messages.append(response)

        thinking, final_text = _extract(response)
        if thinking:
            all_thinking.append(f"[Round {round_num}]\n{thinking}")

        if session_id:
            record_thinking(
                session_id=session_id,
                bet_id=bet_id,
                tool="reasoning",
                model=settings.ANTHROPIC_MODEL,
                prompt=system_prompt if round_num == 1 else f"[Round {round_num} continuation]",
                response=final_text or "(tool_use round — no text output yet)",
                internal_reasoning=thinking,
            )

        stop_reason = response.response_metadata.get("stop_reason")

        if stop_reason == "max_tokens":
            return {
                "available": False,
                "error": "hit_max_tokens_mid_response",
                "internal_reasoning": "\n\n".join(all_thinking),
                "tool_calls_used": call_counts,
                "note": "Model ran out of output tokens before finishing. Increase ANTHROPIC_REASONING_MAX_TOKENS.",
            }

        if stop_reason != "tool_use":
            result = _parse_json(final_text)
            if result is None:
                return {
                    "available": False,
                    "error": "unparseable_response",
                    "raw": final_text,
                    "internal_reasoning": "\n\n".join(all_thinking),
                    "tool_calls_used": call_counts,
                }
            result["available"] = True
            result["internal_reasoning"] = "\n\n".join(all_thinking)
            result["rounds_used"] = round_num
            result["tool_calls_used"] = call_counts
            return result

        for call in response.tool_calls:
            name = call["name"]
            budget = TOOL_BUDGETS.get(name)

            if budget is not None and call_counts[name] >= budget:
                tool_result = (
                    f"Budget exhausted for '{name}' ({call_counts[name]}/{budget} used). "
                    f"Reason using what you already have — do not call this tool again."
                )
            else:
                tool_fn = TOOLS_BY_NAME.get(name)
                if tool_fn is None:
                    tool_result = f"Unknown tool: {name}"
                else:
                    call_counts[name] = call_counts.get(name, 0) + 1
                    tool_result = tool_fn.invoke(call["args"])

            content = json.dumps(tool_result) if isinstance(tool_result, dict) else tool_result
            messages.append({
                "role": "tool",
                "content": content,
                "tool_call_id": call["id"],
            })

    return {
        "available": False,
        "error": f"hit_max_rounds ({settings.MAX_TOOL_ROUNDS})",
        "internal_reasoning": "\n\n".join(all_thinking),
        "tool_calls_used": call_counts,
    }