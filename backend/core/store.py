"""Chat sessions + watches persistence. Plain JSON files under data/:

    data/sessions/<session_id>.json   {id, kind, title, created, messages: [...]}
    data/watches.json                 {watch_id: watch, ...}

Single-process demo — a module lock around read-modify-write is enough.
"""

import json
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"
SESSIONS_DIR = DATA_DIR / "sessions"
WATCHES_PATH = DATA_DIR / "watches.json"

_lock = threading.Lock()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _session_path(session_id: str) -> Path:
    return SESSIONS_DIR / f"{session_id}.json"


def _read_json(path: Path, default):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")


# ── sessions ─────────────────────────────────────────────────────────────────

def create_session(kind: str = "main", title: str = "") -> str:
    session_id = f"s_{uuid.uuid4().hex[:12]}"
    with _lock:
        _write_json(
            _session_path(session_id),
            {"id": session_id, "kind": kind, "title": title, "created": _now(), "messages": []},
        )
    return session_id


def get_messages(session_id: str) -> list[dict]:
    session = _read_json(_session_path(session_id), None)
    return session["messages"] if session else []


def append_message(session_id: str, role: str, content: str) -> None:
    with _lock:
        path = _session_path(session_id)
        session = _read_json(
            path,
            {"id": session_id, "kind": "main", "title": "", "created": _now(), "messages": []},
        )
        session["messages"].append({"role": role, "content": content, "ts": _now()})
        _write_json(path, session)


# ── watches ──────────────────────────────────────────────────────────────────

def create_watch(task: str, cadence_sec: int = 120) -> dict:
    session_id = create_session(kind="watch", title=task[:80])
    watch = {
        "id": f"w_{uuid.uuid4().hex[:12]}",
        "task": task,
        "cadence_sec": cadence_sec,
        "session_id": session_id,
        "status": "active",
        "created": _now(),
        "last_run": None,
        "last_result": "",
    }
    with _lock:
        watches = _read_json(WATCHES_PATH, {})
        watches[watch["id"]] = watch
        _write_json(WATCHES_PATH, watches)
    return watch


def list_watches() -> list[dict]:
    watches = _read_json(WATCHES_PATH, {})
    return sorted(watches.values(), key=lambda w: w.get("created", ""))


def get_watch(watch_id: str) -> dict:
    watches = _read_json(WATCHES_PATH, {})
    if watch_id not in watches:
        raise KeyError(f"no such watch: {watch_id}")
    return watches[watch_id]


def update_watch(watch_id: str, **fields) -> None:
    with _lock:
        watches = _read_json(WATCHES_PATH, {})
        if watch_id not in watches:
            raise KeyError(f"no such watch: {watch_id}")
        watches[watch_id].update(fields)
        _write_json(WATCHES_PATH, watches)
