# ClickHouse Cloud — Build-Ready Guide for Gardener

_Researched against live docs, June 12 2026. Links at bottom._

---

## 1. What It Is

ClickHouse is a column-oriented OLAP database built for sub-second analytical queries on billions of rows. ClickHouse Cloud is the fully managed SaaS offering: serverless auto-pause, replicated storage, and a remote MCP server now GA for AI-agent workflows. As of 26.3 LTS (April 2026), async inserts are **on by default** and the JSON data type is **production-ready** (since 25.3).

---

## 2. Setup

### 2a. Cloud signup

1. Go to `https://console.clickhouse.cloud/signUp`
2. Sign in via email, Google, or Microsoft SSO. New orgs land on the **Scale** tier by default (3 replicas, 4 vCPUs, 16 GiB RAM each).
3. **Trial:** $300 free credits, 30 days. No permanent free tier — after the trial you must choose a paid plan or self-host. Basic plan starts at ~$66/mo (6 h/day active, AWS us-east-1); 24/7 same config is ~$186/mo. Storage: $25.30/TB-month. Basic plan caps at 500 GB compressed storage + 500 GB backup.
4. Once the service is created, click **Connect** in the left nav. The modal shows:
   - **Host:** `<uuid>.<region>.<csp>.clickhouse.cloud`
   - **Port:** `8443` (HTTPS) or `9440` (native TLS)
   - **Username:** `default`
   - **Password:** your service password (copy it now — shown once)

### 2b. Python install

```bash
# Core (sync)
pip install clickhouse-connect==1.3.0   # latest as of 2026-06-11; requires Python 3.10–3.14

# With async support
pip install "clickhouse-connect[async]==1.3.0"   # pulls aiohttp >= 3.9.0
```

**Do not use** the legacy `clickhouse-driver` (native TCP, community-maintained) or `aiochclient` — `clickhouse-connect` is the official ClickHouse Inc. client and is the one docs reference.

---

## 3. SDK Usage

### 3a. Connect

```python
import clickhouse_connect

# Sync client
client = clickhouse_connect.get_client(
    host="abc123.us-east-1.aws.clickhouse.cloud",
    port=8443,
    username="default",
    password="YOUR_PASSWORD",
    secure=True,
)

# Async client (same params)
import asyncio
async_client = await clickhouse_connect.get_async_client(
    host="abc123.us-east-1.aws.clickhouse.cloud",
    port=8443,
    username="default",
    password="YOUR_PASSWORD",
    secure=True,
)
```

Both accept a `settings={}` dict for per-connection ClickHouse settings.

### 3b. Create tables

```sql
-- events: append-only log of every agent turn + tool call
CREATE TABLE IF NOT EXISTS gardener.events
(
    event_id     UUID          DEFAULT generateUUIDv4(),
    user_id      String,
    session_id   String,
    ts           DateTime64(3) DEFAULT now64(),
    event_type   LowCardinality(String),   -- 'turn', 'tool_call', 'tool_result'
    payload      JSON,                      -- arbitrary turn/tool data; production-ready ≥25.3
    tool_name    LowCardinality(String)    DEFAULT '',
    success      Nullable(Bool),
    duration_ms  Nullable(UInt32)
)
ENGINE = MergeTree
PARTITION BY toYYYYMM(ts)
ORDER BY (user_id, ts, event_id)   -- user_id first: most queries filter by user
TTL ts + INTERVAL 90 DAY;

-- lint_findings: one row per proposed vault change
CREATE TABLE IF NOT EXISTS gardener.lint_findings
(
    finding_id   UUID          DEFAULT generateUUIDv4(),
    created_at   DateTime64(3) DEFAULT now64(),
    rule         LowCardinality(String),   -- e.g. 'stale_fact', 'contradiction', 'redundancy'
    severity     LowCardinality(String),   -- 'info', 'warn', 'error'
    target_path  String,                   -- vault file path
    description  String,
    proposed_diff String,                  -- unified diff text
    status       LowCardinality(String) DEFAULT 'pending',  -- 'pending','accepted','rejected'
    resolved_at  Nullable(DateTime64(3))
)
ENGINE = ReplacingMergeTree(resolved_at)
PARTITION BY toYYYYMM(created_at)
ORDER BY (status, rule, finding_id);
-- ReplacingMergeTree: dedupes on (status, rule, finding_id) during merges;
-- use FINAL in queries if you need strongly deduplicated reads.
```

