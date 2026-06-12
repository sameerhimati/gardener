"""Event log. ClickHouse when CLICKHOUSE_URL is set, else data/events.jsonl.

log_event NEVER raises — the product depends on logging being a no-risk call
inside the agent loop, the tools, and the lint worker.
"""

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from backend.core import ch

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"
JSONL_PATH = DATA_DIR / "events.jsonl"

# event kinds (reference):
# user_msg, assistant_msg, tool_call, tool_result, memory_write,
# watch_spawn, watch_cycle, watch_steer, lint_run, lint_finding, lint_apply, publish


def log_event(kind: str, payload: dict, session_id: str = "", user_id: str = "sameer") -> None:
    """Append one event. Never raises; prints a warning on failure."""
    try:
        now = datetime.now(timezone.utc)
        event = {
            "event_id": str(uuid.uuid4()),
            "user_id": user_id,
            "session_id": session_id,
            "ts": now.isoformat(),
            "kind": kind,
            "payload": payload,
        }
        if ch.configured():
            try:
                client = ch.get_client()
                client.insert(
                    "events",
                    [[event["event_id"], user_id, session_id, now.replace(tzinfo=None), kind, json.dumps(payload)]],
                    column_names=["event_id", "user_id", "session_id", "ts", "kind", "payload"],
                )
                return
            except Exception as e:  # ClickHouse down → fall through to JSONL
                print(f"[events] warning: ClickHouse insert failed ({e}); falling back to JSONL")
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        with JSONL_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(event, default=str) + "\n")
    except Exception as e:
        print(f"[events] warning: failed to log event {kind!r}: {e}")


def recent_events(limit: int = 200, kinds: list[str] | None = None) -> list[dict]:
    """Most recent events, newest first. Returns [] on any failure."""
    try:
        if ch.configured():
            try:
                return _recent_from_clickhouse(limit, kinds)
            except Exception as e:
                print(f"[events] warning: ClickHouse query failed ({e}); falling back to JSONL")
        return _recent_from_jsonl(limit, kinds)
    except Exception as e:
        print(f"[events] warning: recent_events failed: {e}")
        return []


def _recent_from_clickhouse(limit: int, kinds: list[str] | None) -> list[dict]:
    client = ch.get_client()
    where = ""
    parameters: dict = {"limit": limit}
    if kinds:
        where = "WHERE kind IN {kinds:Array(String)}"
        parameters["kinds"] = kinds
    result = client.query(
        f"""
        SELECT event_id, user_id, session_id, ts, kind, payload
        FROM events
        {where}
        ORDER BY ts DESC
        LIMIT {{limit:UInt32}}
        """,
        parameters=parameters,
    )
    events = []
    for event_id, user_id, session_id, ts, kind, payload in result.result_rows:
        try:
            parsed = json.loads(payload)
        except (TypeError, ValueError):
            parsed = payload
        events.append(
            {
                "event_id": event_id,
                "user_id": user_id,
                "session_id": session_id,
                "ts": ts.isoformat() if hasattr(ts, "isoformat") else str(ts),
                "kind": kind,
                "payload": parsed,
            }
        )
    return events


def _recent_from_jsonl(limit: int, kinds: list[str] | None) -> list[dict]:
    if not JSONL_PATH.exists():
        return []
    events = []
    with JSONL_PATH.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except ValueError:
                continue
            if kinds and event.get("kind") not in kinds:
                continue
            events.append(event)
    return list(reversed(events[-limit:]))  # newest first
