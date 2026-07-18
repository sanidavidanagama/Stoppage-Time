![Stoppage Time Banner](<docs/Stoppage Time Banner.png>)

# Stoppage Time - FIFA World Cup '26 Polymarket Betting Agent

![Python](https://img.shields.io/badge/Python-000000?style=for-the-badge&logo=python&logoColor=e7b24a)
![FastAPI](https://img.shields.io/badge/FastAPI-000000?style=for-the-badge&logo=fastapi&logoColor=e7b24a)
![uv](https://img.shields.io/badge/uv-000000?style=for-the-badge&logo=uv&logoColor=e7b24a)
![LangChain](https://img.shields.io/badge/LangChain-000000?style=for-the-badge&logo=langchain&logoColor=e7b24a)
![Anthropic](https://img.shields.io/badge/Anthropic-000000?style=for-the-badge&logo=anthropic&logoColor=e7b24a)
![Gemini](https://img.shields.io/badge/Gemini-000000?style=for-the-badge&logo=googlegemini&logoColor=e7b24a)
![Supabase](https://img.shields.io/badge/Supabase-000000?style=for-the-badge&logo=supabase&logoColor=e7b24a)
![Stair AI](https://img.shields.io/badge/Stair_AI-000000?style=for-the-badge)
![Polymarket](https://img.shields.io/badge/Polymarket-000000?style=for-the-badge)

*FIFA World Cup 2026 · Match Outcome Predictor · Polymarket Betting Agent*

Stoppage Time is a reasoning agent that reads a World Cup 2026 fixture, forms
its own probability estimate of the outcome, compares that estimate against
live Polymarket prices, and — when it finds a real statistical edge — places
a real order. Every step of that reasoning is written to a database as it
happens, and the whole thing is exposed behind a FastAPI backend so a
frontend can kick off an analysis, watch it think in near-real-time, and
decide separately whether to actually let it trade.

This document covers what the system is and how it's built. For the full
HTTP API reference — every endpoint, request/response schema, and status
code — see [`api/README.md`](api/README.md).

---

## Contents

- [What this is](#what-this-is)
- [The two agent pipelines](#the-two-agent-pipelines)
  - [Unified agent](#unified-agent)
  - [Multi-agent pipeline](#multi-agent-pipeline)
  - [Shared building blocks](#shared-building-blocks)
- [Reasoning and trading are two separate steps](#reasoning-and-trading-are-two-separate-steps)
- [Data and external services](#data-and-external-services)
- [Project structure](#project-structure)
- [Installation](#installation)
- [Configuration](#configuration)
- [Running it](#running-it)
- [Tests](#tests)

---

## What this is

At its core, this project answers one question, repeatedly, for different
fixtures: *given everything knowable about this match right now, what's the
true probability of each outcome, and does the market disagree with me
enough to be worth betting on?*

Answering that well means pulling together several kinds of information —
squad form and tactics, injuries and pundit takes, historical continental
trends, live market prices — and reasoning over all of it with an LLM.
Stoppage Time does this two different ways (below), records the entire
reasoning trace as it happens, and keeps order placement as a distinct,
deliberate second step rather than something that happens automatically the
moment a decision is reached.

Everything runs against real infrastructure: fixture and squad data comes
from Sportmonks, market prices and order execution go through Polymarket,
and both are proxied through the **Stair AI Arena** (`stair-ai.com`), which
also hosts the agent's USDC wallet and a separate reasoning-audit ledger
used to score agents in competition. The project's own state — sessions,
decisions, and step-by-step logs — lives in its own Supabase project,
independent of Stair AI's ledger.

---

## The two agent pipelines

Every run is either **unified** or **multi-agent**. Both start from the same
place (two team names and a tournament stage) and end at the same place (a
probability estimate, a decision, and — if a real edge exists — a stake),
but they get there differently.

| | Unified agent | Multi-agent pipeline |
|---|---|---|
| LLM calls | One combined call | Several, across specialist agents |
| Model | `claude-opus-4-8`, adaptive thinking, high effort | `claude-haiku-4-5` per agent, fixed thinking budget |
| Tactics analysis | Folded into the single prompt | A dedicated LLM call (Tactics Agent) |
| Tool use | None — all context gathered up front | Reasoning Agent runs a ReAct loop, calling tools on demand |
| Can it skip? | No — the prompt requires a decision | Yes — skips below the edge threshold before any LLM call runs |
| Entry point | `agents/unified_agent.py` | `agents/planning_agent.py` → `reasoning_agent.py` → `betting_agent.py`, orchestrated by `workflows/run_pipeline.py` |
| `session_id` prefix | `unified-` | `live-` |

### Unified agent

`agents/unified_agent.py::run_unified_agent` does everything in one pass:
resolve the fixture, pull full-tournament team form and lineups from
Sportmonks, gather news (injuries, pundit takes, atmosphere — via the News
Agent), pull a continent-level head-to-head trend, fetch the live market
price, and hand all of it to a single large prompt
(`prompts/unified_agent_prompt.md`). Claude Opus, running with adaptive
extended thinking, returns a tactical summary, a probability for each
outcome, a confidence level, a chosen outcome, and a proposed stake — all in
one JSON response. The prompt explicitly forbids skipping: this pipeline
always reaches a decision or an error, never a deliberate no-bet.

News and search are the only sub-calls that happen outside the one big
prompt — they're grounded Gemini searches, not LLM reasoning steps, so they
don't count against the "single call" framing.

### Multi-agent pipeline

`workflows/run_pipeline.py::run` composes three specialist agents in
sequence:

1. **Planning Agent** (`planning_agent.py`) gathers context up front and
   hands it downstream as a formatted brief: a general tactical read (via
   the Tactics Agent), injury/pundit/atmosphere news, and the continental
   head-to-head trend.
2. **Reasoning Agent** (`reasoning_agent.py`) forms an independent
   probability estimate. Unlike the unified agent, it runs a genuine
   **ReAct loop** — `claude-haiku-4-5` bound to three tools
   (`consult_tactics`, `get_fixture_news`, `get_head_to_head`, each under a
   configurable per-run call budget) and free to call them or not as it
   sees fit, up to `MAX_TOOL_ROUNDS` rounds, before committing to a final
   probability and confidence.
3. **Betting Agent** (`betting_agent.py`) starts with pure arithmetic, not
   an LLM call: it scans all three outcomes for the biggest edge (predicted
   probability minus market price) and only proceeds if that edge clears
   `MIN_EDGE_PP`. If it doesn't, the bet is recorded as skipped and nothing
   further happens — no model is invoked at all. If it does, an LLM call
   always bets on that outcome (no skip past this point) and decides only
   the stake size, between `MIN_STAKE_USD` and `MAX_BET_SIZE`, weighing the
   Reasoning Agent's actual match analysis (key factors/summary) against
   the raw edge rather than sizing off the edge number alone.

### Shared building blocks

- **Tactics Agent** (`tactics_agent.py`) — one focused LLM call per
  invocation, producing formation clashes, key matchups, and style-clash
  analysis from Sportmonks lineup/formation data (`service/prompt_builder.py`
  assembles its prompt). Used directly by the Planning Agent, and available
  to the Reasoning Agent as a bindable tool.
- **News Agent** (`news_agent.py`) — Gemini with grounded Google Search,
  queried per "angle" (`injuries`, `pundits`, `atmosphere`, `sentiment`,
  `wildcard`), every query explicitly date-anchored so stale news doesn't
  get treated as current.
- **H2H** (`service/h2h.py`) — no LLM at all. A deterministic lookup against
  a shared Supabase table of continent-vs-continent World Cup history
  (country-level H2H was tried and dropped — too sparse to be reliable).
- **Search Agent** (`search_agent.py`) — general-purpose grounded web
  search, available as a bindable tool but not currently wired into either
  pipeline's default tool list.
- **Reflecting Agent** (`reflecting_agent.py`) — reviews one *settled* bet
  after the fact and decides whether to update a shared "personality note"
  that future Reasoning/Betting calls read as track-record context. Exists
  in the codebase; not currently invoked by either pipeline or the API —
  it's a hook for closing the self-improvement loop, not yet wired in.

---

## Reasoning and trading are two separate steps

Neither pipeline places an order as part of reasoning. Both stop the moment
a decision is made — outcome, confidence, stake — and persist it. The
session's status lands on `awaiting_order` (or `skipped`, if the decision
was not to bet), and nothing has touched the market yet.

Actually placing the order is a distinct, separate call:
`service/order_execution.py::execute_order`. It re-reads the saved decision,
fetches a **fresh** market price (not the one from when the decision was
made — time may have passed), places the order through
`service/orders.py`, and only then updates the record with the real
`order_id`/`fill_price` and moves the session to `completed`.

This split exists so a frontend (or a human) can review the agent's full
reasoning before any money moves — see `POST /api/fixture` vs
`POST /api/fixture/{session_id}/order`, and `GET /api/orders/awaiting` for
finding decisions still waiting on that second step, in
[`api/README.md`](api/README.md).

A session moves through a small set of statuses as it runs — `queued` →
`planning` → (`tactical analysis` / `searching` / `reasoning` / `betting`,
in whatever order the pipeline actually calls them) → `awaiting_order` →
`completed`, or `skipped`/`error` at various points. The full status
vocabulary, with exactly what triggers each transition, is documented in
[`api/README.md`](api/README.md#session-status-vocabulary).

Once a fixture concludes, `POST /api/settlement/run`
(`service/settlement.py`) checks Polymarket's real settlement data against
every unsettled bet and records the actual outcome and profit/loss — a
separate step again, run independently (e.g. on a schedule), from either
reasoning or trading.

---

## Data and external services

| Service | Used for | Accessed via |
|---|---|---|
| **Anthropic (Claude)** | All reasoning — unified agent, planning, reasoning, betting, tactics, reflecting | `langchain-anthropic`, direct API key |
| **Google Gemini** | Grounded news and web search | `google-genai`, direct API key |
| **Stair AI Arena** (`stair-ai.com`) | Proxies Sportmonks fixture/squad data and Polymarket prices/orders; hosts the agent's USDC wallet and a separate reasoning-audit ledger | `httpx`, `ARENA_KEY` header |
| **This project's Supabase** | `sessions` / `agent_bets` / `agent_logs` — the state this API actually reads and writes | `httpx` against the Supabase REST API, `ST_SUPABASE_*` credentials |
| **A second, shared Supabase project** | Read-only reference data: continent-level World Cup head-to-head history (`world_cup_arena` schema) | `httpx`, `SUPABASE_URL`/`SUPABASE_KEY` |

Two separate Supabase projects are in play and it's easy to conflate them:
`ST_SUPABASE_*` is this project's own database, holding everything the API
serves. The plain `SUPABASE_URL`/`SUPABASE_KEY` pair points at a different,
shared project used only as a static reference table for `service/h2h.py`.

---

## Project structure

```
Stoppage-Time/
├── main.py                      FastAPI process entrypoint
├── api/                         HTTP API layer
│   ├── main.py                    FastAPI app: CORS, router registration
│   ├── deps.py                     JWT auth dependency
│   ├── routes/                      auth, fixture, history, orders, stats, settlement
│   └── README.md                     Full API reference
├── agents/                      LLM-driven decision-making
│   ├── unified_agent.py           Single combined-call pipeline
│   ├── planning_agent.py          Multi-agent: context gathering
│   ├── reasoning_agent.py         Multi-agent: ReAct loop, tool-calling
│   ├── betting_agent.py           Multi-agent: edge scan + stake decision
│   ├── tactics_agent.py           Formation/style analysis (shared)
│   ├── news_agent.py              Angle-scoped grounded news search
│   ├── search_agent.py            General grounded web search
│   ├── reflecting_agent.py        Post-settlement self-reflection
│   └── local_unified_agent.py     Dry-run unified agent — no DB writes, no order
├── workflows/                   CLI entrypoints for the two pipelines
├── service/                     Everything that isn't an LLM call
│   ├── db.py                       Supabase REST client for this project's own tables
│   ├── schedule.py                  Sportmonks fixture/schedule lookups
│   ├── polymarket.py                 Live market prices
│   ├── wallet.py                      Arena wallet balance
│   ├── orders.py                       Raw order placement/polling
│   ├── order_execution.py               The one function that spends money
│   ├── settlement.py                     Reconciles bets against real outcomes
│   ├── h2h.py                              Deterministic continent H2H trend
│   ├── telemetry.py                         Dual-writes to Supabase + Reasoning Ledger
│   ├── stair_ai_ledger.py                    Stair AI Reasoning Ledger client
│   ├── context.py                             Propagates session_id/bet_id to tool calls
│   ├── prompt_builder.py                       Assembles the Tactics Agent's prompt
│   └── past_match_formatter.py                  Formats historical matches for prompts
├── tools/                       LangChain @tool wrappers for the Reasoning Agent
├── models/                      Pydantic request/response schemas for the API
├── config/                      Settings, static team/continent data, Sportmonks stat-type map
├── prompts/                     Markdown prompt templates, one per agent
└── tests/                       pytest suite (some marked "live" — real API calls)
```

---

## Installation

This project uses [`uv`](https://github.com/astral-sh/uv) for environment
and dependency management, with Python 3.11+.

```bash
git clone https://github.com/sanidavidanagama/Stoppage-Time.git
cd Stoppage-Time
uv venv
uv sync
```

`uv sync` installs the exact pinned versions from `uv.lock`, resolved from
`pyproject.toml`. (`requirements.txt` also exists but has drifted out of
sync with `pyproject.toml` — treat `uv sync` as the source of truth.)

---

## Configuration

All configuration is loaded from a `.env` file in the project root via
`config/settings.py` (`pydantic-settings`). Four keys are required with no
default — the app won't start without them:

| Variable | Required for |
|---|---|
| `ANTHROPIC_API_KEY` | Every reasoning call across every agent (Claude, via `langchain-anthropic`) |
| `GEMINI_API_KEY` | News search and general web search (Gemini, via `google-genai`) |
| `ARENA_KEY` | All Stair AI Arena access — fixture data, market prices, orders, wallet, Reasoning Ledger |
| `SERP_API_KEY` | Reserved for search-quota tracking (`SERP_MONTHLY_LIMIT`) |

Everything else has a sensible default and only needs overriding to change
behavior:

| Variable | Default | Purpose |
|---|---|---|
| `ARENA` | `https://stair-ai.com` | Base URL for all Stair AI Arena proxy calls |
| `AGENT_ID` | — | This agent's identity in the Arena |
| `ST_SUPABASE_URL` / `ST_SUPABASE_SECRET_KEY` / `ST_SUPABASE_PUBLISHABLE_KEY` | — | This project's own Supabase project (`sessions`/`agent_bets`/`agent_logs`) |
| `SUPABASE_URL` / `SUPABASE_KEY` | shared project | Read-only continent H2H reference data — separate project, see [above](#data-and-external-services) |
| `GEMINI_MODEL` | `gemini-2.5-flash` | Model used for news/search |
| `ANTHROPIC_MODEL` | `claude-haiku-4-5-20251001` | Model used by the multi-agent pipeline (the unified agent hardcodes `claude-opus-4-8`) |
| `ANTHROPIC_THINKING_BUDGET` | `1200` | Extended-thinking token budget for multi-agent LLM calls |
| `ANTHROPIC_MAX_TOKENS` / `ANTHROPIC_REASONING_MAX_TOKENS` | `3000` / `6000` | Output token caps (Tactics/Reflecting vs Reasoning) |
| `SEASON_ID` | `26618` | Sportmonks season id for the tournament |
| `LEDGER_SCHEMA_VERSION` | `0.3` | Stair AI Reasoning Ledger record schema version |
| `MAX_TOOL_ROUNDS` | `4` | Cap on ReAct rounds in the Reasoning Agent |
| `MAX_TACTICS_CALLS` / `MAX_NEWS_CALLS` / `MAX_H2H_CALLS` | `2` / `3` / `3` | Per-run budgets on each bindable tool |
| `MIN_EDGE_PP` | `5.0` | Minimum edge (percentage points) before the Betting Agent's LLM call even runs |
| `MIN_STAKE_USD` | `15.0` | Floor on any stake (no skip once a real edge exists) |
| `MAX_BET_SIZE` | `50.0` | Ceiling on any stake |
| `STARTING_BALANCE_USD` | `100.0` | Reference starting balance for ROI stats (`GET /api/agent/stats`) — not tracked historically, just a fixed baseline |
| `ADMIN_USERNAME` / `ADMIN_PASSWORD` | `admin` / `changeme` | The single admin account for API auth — **change these before deploying** |
| `JWT_SECRET_KEY` | placeholder | Signs API auth tokens — **set a real secret in `.env`** |
| `JWT_ALGORITHM` | `HS256` | JWT signing algorithm |
| `JWT_EXPIRE_DAYS` | `7` | API token lifetime |
| `ALLOWED_ORIGINS` | `*` | Comma-separated CORS origin list for the API |
| `DEBUG` | `False` | — |

---

## Running it

### As an API server

```bash
uv run main.py
```

Starts uvicorn on `0.0.0.0:8000` (or `$PORT`), serving `api.main:app`. From
here a frontend drives everything: `POST /api/fixture` to start a run,
`GET /api/fixture/{session_id}` to poll it, `POST /api/fixture/{session_id}/order`
to act on a decision, and so on — full reference in
[`api/README.md`](api/README.md).

### As a one-off CLI run

Each pipeline also has a standalone script that runs a single hardcoded
fixture end to end — reasoning *and* order placement, useful for local
testing without standing up the API:

```bash
uv run workflows/run_unified_pipeline.py   # unified agent
uv run workflows/run_pipeline.py           # multi-agent pipeline
uv run workflows/run_local_unified_pipeline.py  # dry run — no DB writes, no order
```

Edit the `home_name`/`away_name`/`round_info` arguments in the script itself
to change the fixture.

---

## Tests

```bash
uv run pytest
```

Some tests are marked `live` and make real calls against Sportmonks,
Polymarket, Supabase, or the LLM providers — deselect them for a fast,
offline-safe run:

```bash
uv run pytest -m "not live"
```
