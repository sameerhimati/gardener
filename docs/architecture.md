# Gardener — Build Contract

> Source of truth for module layout, interfaces, API, and schemas. Written 2026-06-12 (hackathon day).
> Any agent (human or Claude) writing code reads this first. If you need to deviate, update this file in the same change.

## Framing (pitch-level, from Sameer)

**Gardener is your agent in your garden.** The agent is the main interface — you talk to it, and it tends visible surfaces around itself: the watches it's running (each a conversation you can open and steer), the memory vault it keeps (readable markdown — the *present* state of what it believes), and the event/correction history (ClickHouse — the *past*). Self-maintaining memory is the feature that makes the agent durable long-term, not the headline. The garden has a public gate: the correction changelog publishes to cited.md, where other agents and AI search can cite it. Generative UI (OpenUI/C1) renders agent outputs as live components *inside* the chat — garnish slot, never the host of the agent loop (C1 owns the LLM call; our loop is hand-written).

## The demo arc (what must work, in order of importance)

1. User chats with the **main agent**; it can act (web fetch, vault writes) — every turn/tool-call/memory-write logged as an **event**.
2. User asks for a **standing watch** ("watch Zillow for houses in 77005"). The agent spawns it via the `spawn_watch` tool → the watch appears as its **own chat** in the UI.
3. User opens the watch chat and **steers** it ("only 3+ bd, 1500+ sqft") → steering is **distilled into the preference vault** (visible markdown diff).
4. Watch **cycles run unattended** (scheduler + manual trigger for demo determinism): fetch sources → evaluate against current preferences → report hits into the watch chat.
5. The **lint worker** audits vault vs. recent events → **contradiction findings** with unified diffs → auto-applies high-confidence fixes, queues the rest for one-click approval in the UI.
6. The correction **changelog publishes to cited.md** via Senso CLI.

Cut order if behind: cited.md publish → Langfuse → Composio → staleness rule. Never cut: event logging, watches-as-chats, steering→preference distillation, contradiction lint with visible diff.

## Layout

```
backend/
  app.py                  # FastAPI app + all routes
  requirements.txt
  agent/
    loop.py               # ★ HAND-WRITTEN BY SAMEER — core agent loop. Skeleton on disk. DO NOT GENERATE.
    loop_stub.py          # echo/fake loop so plumbing+UI are testable before loop.py lands
    tools.py              # tool registry (schemas + impls)
    prompts.py            # system prompts: orchestrator, watch_runner, distiller
  core/
    ch.py                 # ClickHouse client + schema init
    events.py             # event log (ClickHouse, JSONL fallback)
    vault.py              # markdown preference vault
    diffs.py              # unified diff make/apply
    llm.py                # plain LLM completions (Anthropic; Pioneer if key set) — for lint + distiller
    store.py              # watches + chat sessions persistence (JSON files under data/)
  watches/
    runner.py             # watch cycle execution + asyncio scheduler
  worker/
    lint_worker.py        # lint plumbing: load context → run rules → write findings → auto-apply
    rules/
      contradiction.py    # ★ HAND-WRITTEN BY SAMEER — skeleton on disk. DO NOT GENERATE.
web/                      # Next.js 14 App Router + Tailwind
vault/                    # the memory vault (markdown, committed example seeds ok)
data/                     # runtime state (gitignored): sessions, watches, jsonl fallbacks
scripts/
  dev.sh                  # run backend (uvicorn :8000) + web (next dev :3000)
  seed_demo.py            # seed a demo-ready state (vault + contradicting events)
  init_db.py              # create ClickHouse tables
publish/
  senso_publish.py        # changelog → cited.md via Senso CLI (see docs/senso-cited.md)
render.yaml               # web service + cron job (NOT Workflows — see docs/render.md)
.env.example
```

## Module interfaces (exact signatures — parallel agents code against these)

```python
# core/events.py
def log_event(kind: str, payload: dict, session_id: str = "", user_id: str = "sameer") -> None
    # NEVER raises. ClickHouse if CLICKHOUSE_URL set, else appends data/events.jsonl. Adds ts + event_id.
def recent_events(limit: int = 200, kinds: list[str] | None = None) -> list[dict]

# event kinds
# user_msg, assistant_msg, tool_call, tool_result, memory_write,
# watch_spawn, watch_cycle, watch_steer, lint_run, lint_finding, lint_apply, publish

# core/vault.py  (vault root = ./vault, paths relative like "preferences/housing.md")
def list_files() -> list[dict]            # [{path, title, updated}]
def read(path: str) -> str                # raises FileNotFoundError
def write(path: str, content: str, source: str) -> None   # logs memory_write event, source = provenance string
def all_files() -> dict[str, str]

# core/diffs.py
def make_diff(path: str, old: str, new: str) -> str        # unified diff
def apply_diff(path: str, diff: str) -> None               # applies to vault file, logs memory_write

# core/llm.py
def complete(prompt: str, system: str = "", model: str | None = None) -> str
    # Pioneer (OpenAI-compatible) if PIONEER_API_KEY set, else Anthropic. Sync, simple.

# core/store.py  (JSON persistence under data/)
def create_session(kind: str = "main", title: str = "") -> str            # returns session_id
def get_messages(session_id: str) -> list[dict]                          # [{role, content, ts}]
def append_message(session_id: str, role: str, content: str) -> None
def create_watch(task: str, cadence_sec: int = 120) -> dict              # creates its session; returns watch
def list_watches() -> list[dict]   # [{id, task, session_id, status, last_run, last_result}]
def get_watch(watch_id: str) -> dict
def update_watch(watch_id: str, **fields) -> None

# agent/tools.py
TOOLS: list[dict]      # Anthropic tool schema dicts: {name, description, input_schema}
def execute_tool(name: str, tool_input: dict, session_id: str) -> str    # logs tool_call/tool_result events
# tools: web_fetch(url) · vault_read(path) · vault_write(path, content) ·
#        spawn_watch(task, cadence_sec) · list_watches() · save_preference(topic, fact)

# agent/loop.py — ★ SAMEER
def run_turn(session_id: str, user_message: str, system: str | None = None) -> str

# agent/loop_stub.py — same signature; used when loop.py raises NotImplementedError
def run_turn(session_id: str, user_message: str, system: str | None = None) -> str

# watches/runner.py
def run_cycle(watch_id: str) -> dict       # builds watch context (task + vault prefs) → agent run_turn on the
                                           # watch's session with prompts.WATCH_RUNNER → logs watch_cycle event
def start_scheduler() -> None              # asyncio task: due watches → run_cycle

# worker/lint_worker.py
def run_lint(auto_apply_threshold: float = 0.8) -> list[dict]
    # gathers recent_events + vault all_files → calls each rule → writes findings (CH/JSONL) →
    # auto-applies diffs with confidence >= threshold (logs lint_apply) → returns findings

# worker/rules/contradiction.py — ★ SAMEER
def find_contradictions(events: list[dict], vault: dict[str, str]) -> list[Finding]

# Finding (pydantic model in worker/lint_worker.py)
# {id, rule, vault_path, summary, diff, confidence: float, severity, status: open|auto_applied|approved|rejected, ts}
```

