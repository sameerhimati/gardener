# Langfuse — Build-Ready Reference for Gardener

> Fetched: June 12, 2026 | SDK version: `langfuse==4.7.1` (v4 GA, March 2026)

---

## 1. What It Is

Langfuse is an open-source LLM observability and engineering platform that traces agent turns, tool calls, generations, and custom spans into a searchable UI. As of January 2026 it is owned by ClickHouse (acquired 2026-01-16) and remains MIT-licensed for self-hosted use. Its entire backend storage — Cloud and self-hosted — runs on ClickHouse, which is the on-thesis angle for Gardener.

---

## 2. Setup: Cloud Quickstart

**Sign up:** https://cloud.langfuse.com → create project → copy `pk-lf-…` and `sk-lf-…` keys.

```bash
pip install langfuse                                  # v4.7.1, requires Python >=3.10
pip install opentelemetry-instrumentation-anthropic  # for auto-instrumentation path
```

```bash
# .env
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_BASE_URL=https://cloud.langfuse.com   # EU: https://eu.cloud.langfuse.com
ANTHROPIC_API_KEY=sk-ant-...
```

```python
from langfuse import get_client

langfuse = get_client()          # singleton; reads env vars
assert langfuse.auth_check()
```

---

## 3. SDK for Our Use Case

### Path A — Auto-instrument via OTEL (recommended for agent loop)

```python
from opentelemetry.instrumentation.anthropic import AnthropicInstrumentor
AnthropicInstrumentor().instrument()
```

```python
import anthropic
from langfuse import get_client, observe

langfuse = get_client()
client = anthropic.Anthropic()

@observe(name="agent-turn")          # wraps the entire turn as a root span
def run_turn(messages: list) -> str:
    response = client.messages.create(
        model="claude-opus-4-20250514",
        max_tokens=4096,
        messages=messages,
    )
    # AnthropicInstrumentor auto-captures model, input, output, tokens
    return response.content[0].text
```

### Path B — Manual spans (for the lint worker)

```python
from langfuse import get_client

langfuse = get_client()

def run_lint_worker(events: list[dict]) -> list[dict]:
    with langfuse.start_as_current_observation(
        as_type="span",
        name="lint-worker",
        input={"event_count": len(events)},
    ) as span:
        diffs = mine_events(events)
        span.update(
            output={"diff_count": len(diffs)},
            metadata={"source": "clickhouse-events-table"},
        )
        return diffs
```

### Combining: full agent loop trace

```python
from langfuse import get_client, observe, propagate_attributes
from opentelemetry.instrumentation.anthropic import AnthropicInstrumentor

AnthropicInstrumentor().instrument()
langfuse = get_client()
client = anthropic.Anthropic()

@observe(name="gardener-session")
def agent_loop(user_input: str, session_id: str, user_id: str) -> str:
    with propagate_attributes(
        session_id=session_id,
        user_id=user_id,
        tags=["agent", "gardener"],
    ):
        messages = [{"role": "user", "content": user_input}]
        while True:
            response = client.messages.create(
                model="claude-opus-4-20250514",
                max_tokens=4096,
                tools=TOOLS,
                messages=messages,
            )
            if response.stop_reason == "end_turn":
                return response.content[0].text
            messages = handle_tool_calls(response, messages)
```

### Flush in short-lived processes

```python
langfuse.flush()    # blocks until queue drains; call before process exit
```

### Manual generation span

```python
with langfuse.start_as_current_observation(
    as_type="generation",
    name="llm-call",
    model="claude-opus-4-20250514",
    input=messages,
) as gen:
    response = client.messages.create(...)
    gen.update(
        output=response.content[0].text,
        usage={
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
        },
    )
```

---

## 4. The ClickHouse Angle

### Self-host architecture

| Component | Role |
|---|---|
| ClickHouse >=24.3 | Traces, observations, scores (OLAP) |
| PostgreSQL | Users, projects, prompts (OLTP) |
| Redis / Valkey | Queue + cache |
| S3 / blob store | Event persistence, multimodal |
| 2 app containers | Web server + async worker |

Docker Compose works for dev/single-node. Production needs Kubernetes (Helm) or Railway. All components must run with `TZ=UTC`.