**Engine rationale:**
- `events`: pure MergeTree — append-only, never updated. ORDER BY `(user_id, ts, event_id)` makes per-user time-range scans fast.
- `lint_findings`: ReplacingMergeTree on `resolved_at` — findings get status updates (`pending` → `accepted/rejected`). The versioning column is timestamp so the latest write wins after merge. Query with `FINAL` when accuracy matters or use `argMax(status, resolved_at)` for eventual reads.

### 3c. Insert events (agent loop)

```python
# Async inserts are ON BY DEFAULT in 26.3 LTS — server auto-batches small inserts.
# Explicit settings below are optional but recommended for durability.

settings = {
    "async_insert": 1,
    "wait_for_async_insert": 1,        # waits for server flush confirmation (safe default)
    "async_insert_busy_timeout_ms": 500,  # flush every 500 ms or when buffer fills
}

# Sync insert (fine for low-volume; server still batches)
client.insert(
    "gardener.events",
    [
        ["user-123", "sess-abc", "turn", '{"role":"user","text":"hello"}', "", None, None],
        ["user-123", "sess-abc", "tool_call", '{"tool":"search","args":{"q":"climate"}}', "search", None, 120],
    ],
    column_names=["user_id", "session_id", "event_type", "payload", "tool_name", "success", "duration_ms"],
    settings=settings,
)

# Async insert (high-concurrency agent loop)
await async_client.insert(
    "gardener.events",
    rows,
    column_names=["user_id", "session_id", "event_type", "payload", "tool_name", "success", "duration_ms"],
    settings=settings,
)
```

For chatty agents: fire individual inserts with `wait_for_async_insert=1`; the server coalesces them. No need for an application-side queue. If you want fire-and-forget with higher throughput, set `wait_for_async_insert=0` — but accept possible data loss on crash.

### 3d. Lint worker queries

```python
# 1. Recent events for a user (last 30 min)
result = client.query(
    """
    SELECT ts, event_type, tool_name, success, payload
    FROM gardener.events
    WHERE user_id = {user_id:String}
      AND ts >= now() - INTERVAL 30 MINUTE
    ORDER BY ts DESC
    LIMIT 200
    """,
    parameters={"user_id": "user-123"},
)

# 2. Facts not referenced in N minutes — staleness check
result = client.query(
    """
    SELECT
        payload.path AS fact_path,      -- JSON subcolumn extraction
        max(ts) AS last_seen,
        now() - max(ts) AS age
    FROM gardener.events
    WHERE event_type = 'turn'
      AND JSONHas(payload, 'path')
    GROUP BY fact_path
    HAVING age > INTERVAL {stale_minutes:UInt32} MINUTE
    ORDER BY age DESC
    LIMIT 100
    """,
    parameters={"stale_minutes": 60},
)

# 3. Tool failure counts (last 24 h)
result = client.query(
    """
    SELECT
        tool_name,
        countIf(success = false) AS failures,
        countIf(success = true)  AS successes,
        round(countIf(success = false) / count() * 100, 1) AS failure_pct
    FROM gardener.events
    WHERE event_type = 'tool_call'
      AND ts >= now() - INTERVAL 24 HOUR
    GROUP BY tool_name
    ORDER BY failures DESC
    """,
)

# 4. Pending lint findings (for UI / next diff batch)
result = client.query(
    """
    SELECT finding_id, rule, severity, target_path, description, proposed_diff
    FROM gardener.lint_findings FINAL    -- FINAL deduplicates ReplacingMergeTree
    WHERE status = 'pending'
    ORDER BY severity DESC, created_at ASC
    LIMIT 50
    """,
)

rows = result.result_rows
```

**JSON column access in 26.3+:** `payload.some.path` subcolumn syntax works directly; `JSONExtract` now accepts JSON-typed columns (not just strings). Bloom filter skip indexes on `JSONAllPaths(payload)` can speed up lint scans over large payloads.

---

## 4. Gotchas and Free Tier Notes

