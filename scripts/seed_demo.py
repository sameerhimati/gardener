"""Seed a demo-ready state for Gardener. Idempotent — safe to run repeatedly.

Seeds the exact setup the lint demo needs:
  1. vault/sameer/preferences/housing.md with a belief ("Any size or layout is fine")
  2. events: a user_msg asking for a Zillow watch + a watch_steer that
     CONTRADICTS the vault belief ("only 3+ bedrooms, 1500+ sqft minimum")
     → this is what the contradiction lint rule catches on camera
  3. one watch (via backend.core.store.create_watch) if none exists

Backend modules are lazily imported; if they aren't written yet (parallel
agent), we poll for up to SEED_IMPORT_TIMEOUT seconds (default 300), then fall
back to writing data/events.jsonl + data/watches.json directly per the
contract's formats (docs/architecture.md).

Run from the repo root: python scripts/seed_demo.py
"""

from __future__ import annotations

import json
import os
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

# Sameer's seeded demo persona is the DEFAULT garden: vault/sameer/. The
# header-less default user is "sameer", so the contradiction-lint replay (which
# reads vault.all_files() with no user_id) audits exactly this file.
VAULT_HOUSING = REPO_ROOT / "vault" / "sameer" / "preferences" / "housing.md"
DATA_DIR = REPO_ROOT / "data"
EVENTS_JSONL = DATA_DIR / "events.jsonl"
WATCHES_JSON = DATA_DIR / "watches.json"

# The seeded belief is intentionally LOCATION-NEUTRAL: the contradiction beat is
# about *size* ("any size is fine" vs "3+ bedrooms, 1500+ sqft"), which holds no
# matter where the user lives. Keeping the city/zip out of the seed means a fresh
# user's own zip (typed in onboarding basics) drives "houses near me" — the seed
# never fights the type-your-own-zip story. Do NOT reintroduce a hardcoded city
# here: it would both contradict the user's entered location and add noise the
# contradiction-lint demo doesn't need.
HOUSING_MD = """---
topic: housing
updated: 2026-06-12
---
- Looking to buy a house (src: chat 2026-06-12)
- Any size or layout is fine (src: chat 2026-06-12)
"""

WATCH_TASK = "Watch Zillow for new house listings near me"
USER_MSG = (
    "Can you watch Zillow for new house listings near me and let me know "
    "when something comes up?"
)
STEER_MSG = (
    "Actually — only show me 3+ bedrooms, 1500+ sqft minimum. Nothing smaller."
)

IMPORT_TIMEOUT = int(os.environ.get("SEED_IMPORT_TIMEOUT", "300"))


def import_backend(timeout_sec: int):
    """Poll for backend.core.{events,store} (a parallel agent may still be
    writing them). Returns (events, store) or (None, None) after timeout."""
    deadline = time.time() + timeout_sec
    last_err = None
    while True:
        try:
            from backend.core import events, store  # lazy import

            return events, store
        except Exception as exc:  # noqa: BLE001 — ImportError or partial module
            last_err = exc
        if time.time() >= deadline:
            print(f"[seed] backend modules unavailable after {timeout_sec}s "
                  f"({last_err}) — falling back to direct file writes")
            return None, None
        print(f"[seed] backend not importable yet ({last_err}); retrying in 10s...")
        time.sleep(10)


# ── fallback primitives (contract formats, docs/architecture.md) ─────────────


def fallback_log_event(kind: str, payload: dict, session_id: str = "") -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    event = {
        "event_id": uuid.uuid4().hex,
        "ts": datetime.now(timezone.utc).isoformat(),
        "kind": kind,
        "payload": payload,
        "session_id": session_id,
        "user_id": "sameer",
    }
    with EVENTS_JSONL.open("a") as fh:
        fh.write(json.dumps(event) + "\n")


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


# ── idempotency check ─────────────────────────────────────────────────────────


def events_already_seeded(events_mod) -> bool:
    """True if the contradicting steer event is already in the log."""
    rows: list[dict] = []
    if events_mod is not None:
        try:
            rows = events_mod.recent_events(limit=500, kinds=["watch_steer"])
        except Exception:
            rows = []
    if not rows:
        rows = [e for e in read_jsonl(EVENTS_JSONL) if e.get("kind") == "watch_steer"]
    for ev in rows:
        payload = ev.get("payload") or {}
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except json.JSONDecodeError:
                payload = {}
        if "3+ bedrooms" in str(payload.get("text", "")):
            return True
    return False


def main() -> int:
    seeded: list[str] = []
    events_mod, store_mod = import_backend(IMPORT_TIMEOUT)

    # 1. Vault belief the steer will contradict (deterministic content → idempotent)
    VAULT_HOUSING.parent.mkdir(parents=True, exist_ok=True)
    if VAULT_HOUSING.exists() and VAULT_HOUSING.read_text() == HOUSING_MD:
        print(f"[seed] vault/sameer/preferences/housing.md already seeded — skipping")
    else:
        VAULT_HOUSING.write_text(HOUSING_MD)
        seeded.append("vault/sameer/preferences/housing.md (belief: 'Any size or layout is fine')")

    # 2. Watch (before events, so the steer can reference its session)
    watch = None
    if store_mod is not None:
        try:
            existing = store_mod.list_watches()
        except Exception:
            existing = []
        if existing:
            watch = existing[0]
            print(f"[seed] watch already exists ({watch.get('id', '?')}) — skipping")
        else:
            watch = store_mod.create_watch(WATCH_TASK)
            seeded.append(f"watch {watch.get('id', '?')}: {WATCH_TASK}")
    else:
        watches = json.loads(WATCHES_JSON.read_text()) if WATCHES_JSON.exists() else []
        if watches:
            watch = watches[0]
            print(f"[seed] watch already exists ({watch.get('id', '?')}) — skipping")
        else:
            watch = {
                "id": f"w_{uuid.uuid4().hex[:8]}",
                "task": WATCH_TASK,
                "session_id": f"s_{uuid.uuid4().hex[:8]}",
                "status": "active",
                "cadence_sec": 120,
                "last_run": None,
                "last_result": None,
            }
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            WATCHES_JSON.write_text(json.dumps([watch], indent=2))
            seeded.append(f"watch {watch['id']} (fallback data/watches.json): {WATCH_TASK}")

    # 3. Events: the ask + the contradicting steer
    if events_already_seeded(events_mod):
        print("[seed] demo events already in the log — skipping")
    else:
        watch_session = (watch or {}).get("session_id", "")
        log = events_mod.log_event if events_mod is not None else fallback_log_event
        log("user_msg", {"text": USER_MSG}, session_id="")
        log("watch_steer", {"text": STEER_MSG, "watch_id": (watch or {}).get("id", "")},
            session_id=watch_session)
        seeded.append("events: user_msg (watch Zillow 77005) + watch_steer "
                      "(3+ bd / 1500+ sqft — contradicts 'Any size or layout is fine')")

    print()
    if seeded:
        print("[seed] seeded:")
        for item in seeded:
            print(f"  - {item}")
    else:
        print("[seed] nothing to do — demo state already in place")
    print("\n[seed] next: run the lint worker (POST /lint/run or "
          "`python -m backend.worker.lint_worker`) to catch the contradiction.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
