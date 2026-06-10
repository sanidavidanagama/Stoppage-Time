
![Stoppage Time Banner](<docs/Stoppage Time Banner.png>)

<p align="center">
  <img alt="Python" src="https://img.shields.io/badge/python-3670A0?style=for-the-badge&logo=python&logoColor=ffdd54" />
  <img alt="uv" src="https://img.shields.io/badge/uv-0DB9FF?style=for-the-badge" />
  <img alt="pytest" src="https://img.shields.io/badge/pytest-151515?style=for-the-badge&logo=pytest" />
  <img alt="Supabase" src="https://img.shields.io/badge/supabase-3ECF8E?style=for-the-badge&logo=supabase" />
  <img alt="Stair AI" src="https://img.shields.io/badge/stair--ai-FF6B6B?style=for-the-badge" />
  <img alt="Polymarket" src="https://img.shields.io/badge/polymarket-1F8ACB?style=for-the-badge" />
  <img alt="Anthropic" src="https://img.shields.io/badge/anthropic-6C4EFF?style=for-the-badge" />
  <img alt="Gemini" src="https://img.shields.io/badge/gemini-4285F4?style=for-the-badge&logo=google" />
</p>

# Stoppage Time - FIFA World Cup '26 Polymarket Betting Agent



Stoppage Time is a **highly reasoning** betting agent built around three specialist sub-agents: a Reasoning Agent that analyses all available data and decides whether a bet is worth placing, a Tactics Agent that performs deep formation and style analysis when the Reasoning Agent needs a second opinion, and a Bet Manager that decides exactly how much to stake and at what price. The Reasoning Agent uses a ReAct loop, meaning it alternates between Reasoning (thinking about what it knows) and Acting (calling a data tool to fill a gap), repeating until it's confident enough to make a final call. It pulls data from five sources; Sportmonks ML predictions, live Polymarket prices, bookmaker consensus, historical Supabase stats, and live news, and only places a bet when its predicted probability differs from the market by more than 5 percentage points. Every decision step is logged to the Stair AI reasoning ledger, giving a full audit trail from the first data fetch to the final order.

---

## Project structure

Top-level files and folders:

- `main.py` — lightweight runner / CLI entrypoint
- `config.py` — configuration and constants
- `agent/` — core agent code
  - `orchestrator.py` — coordinates sub-agents and the run loop
  - `reasoning.py` — the Reasoning Agent and ReAct loop implementation
  - `bet_manager.py` — stake sizing and order execution logic
  - `tool_executor.py` — wrappers to call external data sources and tools
  - `memory/` — memory backends (`ltm.py`, `stssm.py`)
  - `prompts/` — agent prompt templates
- `data/` — data adapters for Sportmonks, Polymarket, Supabase, bookmakers, news
- `ledger/` — reasoning-ledger client, logging and reader utilities
- `tests/` — automated tests for the components
- notebooks/ — demonstration and analysis notebooks (backtests, EDA)

See the `tests` folder for unit and integration tests: [tests](tests)

---

## Architecture (step-by-step)

1. Runner: `main.py` is the CLI entrypoint. It parses arguments (home/away teams) and starts a single pre-match evaluation run.
2. Orchestrator: `agent/orchestrator.py` is the high-level coordinator. It initializes sub-agents, loads configuration and memory, and drives the evaluation loop for a single fixture.
3. Reasoning Agent: `agent/reasoning.py` implements a ReAct loop: it alternates between Reasoning (generating hypotheses, assessing confidence, or deciding which data to fetch next) and Acting (invoking `tool_executor.py` to fetch external data). The loop repeats until a confidence threshold is met or a maximum number of steps is reached.
4. Tool Executor: `agent/tool_executor.py` provides safe, rate-limited wrappers around the external data sources (Sportmonks, Polymarket, Supabase, bookmaker feeds, news). It normalizes responses into a compact format the Reasoning Agent can consume.
5. Tactics Agent: Called by the Reasoning Agent when formation/style-level detail is required. Performs deeper analysis of team tactics, lineup and historical match-ups using data in `data/tactics.py` and news embeds.
6. Bet Manager: `agent/bet_manager.py` is responsible for stake calculation, order construction and submission. It receives the final probability estimate and market snapshot then returns an actionable order (or no-op) based on bankroll constraints, risk limits and edge threshold (5% by default).
7. Ledger: Every decision, intermediate step, data fetch and final order is recorded to the Stair AI reasoning ledger via the code in `ledger/` to create an audit trail.

The typical run therefore flows: `main.py` -> `orchestrator` -> `reasoning` (ReAct loop) -> `tool_executor` (Act) -> optionally `tactics` -> `bet_manager` -> `ledger`.

---

## Agents and key files

- Reasoning Agent (`agent/reasoning.py`): Runs the ReAct loop, builds hypotheses, decides which tools to call, and aggregates evidence into a probability estimate.
- Tactics Agent (`agent/prompts/tactics_prompt.md` + related `data/tactics.py`): Performs detailed formation/style analysis when requested by the Reasoning Agent.
- Bet Manager (`agent/bet_manager.py`): Computes stake sizes and submits orders. It enforces bankroll and risk rules and only executes when the edge (predicted probability − market probability) exceeds the configured threshold.
- Orchestrator (`agent/orchestrator.py`): Boots the agents, wires memory and the ledger, and serialises a single run for a fixture.
- Tool Executor (`agent/tool_executor.py`): Encapsulates API calls, caching and normalization for all external data sources.

These files together implement the decision-making pipeline: data acquisition, reasoning (with external tool calls), optional deep tactical checks, then staking and order execution.

---

## Memory

Memory is handled under `agent/memory/` and split into short-term and long-term components:

- Short-term state (`stssm.py`) stores transient run-scoped state: recent observations, intermediate reasoning context and the active ReAct conversation state.
- Long-term memory (`ltm.py`) stores aggregated historical statistics and embeddings derived from news and historical match records (used by the Tactics Agent and by off-line analyses).

The orchestrator initialises memory backends and passes references into the Reasoning and Tactics Agents. Memory reads are performed frequently during the ReAct loop; writes append compact, timestamped records so the ledger and memory remain auditable.

---

## Tests

Automated tests are available in the `tests/` directory. Run them with `pytest`. Link: [tests](tests)

---

## Installation (using `uv`)

This project uses `uv` (https://github.com/astral-sh/uv) for environment and task management. Example workflow:

```bash
git clone https://github.com/sanidavidanagama/Stoppage-Time.git
cd Stoppage-Time
uv venv
uv sync
```

The above creates a virtual environment and installs pinned dependencies.

---

## Environment variables

Required keys (create a `.env` file or set in your environment):

- `GEMINI_API_KEY` — get this from https://aistudio.google.com/
- `ARENA_KEY` — get this from https://staging.stair-ai.com/api-keys

Optional keys and notes are documented in `config.py`.

---

## Running

Start a single run with the built-in runner. By default the repository ships with a demo fixture (Mexico vs South Africa). To run:

```bash
uv run main.py
```

To evaluate a specific fixture, pass home/away team names as arguments:

```bash
uv run main.py "Home" "Away"
```

---

## API references

- Stair AI Builder Guide and API reference: https://stair-ai.com/builder-guide#api-reference
- Staging API endpoints: https://staging.stair-ai.com/api

