"""One-off: migrate stranded JSONL events into ClickHouse, then run the lint worker.

Needed because the event store switched from JSONL fallback to ClickHouse mid-day
when the tables were created — the seeded demo story was stranded in data/events.jsonl.
Idempotent enough for demo use (re-logging duplicates is harmless for lint).
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from backend.core import events  # noqa: E402

migrated = 0
jsonl = Path("data/events.jsonl")
if jsonl.exists():
    for line in jsonl.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        e = json.loads(line)
        if e.get("kind") == "lint_run":
            continue
        payload = e.get("payload")
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except ValueError:
                payload = {"text": payload}
        events.log_event(e["kind"], payload or {}, e.get("session_id", ""), e.get("user_id", "sameer"))
        migrated += 1
print(f"migrated {migrated} events")

evts = events.recent_events(300)
steers = [e for e in evts if e.get("kind") == "watch_steer"]
print(f"recent_events sees {len(evts)} events, {len(steers)} steer(s)")

from backend.worker import lint_worker  # noqa: E402

findings = lint_worker.run_lint()
for f in findings:
    print(f"FINDING [{f.get('rule')}] conf={f.get('confidence')} status={f.get('status')} — {f.get('summary')}")
print(f"done: {len(findings)} finding(s)")