| Concern | Detail |
|---|---|
| No permanent free tier | $300 / 30 days only. Burn rate on a demo project: ~$2–5/day idle. |
| Basic plan storage cap | 500 GB compressed. More than enough for millions of events. |
| Auto-pause | Services idle-pause after inactivity (configurable). Cold-start latency is 2–10 s. Fine for lint worker cron; bad for synchronous user-facing queries. |
| JSON in Basic plan | JSON type is fully supported on Basic. No tier restriction. |
| ReplacingMergeTree + FINAL | FINAL triggers a synchronous merge at query time — can be slow on large tables. At demo scale (<1M rows) it's fine. |
| async_insert deduplication | `async_insert_deduplicate=1` only works on Replicated* engines. Standard MergeTree events table doesn't deduplicate; idempotent inserts are not safe by default. |
| Part count | Async inserts reduce part explosion, but on the Basic plan with 1 replica avoid inserting at sub-100ms intervals even with async enabled — monitor part count via `system.parts`. |
| clickhouse-connect port | Use **8443** (HTTPS) for Cloud, not 9440 (native TLS). Both work, but 8443 is the HTTP interface the library is optimized for. |

---

## 5. What Changed Since Early 2025

| What | When | Impact |
|---|---|---|
| JSON type → production ready | 25.3 (early 2025) | Use `JSON` columns in prod; `Object('json')` is deprecated |
| `JSONExtract` on JSON-typed columns | 26.3 (Apr 2026) | Cleaner lint queries; no cast required |
| JSON type hints as metadata-only op | 26.3 | Add/change type hints without rewriting data |
| Async inserts on by default | 26.3 | No config needed for basic batching |
| Async insert deduplication | 26.3 | Consistent dedup for regular + async inserts (Replicated engines) |
| clickhouse-connect 1.x (was 0.x) | 2025 | `get_async_client()` native aiohttp; 1.0+ drops legacy pattern |
| clickhouse-connect 1.3.0 | 2026-06-11 | Large params as POST body (avoids HTTP 414); structured error codes; Python 3.14 free-threading wheels |
| Remote MCP server beta | Mar 2026 | Cloud exposes `run_select_query`, `list_databases`, `list_tables` over OAuth MCP — direct Python client is simpler for our use |
| `Object('json')` deprecated | ≥25.3 | Do not use; migrate to `JSON` type |
| `clickhouse-driver` (TCP) | ongoing | Not maintained by ClickHouse Inc.; stick to `clickhouse-connect` |

---

## 6. Verdict

ClickHouse is **load-bearing** for Gardener: the events→lint→diff loop is analytically structured (aggregations, time-range scans, grouping by user/tool) and ClickHouse's columnar engine + JSON type + async inserts handle the chatty-agent write pattern and sub-second lint queries better than Postgres or SQLite at any non-trivial scale. The $300 trial covers months of development.

---

## 7. Links (fetched June 12 2026)

- [ClickHouse Cloud pricing](https://clickhouse.com/pricing)
- [Billing overview / trial details](https://clickhouse.com/docs/cloud/manage/billing/overview)
- [Cloud quick start](https://clickhouse.com/docs/cloud/get-started/cloud-quick-start)
- [Python client docs (advanced usage)](https://clickhouse.com/docs/integrations/language-clients/python/advanced-usage)
- [Designing the async-native Python client](https://clickhouse.com/blog/python-async-native-client)
- [clickhouse-connect on PyPI (v1.3.0)](https://pypi.org/project/clickhouse-connect/)
- [clickhouse-connect CHANGELOG](https://github.com/ClickHouse/clickhouse-connect/blob/main/CHANGELOG.md)
- [JSON data type docs](https://clickhouse.com/docs/sql-reference/data-types/newjson)
- [ClickHouse 26.3 LTS release blog](https://clickhouse.com/blog/clickhouse-release-26-03)
- [Async inserts guide](https://oneuptime.com/blog/post/2026-03-31-clickhouse-how-to-use-async-inserts-in-clickhouse/view)
- [MergeTree engine docs](https://clickhouse.com/docs/engines/table-engines/mergetree-family/mergetree)
- [MCP server for ClickHouse Cloud](https://clickhouse.com/docs/use-cases/AI/MCP)
- [Remote MCP server beta announcement](https://clickhouse.com/blog/agentic-analytics-ask-ai-agent-and-remote-mcp-server-beta-launch)