### Querying Langfuse's ClickHouse directly

**You can** (self-hosted): tables `traces`, `observations`, `scores` — all ReplacingMergeTree.

**Gotcha: schema is not a stable API.** Langfuse warns: *"The ClickHouse schema is not a stable API contract. Major upgrades can alter tables and columns without notice."* The v4 architecture (preview March 2026) is migrating to a single wide observations table with `user_id`, `session_id`, `tags` propagated onto every row.

### Verdict on mining Langfuse ClickHouse vs your own events table

**Cloud + your own parallel events table is the sane play:**

1. Self-host is a half-day of infra minimum, and schema instability means re-validating queries on every upgrade.
2. The lint worker's mine target and Langfuse's trace store are different granularities — your events table can be purpose-built (event_type, vault_path, diff_proposed) while observations are observability-shaped.
3. Best of both: Langfuse Cloud for the UI (free tier covers our volume), own events table for mining. Complementary, not redundant.
4. Later self-host option: `CLICKHOUSE_READ_ONLY_URL` + read replica for the lint worker once the v4 wide table lands.

**Export alternative (Cloud):** Blob Storage Export (S3/GCS/Azure, scheduled) — observations as Parquet/JSON → `Langfuse Cloud → Blob Export → DuckDB read → lint worker`.

---

## 5. Gotchas & Free-Tier Limits

| Item | Detail |
|---|---|
| Free (Hobby) | 50,000 units/month, 30-day retention, 2 users |
| Unit definition | 1 trace = 1 unit; 1 observation = 1 unit; 1 score = 1 unit. A 3-tool-call agent turn ≈ 5 units. |
| Overage | Not available on Hobby — hard cutoff at 50k |
| Core plan | $29/mo, 100k units, unlimited users, 90-day retention |
| `langfuse.flush()` | Required before process exit in scripts; omitting silently drops traces |
| OTEL gRPC | Not supported — HTTP/JSON and HTTP/protobuf only |
| Self-host ClickHouse | Must be >=24.3, timezone UTC |
| SDK v4 Python | >=3.10 |
| Raw OTEL auth | `base64("pk-lf-...:sk-lf-...")` — easy to get wrong |

---

## 6. What Changed Since Early 2025

| Period | Change |
|---|---|
| May 2025 | Python SDK v3 beta: OTEL-based, `get_client()` singleton, W3C trace IDs, automatic context propagation |
| June 2025 | v3 GA |
| March 2026 | Python SDK **v4** (latest 4.7.1). Largely v3-compatible; better streaming, LangGraph, Azure chunk handling |
| January 2026 | **ClickHouse acquires Langfuse**; remains MIT open-source |
| March 2026 | Langfuse v4 platform preview: wide single-table ClickHouse model; 10x dashboard perf |
| Ongoing | `@observe` stable; `start_as_current_observation()` is the recommended low-level primitive over old `start_span()`/`start_generation()` |

**Breaking from v2:** `langfuse.trace()` / `span.generation()` chain pattern is gone. Use `start_as_current_observation(as_type="generation")` or `@observe`.

---

## 7. Verdict

Langfuse is **load-bearing for the observability layer** — turn-by-turn trace UI and token accounting in ~20 lines — but the lint worker's mining source should be your own purpose-built events table, not Langfuse's internal schema (explicitly unstable, UI-optimized). Note: $350 prize for "most impressive use of Langfuse" inside the ClickHouse track.

---

## 8. Links (fetched June 12, 2026)

- https://langfuse.com/integrations/model-providers/anthropic
- https://langfuse.com/docs/observability/sdk/overview
- https://langfuse.com/changelog/2025-05-23-otel-based-python-sdk
- https://langfuse.com/changelog/2025-06-05-python-sdk-v3-generally-available
- https://langfuse.com/self-hosting/deployment/infrastructure/clickhouse
- https://langfuse.com/blog/2026-03-10-simplify-langfuse-for-scale
- https://langfuse.com/blog/joining-clickhouse
- https://langfuse.com/pricing
- https://langfuse.com/docs/api-and-data-platform/features/query-via-sdk
- https://pypi.org/project/langfuse/ (v4.7.1, May 29 2026)
- https://langfuse.com/integrations/frameworks/claude-agent-sdk
