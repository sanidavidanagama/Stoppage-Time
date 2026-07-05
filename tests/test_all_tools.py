# tests/test_all_tools.py
from dotenv import load_dotenv
load_dotenv()

import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage
from tools.tactics_tool import consult_tactics
from tools.search_tool import search_web
from tools.h2h_tool import get_head_to_head
from tools.polymarket_tool import get_market_odds
from config.settings import settings

TOOLS = [consult_tactics, search_web, get_head_to_head, get_market_odds]
TOOLS_BY_NAME = {t.name: t for t in TOOLS}

model = ChatAnthropic(model=settings.ANTHROPIC_MODEL)
model_with_tools = model.bind_tools(TOOLS)

MAX_ROUNDS = 4

def run_loop(question: str):
    messages = [HumanMessage(question)]

    for round_num in range(1, MAX_ROUNDS + 1):
        print(f"\n--- Round {round_num} ---")
        response = model_with_tools.invoke(messages)
        messages.append(response)

        if response.response_metadata["stop_reason"] != "tool_use":
            print("Model gave a final answer.")
            return response.content

        print("Model requested tools:", [c["name"] for c in response.tool_calls])

        for call in response.tool_calls:
            tool_fn = TOOLS_BY_NAME[call["name"]]
            print(f"  calling {call['name']} with {call['args']}")
            result = tool_fn.invoke(call["args"])
            content = json.dumps(result) if isinstance(result, dict) else result
            messages.append({
                "role": "tool",
                "content": content,
                "tool_call_id": call["id"],
            })

    print("Hit MAX_ROUNDS without a final answer.")
    return None


answer = run_loop(
    "I'm evaluating Argentina vs Cape Verde, Round of 32. Give me a full picture: "
    "how the teams match up tactically, any current squad news, historical "
    "trends between these regions, and what the market currently thinks."
)
print("\n=== FINAL ===")
print(answer)