The chat endpoint resolves the loop like:

```python
from backend.agent import loop, loop_stub
try:
    reply = loop.run_turn(session_id, msg)
except NotImplementedError:
    reply = loop_stub.run_turn(session_id, msg)
```

## HTTP API (FastAPI, port 8000, CORS open to localhost:3000)

```
POST /chat                      {session_id?, message}        → {session_id, reply}
GET  /sessions/{id}/messages                                  → [{role, content, ts}]
GET  /watches                                                 → [watch]
POST /watches                   {task, cadence_sec?}          → watch          (manual create; agent uses spawn_watch tool)
POST /watches/{id}/run                                        → cycle result   (demo determinism)
POST /watches/{id}/message      {message}                     → {reply}        (steering — logs watch_steer, triggers distiller)
GET  /vault                                                   → [{path, title, updated}]
GET  /vault/file?path=...                                     → {path, content}
GET  /findings                                                → [Finding]
POST /findings/{id}/apply | /findings/{id}/reject             → Finding
POST /lint/run                                                → [Finding]      (manual trigger for demo)
GET  /events/recent?limit=50                                  → [event]
POST /distill                   {text, source?}               → {written: [{topic, fact}]}   (onboarding answers / any free text → vault)
GET  /demo/listings  ·  POST /demo/listings/add               → demo fixture (docs/watch-layer.md)
```

## UI direction (updated 12:40 PM per Sameer)

Notion-like: **light mode default**, editorial, calm — generous whitespace, near-white background, ink text, moss green as the single accent. First run (no `gardener_onboarded` localStorage flag) opens **onboarding as a conversation-styled form**: Gardener asks ~4 questions one at a time (who are you / what are you actively looking for / what should I keep an eye on / hard preferences), each answer POSTs to `/distill`, the planted facts render as they land ("planted: …"), final step offers to create a watch from the answers and drops you into the app. Skippable.

## Steering → preference distillation

On `POST /watches/{id}/message`: append the message to the watch chat, log `watch_steer`, then call the distiller (core/llm.complete with prompts.DISTILLER) to extract durable preferences from the steering text → `vault.write("preferences/<topic>.md", ...)` with source = `watch:<id>`. This is what the lint worker later audits for contradictions.

## ClickHouse (see docs/clickhouse.md for DDL details, port 8443, clickhouse-connect)

- `events` — MergeTree, ORDER BY (user_id, ts, event_id), payload JSON
- `lint_findings` — ReplacingMergeTree(resolved_at)
- No creds → everything falls back to `data/events.jsonl` / `data/findings.jsonl` transparently. The app must run with zero env vars except ANTHROPIC_API_KEY.

## Vault file format

```markdown
---
topic: housing
updated: 2026-06-12
---
- Looking to buy in Houston 77005 (src: watch:w_abc123 2026-06-12)
- Wants 3+ bedrooms, 1500+ sqft (src: watch:w_abc123 2026-06-12)
```

One fact per bullet, provenance suffix mandatory — the lint rule depends on it.

## Env (.env at repo root; backend loads via python-dotenv)

```
ANTHROPIC_API_KEY=            # required
CLICKHOUSE_URL=               # optional → JSONL fallback (https://...clickhouse.cloud:8443)
CLICKHOUSE_USER= CLICKHOUSE_PASSWORD=
PIONEER_API_KEY= PIONEER_BASE_URL=   # optional → lint/distiller use Anthropic
SENSO_API_KEY=                # optional (tgr_...)
COMPOSIO_API_KEY=             # optional garnish
LANGFUSE_PUBLIC_KEY= LANGFUSE_SECRET_KEY=   # optional garnish
```

## Conventions

- Python 3.12, type hints, no async where sync is fine (except the watch scheduler). Keep modules small and flat.
- Anthropic model: `claude-sonnet-4-6` for the main loop (fast), overridable via env MODEL.
- Web UI talks to `NEXT_PUBLIC_API_URL` (default http://localhost:8000), polls findings/watches every 3s. Plain Tailwind, no component library.
- Don't touch the two ★ files. Don't run git commands unless you own the commit (main build session does).
```
