# Stoppage Time API

FastAPI backend for the agent pipelines. Entry point: `api/main.py` (served
via `main.py` → `uvicorn.run("api.main:app", ...)`).

Base URL in local dev: `http://localhost:8000`

## Contents

- [Auth](#auth)
- [Data model](#data-model)
  - [Session status vocabulary](#session-status-vocabulary)
  - [Bet `decision` vocabulary](#bet-decision-vocabulary)
- [Endpoints](#endpoints)
  - [`POST /api/auth/login`](#post-apiauthlogin)
  - [`POST /api/fixture`](#post-apifixture)
  - [`GET /api/fixture/{session_id}`](#get-apifixturesession_id)
  - [`POST /api/fixture/{session_id}/order`](#post-apifixturesession_idorder)
  - [`GET /api/history`](#get-apihistory)
  - [`GET /api/history/{session_id}`](#get-apihistorysession_id)
  - [`GET /api/agent/stats`](#get-apiagentstats)
  - [`GET /health`](#get-health)
- [Schemas](#schemas)
- [Error conventions](#error-conventions)

---

## Auth

Every endpoint is a public read **except** `POST /api/fixture/{session_id}/order`,
which requires a Bearer JWT.

There is exactly one admin account, defined by `ADMIN_USERNAME`/`ADMIN_PASSWORD`
in `config/settings.py` (env-overridable). Get a token from `POST /api/auth/login`,
then send it as:

```
Authorization: Bearer <access_token>
```

Tokens are signed with `JWT_SECRET_KEY`/`JWT_ALGORITHM` and expire after
`JWT_EXPIRE_DAYS` days (all in `config/settings.py`).

CORS: `allow_origins` comes from `ALLOWED_ORIGINS` (comma-separated, default
`"*"`). `allow_credentials` is deliberately `False` — auth is Bearer-token,
not cookies, and a wildcard origin combined with `allow_credentials=True` is
an invalid CORS combination browsers reject outright.

---

## Data model

Three Supabase tables back this API:

- **`sessions`** — one row per pipeline run. `session_id` is prefixed by
  which pipeline produced it: `unified-xxxxxxxx` (single combined LLM call)
  or `live-xxxxxxxx` (multi-agent: planning → tactics/news/h2h → reasoning →
  betting).
- **`agent_bets`** — one row per session's betting decision (created once a
  decision process starts, `session_id` FK). Holds probabilities, market
  prices, the decision itself, and — once an order is actually placed —
  `order_id`/`order_status`/`fill_price`.
- **`agent_logs`** — one row per agent step (`session_id` FK). Every LLM
  call and tool call in a run gets logged here, in order.

A session produces **at most one** bet row today (application-enforced, not
a DB constraint).

### Session status vocabulary

`sessions.status` is updated in near-real-time as a run progresses — poll
`GET /api/fixture/{session_id}` to watch it move:

| Status | Meaning |
|---|---|
| `queued` | Session row just created, nothing has run yet. |
| `planning` | Gathering fixture/market/context data. |
| `tactical analysis` | The tactics LLM call is running. |
| `searching` | A news search call is running. |
| `reasoning` | The reasoning LLM call is running. |
| `betting` | The betting LLM call is running (multi-agent only — decides stake/confirm). |
| `awaiting_order` | A decision has been made (`agent_bets.decision` is `home`/`draw`/`away`, `stake_usd` set) but no order has been placed yet. **This is the state to watch for before calling `POST /order`.** |
| `skipped` | The agent decided not to bet — no order is possible for this session. |
| `completed` | An order was placed successfully. |
| `error` | Something failed (fixture not found, no live market, unparseable LLM output, order rejected, etc). |

Note: the `unified` pipeline never produces `skipped` — its prompt forbids
skipping, it always reaches a `home`/`draw`/`away` decision or `error`.

### Bet `decision` vocabulary

`agent_bets.decision` is one of:

- `pending` — row created, decision not made yet.
- `skip` — agent chose not to bet (no edge, or LLM judgment call).
- `home` / `draw` / `away` — the chosen outcome. Combined with `order_id`
  being set or not, this tells you whether the bet was just decided
  (`awaiting_order`) or actually placed (`completed`).

---

## Endpoints

### `POST /api/auth/login`

Unauthenticated. Form-encoded body (`application/x-www-form-urlencoded`),
not JSON — this is FastAPI's standard `OAuth2PasswordRequestForm`.

**Request** (form fields):

| Field | Type | Notes |
|---|---|---|
| `username` | string | must equal `ADMIN_USERNAME` |
| `password` | string | must equal `ADMIN_PASSWORD` |

**Response** `200` → [`TokenResponse`](#tokenresponse)

**Errors**: `401` if credentials don't match.

```bash
curl -X POST localhost:8000/api/auth/login -d "username=admin&password=..."
```

---

### `POST /api/fixture`

Unauthenticated. Kicks off a full pipeline run (unified or multi-agent) in
the background — the request returns immediately with a `session_id`; the
actual reasoning happens after the response is sent. **Never places an
order** — it stops once a decision is made (`awaiting_order`/`skipped`).

**Request body** → [`FixtureCreateRequest`](#fixturecreaterequest)

**Response** `200` → [`FixtureCreateResponse`](#fixturecreateresponse)

```bash
curl -X POST localhost:8000/api/fixture -H "Content-Type: application/json" \
  -d '{"home":"Argentina","away":"Switzerland","stage":"Quarter-final","agent":"unified","kick_off_time":"2026-07-04T18:00:00Z"}'
# -> {"session_id": "unified-a1b2c3d4"}
```

Notes:
- `agent: "unified"` → `session_id` prefixed `unified-`, runs `agents.unified_agent.run_unified_agent`.
- `agent: "multi-agent"` → `session_id` prefixed `live-`, runs `workflows.run_pipeline.run` (planning → reasoning → betting).
- `kick_off_time` is a best-effort disambiguation hint, not a hard filter. If
  the same two teams meet twice in the tournament, it's used to pick the
  fixture whose actual kickoff is closest to the given time; with 0 or 1
  name matches it's ignored entirely. Accepts an ISO datetime string or a
  unix timestamp string. Fixture resolution otherwise matches on team names
  only (see `service/schedule.py::find_fixture_by_teams`).
- Polling `GET /api/fixture/{session_id}` immediately after this call can
  briefly 404 (the background task hasn't reached `create_session()` yet).
  Retry once.

---

### `GET /api/fixture/{session_id}`

Unauthenticated. Poll this while a run is in flight, and to read the
decision once it lands. Returns the session, the bet row if one exists yet
(`null` otherwise), and every log row for the session so far.

**Response** `200` → [`FixtureStatusResponse`](#fixturestatusresponse)

**Errors**: `404` if no session with this id exists.

```bash
curl localhost:8000/api/fixture/unified-a1b2c3d4
```

---

### `POST /api/fixture/{session_id}/order`

**Requires `Authorization: Bearer <token>`.** The only endpoint that places
a real Polymarket order — this moves real money the moment it succeeds.

Reads the session's bet row and, if it has a placeable decision
(`home`/`draw`/`away`) with no order placed yet, re-fetches a **fresh**
market price (not the reasoning-time snapshot — time may have passed since
the decision was made) and places the order via `service/orders.py`.

**Path param**: `session_id`

**Response** → [`OrderResponse`](#orderresponse), with the HTTP status
reflecting outcome:

| HTTP | `status` field | Meaning |
|---|---|---|
| `200` | `completed` | Order placed successfully. |
| `200` | `already_ordered` | Idempotency guard — an order was already placed for this bet; returns the existing order info instead of placing a second one. |
| `401` | — | Missing/invalid/expired token. |
| `404` | — | No session with this id exists. |
| `409` | `error` | Nothing to order — no bet yet, or `decision` is `pending`/`skip`. |
| `502` | `error` | Order was rejected or failed (bad stake, no live market, upstream error) — see `reason`. |

```bash
curl -X POST localhost:8000/api/fixture/unified-a1b2c3d4/order \
  -H "Authorization: Bearer $TOKEN"
```

Calling this twice on the same session is safe — the second call returns
`already_ordered` rather than placing a duplicate order.

---

### `GET /api/history`

Unauthenticated. Paginated list of **all** bets across every session, most
recent first. Does **not** include per-session logs — use
`GET /api/history/{session_id}` for that.

**Query params**:

| Param | Type | Default | Notes |
|---|---|---|---|
| `limit` | int | `20` | clamped `1`–`100` |
| `offset` | int | `0` | |

**Response** `200` → [`HistoryListResponse`](#historylistresponse)

```bash
curl "localhost:8000/api/history?limit=20&offset=0"
```

---

### `GET /api/history/{session_id}`

Unauthenticated. Full record for one session: the session row, its bet, and
every log entry — the "click into a bet from the history list" view.

**Response** `200` → [`HistoryDetailResponse`](#historydetailresponse)

**Errors**: `404` if the session doesn't exist, **or** if it exists but has
no bet row yet (history implies something concluded — for an in-flight
session, use `GET /api/fixture/{session_id}` instead).

```bash
curl localhost:8000/api/history/unified-a1b2c3d4
```

---

### `GET /api/agent/stats`

Unauthenticated. Aggregate performance stats across all bets.

**Response** `200` → [`StatsResponse`](#statsresponse)

```bash
curl localhost:8000/api/agent/stats
```

**Aggregation definitions** (computed in `api/routes/stats.py`, in Python,
over every row from `agent_bets` — no server-side SQL aggregation today):

- **placed** = `decision` in (`home`, `draw`, `away`) **and** `order_id` is
  set (an order actually went through — a bet that reached `awaiting_order`
  but was never confirmed does **not** count as placed).
- **won** / **lost** = placed **and** settled (`actual_outcome` is set),
  split by `pnl > 0` vs `pnl <= 0`.
- **skipped** = `decision == "skip"`.
- `win_percentage` = won / (won + lost) — over settled bets only, `null` if
  none settled.
- `roi_percentage` = `sum(pnl) / sum(stake_usd) × 100` over settled+placed
  bets — a **pooled** ROI across all bets, not an average of per-bet ROIs.
  `pnl` is profit only (not total payout): a $5 stake with `pnl = +$15`
  means 300% ROI on that bet. `null` if no settled stake to divide by.
- `biggest_profit_usd` / `biggest_loss_usd` = max/min `pnl` among settled
  bets, `null` if none settled.
- `wallet_balance_usd` — live call to the Arena wallet API (not stored).
- `starting_balance_usd` — from `STARTING_BALANCE_USD` in
  `config/settings.py` (default `100.0`), not tracked historically.

---

### `GET /health`

Unauthenticated. `{"status": "ok"}` — liveness check, not wired to any
dependency (DB, LLM, etc).

---

## Schemas

All schemas are Pydantic v2 models. Source of truth: `models/*.py`.

### `SessionOut`
*(`models/common.py`)* — a `sessions` row.

| Field | Type |
|---|---|
| `session_id` | `string` |
| `created_at` | `string \| null` |
| `fixture_name` | `string \| null` |
| `home_team` | `string \| null` |
| `away_team` | `string \| null` |
| `status` | `string \| null` — see [status vocabulary](#session-status-vocabulary) |
| `source` | `string \| null` — `"v2"` (unified) or `"multi_agent"` |

### `BetOut`
*(`models/common.py`)* — an `agent_bets` row.

| Field | Type |
|---|---|
| `id` | `string` |
| `session_id` | `string` |
| `fixture_id` | `string \| number \| null` |
| `fixture_name` | `string \| null` |
| `home_team` / `away_team` | `string \| null` |
| `home_code` / `away_code` | `string \| null` — market outcome short codes |
| `home_probability` / `draw_probability` / `away_probability` | `number \| null` |
| `confidence` | `string \| null` |
| `market_home_price` / `market_draw_price` / `market_away_price` | `number \| null` |
| `edge_pp` | `number \| null` — edge in percentage points |
| `decision` | `string \| null` — see [decision vocabulary](#bet-decision-vocabulary) |
| `stake_usd` | `number \| null` |
| `bet_reason` | `string \| null` — LLM's reasoning for the decision |
| `actual_outcome` | `string \| null` — set once settled |
| `pnl` | `number \| null` — profit only, set once settled |
| `order_id` | `string \| null` — set once an order is actually placed |
| `order_status` | `string \| null` |
| `fill_price` | `number \| null` |
| `created_at` / `settled_at` | `string \| null` |

### `LogEntryOut`
*(`models/common.py`)* — an `agent_logs` row.

| Field | Type |
|---|---|
| `id` | `string` |
| `session_id` | `string` |
| `step_type` | `string` — `Observing` \| `Planning` \| `ToolCalling` \| `Thinking` \| `Reflecting` |
| `tool` | `string` — e.g. `pipeline`, `planning`, `tactics`, `news`, `reasoning`, `betting`, `unified`, `consult_tactics`, `get_fixture_news`, `get_h2h`, `get_head_to_head` |
| `model` | `string \| null` — LLM model used, e.g. `claude-opus-4-8`, `gemini-2.5-flash`; `null` for non-LLM steps |
| `prompt` | `string \| null` |
| `response` | `string \| null` |
| `created_at` | `string \| null` |

### `TokenResponse`
*(`models/auth.py`)*

| Field | Type |
|---|---|
| `access_token` | `string` |
| `token_type` | `string` — always `"bearer"` |

### `FixtureCreateRequest`
*(`models/fixture.py`)*

| Field | Type | Notes |
|---|---|---|
| `home` | `string` | required |
| `away` | `string` | required |
| `stage` | `string` | required — e.g. `"Quarter-final"` |
| `agent` | `"multi-agent" \| "unified"` | required |
| `kick_off_time` | `string \| null` | optional disambiguation hint |

### `FixtureCreateResponse`

| Field | Type |
|---|---|
| `session_id` | `string` |

### `FixtureStatusResponse`

| Field | Type |
|---|---|
| `session` | [`SessionOut`](#sessionout) |
| `bet` | [`BetOut`](#betout) `\| null` |
| `logs` | `LogEntryOut[]` |

### `OrderResponse`

| Field | Type |
|---|---|
| `status` | `string` — `completed` \| `already_ordered` \| `error` |
| `decision` | `string \| null` |
| `stake_usd` | `number \| null` |
| `order_id` | `string \| null` |
| `order_status` | `string \| null` |
| `fill_price` | `number \| null` |
| `reason` | `string \| null` — set on `error` |

### `HistoryListResponse`

| Field | Type |
|---|---|
| `items` | `BetOut[]` |
| `limit` | `number` |
| `offset` | `number` |
| `total` | `number` — total rows matching, for pagination UI |

### `HistoryDetailResponse`

| Field | Type |
|---|---|
| `session` | [`SessionOut`](#sessionout) |
| `bet` | [`BetOut`](#betout) |
| `logs` | `LogEntryOut[]` |

### `StatsResponse`

| Field | Type |
|---|---|
| `wallet_balance_usd` | `number` |
| `starting_balance_usd` | `number` |
| `bets_placed` | `number` |
| `bets_won` | `number` |
| `bets_lost` | `number` |
| `bets_skipped` | `number` |
| `win_percentage` | `number \| null` |
| `roi_percentage` | `number \| null` |
| `biggest_profit_usd` | `number \| null` |
| `biggest_loss_usd` | `number \| null` |

---

## Error conventions

Standard FastAPI error shape unless noted otherwise:

```json
{ "detail": "human-readable message" }
```

`POST /api/fixture/{session_id}/order` is the one exception — its
non-2xx bodies are still a full [`OrderResponse`](#orderresponse) (with
`status: "error"` and a `reason`), not a bare `detail` string, so a client
can render it the same way as a success response.

Interactive schema/try-it-out: `GET /docs` (Swagger UI) and `GET /redoc`,
both auto-generated by FastAPI from these same models.
