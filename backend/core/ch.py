"""ClickHouse client factory + schema init.

Lazy and optional: only connects when CLICKHOUSE_URL is set. Everything else
in the codebase falls back to JSONL files under data/ when this returns None.
"""

import os
from urllib.parse import urlparse

_client = None

EVENTS_DDL = """
CREATE TABLE IF NOT EXISTS events
(
    event_id   String,
    user_id    String,
    session_id String,
    ts         DateTime64(3),
    kind       LowCardinality(String),
    payload    String
)
ENGINE = MergeTree
ORDER BY (user_id, ts, event_id)
"""

FINDINGS_DDL = """
CREATE TABLE IF NOT EXISTS lint_findings
(
    id          String,
    rule        LowCardinality(String),
    vault_path  String,
    summary     String,
    diff        String,
    confidence  Float64,
    severity    LowCardinality(String),
    status      LowCardinality(String) DEFAULT 'open',
    ts          DateTime64(3),
    resolved_at DateTime64(3) DEFAULT now64()
)
ENGINE = ReplacingMergeTree(resolved_at)
ORDER BY (id)
"""


def configured() -> bool:
    return bool(os.environ.get("CLICKHOUSE_URL"))


def get_client():
    """Return a cached clickhouse-connect client, or None if not configured."""
    global _client
    if not configured():
        return None
    if _client is None:
        import clickhouse_connect

        raw = os.environ["CLICKHOUSE_URL"]
        parsed = urlparse(raw if "://" in raw else f"https://{raw}")
        _client = clickhouse_connect.get_client(
            host=parsed.hostname,
            port=parsed.port or 8443,
            username=os.environ.get("CLICKHOUSE_USER", "default"),
            password=os.environ.get("CLICKHOUSE_PASSWORD", ""),
            secure=True,
        )
    return _client


def init_schema() -> bool:
    """Create the events + lint_findings tables. Returns False if not configured."""
    client = get_client()
    if client is None:
        return False
    client.command(EVENTS_DDL)
    client.command(FINDINGS_DDL)
    return True
