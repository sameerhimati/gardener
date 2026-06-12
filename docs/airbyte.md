# Airbyte (PyAirbyte) — Build-Ready Guide for Gardener

*Researched June 12, 2026. All claims verified against live docs.*

---

## 1. What It Is

Airbyte is an open-source ELT platform with 600+ connectors. **PyAirbyte** (`pip install airbyte`, currently v0.47.1) is the embedded Python library that runs connectors in-process — no Docker, no hosted service, no orchestration layer required. It writes to a local DuckDB cache by default; data surfaces as Pandas DataFrames or SQL tables. For production sync scheduling, add Airflow/Dagster or use Airbyte Cloud.

---

## 2. Lightest Path: PyAirbyte Setup

**Requirements:** Python >=3.10, <3.13. Install `uv` first (v0.29.0+ uses it by default).

```bash
pip install airbyte          # ~30 seconds with uv
```

**Minimal working example (source-faker, no auth):**

```python
import airbyte as ab

source = ab.get_source(
    "source-faker",
    config={"count": 1_000},
    install_if_missing=True,
)
source.check()
source.select_all_streams()
result = source.read()         # writes to local DuckDB by default

df = result["users"].to_pandas()
print(df.head())
```

---

## 3. Our Use Case: Pull Gmail → DuckDB

**Gmail connector name:** `gmail`.

**Step 1 — Google Cloud setup (one-time, ~20 min):**
1. Enable Gmail API at console.cloud.google.com
2. Create OAuth 2.0 client (Web application type)
3. Add scope: `https://www.googleapis.com/auth/gmail.readonly`
4. Exchange auth code for refresh token (Google OAuth2 playground or `requests-oauthlib`)

**Step 2 — PyAirbyte code:**

```python
import airbyte as ab
import duckdb

source = ab.get_source(
    "gmail",
    config={
        "credentials": {
            "client_id": "YOUR_CLIENT_ID",
            "client_secret": "YOUR_CLIENT_SECRET",
            "client_refresh_token": "YOUR_REFRESH_TOKEN",
        },
        "start_date": "2026-01-01T00:00:00Z",
    },
    install_if_missing=True,
)
source.check()
source.select_streams(["messages_details"])   # full content; "messages" = stubs only
result = source.read()                        # → .cache/airbyte_cache.duckdb

con = duckdb.connect(".cache/airbyte_cache.duckdb")
df = con.execute("SELECT * FROM messages_details LIMIT 20").df()
```

**Alternative: land in ClickHouse directly** (destination v2.1.24, all sync modes):

```python
destination = ab.get_destination(
    "destination-clickhouse",
    config={
        "host": "localhost",
        "port": "8123",
        "database": "gardener",
        "username": "airbyte",
        "password": "...",
        "protocol": "http",
        "ssl": False,
    },
    docker_image=True,           # ClickHouse destination requires Docker
)
destination.write(result)
```

**Note:** Most destination connectors (incl. ClickHouse) require Docker. SQL cache types (DuckDB, Postgres) are native Python. For a hackathon, **DuckDB cache → query directly** avoids Docker entirely.

---

## 4. Gotchas, Limits, Setup-Time Reality

- **Python version:** 3.10–3.12 only. 3.13 explicitly excluded.
- **Gmail OAuth friction:** Open-source/PyAirbyte requires manually obtaining the refresh token. Budget 20–30 min Google Cloud Console setup. Airbyte Cloud does one-click OAuth but costs credits.
- **`messages` vs `messages_details`:** `messages` returns `{id, threadId}` stubs only. Sync `messages_details` for content — hits Gmail API per message (15,000 units/user/min quota; `messages.get` = 5 units).
- **ClickHouse destination needs Docker.** Pattern without Docker: PyAirbyte → DuckDB cache → your ETL writes to ClickHouse.
- **No scheduling/orchestration** in PyAirbyte — you call it from your own scheduler.
- **Airbyte Cloud free tier:** 1,000 Agent Operations/month free (the new "Airbyte Agents" product); data replication is volume-based, no permanent free tier. Self-hosted OSS fully free.

**Realistic one-source setup time:**
- source-faker: 5 min
- GitHub or Notion (API key): 15–20 min
- Gmail (OAuth): **45–60 min** incl. Google Cloud setup
- ClickHouse destination via Docker: +15–20 min

---

## 5. What Changed Since Early 2025

- **v0.29.0:** default connector installer pip → `uv` (3–5x faster installs).
- **v0.41.0:** namespace support for destinations.
- **v0.46.0:** workspace management via Python API; CLI migrated Click → Cyclopts.
- **v0.47.0 (June 3, 2026):** MCP features — PyAirbyte powers the Airbyte Cloud Replication MCP; connector ops exposed as MCP tools for AI agents.
- **ClickHouse destination v2:** complete rewrite on Bulk CDK. Typed columns (not JSON blobs), ReplacingMergeTree dedup, all five sync modes. Arrays/unions still coerce to strings.
- **Python floor raised** to >=3.10; 3.13 excluded.
- **Airbyte Agents:** separate agentic product (1,000 AOs/month free) — don't conflate with PyAirbyte. (Note: the hackathon's $1,750 Airbyte prize is for "Best Use of Airbyte's Agent Engine".)

---

## 6. Verdict

**Garnish.** PyAirbyte is real and works, but it earns its integration time only if you need structured external data flowing into ClickHouse at hackathon depth — and the Gmail OAuth setup alone (~45 min) competes directly with time spent making the core wedge demonstrably useful. Ship the core loop first; slot Airbyte in as a second-session add-on.

---

## 7. Links (accessed June 12, 2026)

- [PyAirbyte Docs — Getting Started](https://docs.airbyte.com/using-airbyte/pyairbyte/getting-started)
- [PyAirbyte API Reference](https://docs.airbyte.com/developers/pyairbyte)
- [PyAirbyte PyPI](https://pypi.org/project/airbyte/) — v0.47.1, June 7 2026
- [PyAirbyte GitHub Releases](https://github.com/airbytehq/PyAirbyte/releases)
- [Gmail Connector Docs](https://docs.airbyte.com/integrations/sources/gmail)
- [Google Calendar Connector Docs](https://docs.airbyte.com/integrations/sources/google-calendar)
- [ClickHouse Destination v2 Docs](https://docs.airbyte.com/integrations/destinations/clickhouse-v2)
- [Airbyte Cloud Limits](https://docs.airbyte.com/platform/cloud/managing-airbyte-cloud/understand-airbyte-cloud-limits)
- [Destinations Reference](https://docs.airbyte.com/developers/pyairbyte/reference/airbyte/destinations)
