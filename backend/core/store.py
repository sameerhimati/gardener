"""Chat sessions + watches persistence. Plain JSON files under data/:

    data/sessions/<session_id>.json   {id, kind, title, created, messages: [...]}
    data/watches.json                 {watch_id: watch, ...}

Single-process demo — a module lock around read-modify-write is enough.
"""

import contextvars
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

DEFAULT_USER = "sameer"

# Ambient "who is this turn for" channel. Set by the HTTP route (and the watch
# runner) BEFORE calling into the agent loop; read by prompts.with_vault_context
# so the spine loop — which we must not modify — injects the CALLING user's vault
# instead of always Sameer's. Defaults to "sameer", so any path that doesn't set
# it (curl, cron lint, tests) keeps the single-user behavior.
_current_user: contextvars.ContextVar[str] = contextvars.ContextVar(
    "gardener_current_user", default=DEFAULT_USER
)


def set_current_user(user_id: str) -> contextvars.Token:
    """Bind the active user for this execution context. Returns a token the
    caller may pass to reset_current_user (optional in request-scoped threads)."""
    return _current_user.set(user_id or DEFAULT_USER)


def reset_current_user(token: contextvars.Token) -> None:
    try:
        _current_user.reset(token)
    except (ValueError, LookupError):
        pass


def current_user() -> str:
    """The user the current turn is acting for (default "sameer")."""
    return _current_user.get()


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

def create_session(kind: str = "main", title: str = "", user_id: str = DEFAULT_USER) -> str:
    session_id = f"s_{uuid.uuid4().hex[:12]}"
    with _lock:
        _write_json(
            _session_path(session_id),
            {
                "id": session_id,
                "kind": kind,
                "title": title,
                "user_id": user_id,
                "created": _now(),
                "messages": [],
            },
        )
    return session_id


def get_messages(session_id: str) -> list[dict]:
    session = _read_json(_session_path(session_id), None)
    return session["messages"] if session else []


def session_user_id(session_id: str) -> str:
    """The user_id that owns a session, default "sameer". This is the channel the
    spine agent loop uses to learn the caller's identity without changing its
    signature: tools resolve user_id from the session record."""
    session = _read_json(_session_path(session_id), None)
    if not session:
        return DEFAULT_USER
    return session.get("user_id") or DEFAULT_USER


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

def create_watch(
    task: str, cadence_sec: int = 3600, act_mode: str = "off", user_id: str = DEFAULT_USER
) -> dict:
    session_id = create_session(kind="watch", title=task[:80], user_id=user_id)
    # act_mode controls what a watch does on a genuine match:
    #   "off"  -> report only (default; no existing watch ever auto-acts)
    #   "draft"-> create a Gmail draft / tentative calendar event, never send
    #   "send" -> send a concise alert email
    if act_mode not in ("draft", "send", "off"):
        act_mode = "off"
    watch = {
        "id": f"w_{uuid.uuid4().hex[:12]}",
        "task": task,
        "cadence_sec": cadence_sec,
        "act_mode": act_mode,
        "session_id": session_id,
        "user_id": user_id,
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


def list_watches(user_id: str | None = DEFAULT_USER) -> list[dict]:
    """Watches owned by user_id (default "sameer" sees the seeded watches).

    Existing seeded watches predate the user_id field — treat a missing user_id
    as "sameer" so the demo's watches stay visible to the default garden. Pass
    user_id=None to list every watch (used by the scheduler, which must cycle
    everyone's watches)."""
    watches = _read_json(WATCHES_PATH, {})
    rows = sorted(watches.values(), key=lambda w: w.get("created", ""))
    if user_id is None:
        return rows
    return [w for w in rows if (w.get("user_id") or DEFAULT_USER) == user_id]


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


def delete_watch(watch_id: str) -> None:
    with _lock:
        watches = _read_json(WATCHES_PATH, {})
        if watch_id not in watches:
            raise KeyError(f"no such watch: {watch_id}")
        watches.pop(watch_id)
        _write_json(WATCHES_PATH, watches)
