"""Gardener FastAPI app — all HTTP routes per docs/architecture.md.

Run from repo root:  .venv/bin/uvicorn backend.app:app --reload --port 8000
"""

import importlib
import json
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")  # before any module reads env

from fastapi import Depends, FastAPI, Header, HTTPException  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from pydantic import BaseModel  # noqa: E402

from backend.agent import loop_stub, prompts  # noqa: E402
from backend.core import ch, events, store, vault  # noqa: E402

FINDINGS_JSONL = ROOT / "data" / "findings.jsonl"


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Langfuse: globally instrument the Anthropic SDK so every LLM call (agent
    # loop, core.llm) is traced. No-ops without LANGFUSE_* keys. Additive.
    try:
        from backend.core import tracing

        tracing.init()
    except Exception as e:
        print(f"[app] warning: Langfuse init failed ({e}) — tracing disabled")
    try:
        if ch.configured():
            ch.init_schema()
            print("[app] ClickHouse schema initialized")
    except Exception as e:
        print(f"[app] warning: ClickHouse init failed ({e}) — JSONL fallback in effect")
    try:
        from backend.watches import runner

        runner.start_scheduler()
        print("[app] watch scheduler started")
    except (ImportError, AttributeError, NotImplementedError) as e:
        print(f"[app] watch scheduler not started yet: {e}")
    except Exception as e:
        print(f"[app] warning: watch scheduler failed: {e}")
    yield


app = FastAPI(title="Gardener", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_origin_regex=r"https://.*\.onrender\.com",  # deployed UI is on a different subdomain than the API
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── multi-tenant identity ─────────────────────────────────────────────────────
# Each browser mints an opaque uuid (web/lib/uid.ts), stored in localStorage and
# sent as X-User-Id on every request. We resolve it here, DEFAULTING TO "sameer"
# when absent — so the seeded demo garden (vault/sameer/, the seeded watches, the
# contradiction-lint replay) and any header-less caller (curl, the cron lint
# worker) are exactly the "sameer" garden and keep working unchanged.

import re as _re  # noqa: E402

_SAFE_UID = _re.compile(r"[^a-zA-Z0-9_-]+")


def current_user(x_user_id: str | None = Header(default=None)) -> str:
    """Resolve the calling user from the X-User-Id header, default "sameer".
    Sanitized to the same charset the vault accepts (no path-escape risk)."""
    if not x_user_id or not x_user_id.strip():
        return "sameer"
    safe = _SAFE_UID.sub("", x_user_id.strip())
    return safe or "sameer"


class ChatIn(BaseModel):
    session_id: str | None = None
    message: str
    image: str | None = None  # optional data: URI for a dropped/pasted image


class WatchIn(BaseModel):
    task: str
    cadence_sec: int = 120


class MessageIn(BaseModel):
    message: str


class WatchPatch(BaseModel):
    task: str | None = None
    cadence_sec: int | None = None


def _run_turn(
    session_id: str,
    message: str,
    system: str | None = None,
    image: str | None = None,
    user_id: str | None = None,
) -> str:
    """Sameer's loop if it exists, else the stub. Reimported fresh each request
    so his edits land immediately under uvicorn --reload.

    Binds the calling user into the ambient context (store.set_current_user)
    BEFORE entering the loop, so prompts.with_vault_context injects THIS user's
    vault — without touching the hand-written spine loop. Resolves user_id from
    the session record when not passed (e.g. watch cycles)."""
    uid = user_id or store.session_user_id(session_id)
    token = store.set_current_user(uid)
    import backend.agent.loop as loop

    loop = importlib.reload(loop)
    try:
        try:
            return loop.run_turn(session_id, message, system, image=image)
        except NotImplementedError:
            return loop_stub.run_turn(session_id, message, system)
    finally:
        store.reset_current_user(token)


# ── chat ─────────────────────────────────────────────────────────────────────

@app.post("/chat")
def chat(body: ChatIn, user_id: str = Depends(current_user)):
    # A new session is stamped with the caller's user_id; every tool call in the
    # turn resolves that user_id from the session (see tools.execute_tool), so
    # the spine loop signature is untouched.
    session_id = body.session_id or store.create_session(kind="main", user_id=user_id)
    reply = _run_turn(session_id, body.message, image=body.image, user_id=user_id)
    return {"session_id": session_id, "reply": reply}


@app.get("/sessions/{session_id}/messages")
def session_messages(session_id: str):
    return store.get_messages(session_id)


# ── watches ──────────────────────────────────────────────────────────────────

@app.get("/watches")
def watches(user_id: str = Depends(current_user)):
    return store.list_watches(user_id=user_id)


@app.post("/watches")
def create_watch(body: WatchIn, user_id: str = Depends(current_user)):
    watch = store.create_watch(body.task, body.cadence_sec, user_id=user_id)
    events.log_event(
        "watch_spawn",
        {"watch_id": watch["id"], "task": body.task, "cadence_sec": body.cadence_sec, "manual": True},
        watch["session_id"],
        user_id=user_id,
    )
    return watch


@app.post("/watches/{watch_id}/run")
def run_watch(watch_id: str):
    _get_watch_or_404(watch_id)
    try:
        from backend.watches import runner
    except ImportError as e:
        raise HTTPException(status_code=503, detail=f"watches.runner not available yet: {e}")
    try:
        return runner.run_cycle(watch_id)
    except NotImplementedError as e:
        raise HTTPException(status_code=503, detail=f"run_cycle not implemented yet: {e}")


@app.post("/watches/{watch_id}/message")
def steer_watch(watch_id: str, body: MessageIn):
    watch = _get_watch_or_404(watch_id)
    wuid = watch.get("user_id") or "sameer"
    events.log_event(
        "watch_steer", {"watch_id": watch_id, "text": body.message}, watch["session_id"], user_id=wuid
    )

    # distill steering into the preference vault (module owned by another agent)
    try:
        from backend.watches import runner

        runner.distill_steering(watch_id, body.message)
    except (ImportError, AttributeError, NotImplementedError) as e:
        print(f"[app] distiller not available yet, skipping: {e}")
    except Exception as e:
        print(f"[app] warning: distill_steering failed: {e}")

    system = prompts.WATCH_RUNNER + f"\n\n## Your watch task\n{watch['task']}"
    # note: run_turn persists the user message itself — no separate append here,
    # or every steering message would appear twice in the watch chat.
    reply = _run_turn(watch["session_id"], body.message, system)
    return {"reply": reply}


@app.post("/watches/{watch_id}/pause")
def pause_watch(watch_id: str):
    watch = _get_watch_or_404(watch_id)
    store.update_watch(watch_id, status="paused")
    events.log_event("watch_pause", {"watch_id": watch_id}, watch["session_id"])
    return store.get_watch(watch_id)


@app.post("/watches/{watch_id}/resume")
def resume_watch(watch_id: str):
    watch = _get_watch_or_404(watch_id)
    store.update_watch(watch_id, status="active")
    events.log_event("watch_resume", {"watch_id": watch_id}, watch["session_id"])
    return store.get_watch(watch_id)


@app.patch("/watches/{watch_id}")
def edit_watch(watch_id: str, body: WatchPatch):
    watch = _get_watch_or_404(watch_id)
    fields = {k: v for k, v in body.model_dump().items() if v is not None}
    if fields:
        store.update_watch(watch_id, **fields)
    events.log_event("watch_edit", {"watch_id": watch_id, **fields}, watch["session_id"])
    return store.get_watch(watch_id)


@app.delete("/watches/{watch_id}")
def delete_watch(watch_id: str):
    watch = _get_watch_or_404(watch_id)
    store.delete_watch(watch_id)
    events.log_event("watch_delete", {"watch_id": watch_id}, watch["session_id"])
    return {"ok": True}


def _get_watch_or_404(watch_id: str) -> dict:
    try:
        return store.get_watch(watch_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"no such watch: {watch_id}")


@app.get("/watches/{watch_id}/events")
def watch_events(watch_id: str, limit: int = 40):
    """The watch's web activity — tool calls/results + cycle summaries — so the
    UI can show what the worker actually did. Newest first."""
    watch = _get_watch_or_404(watch_id)
    sid = watch.get("session_id", "")
    rows = events.recent_events(limit=400, kinds=["tool_call", "tool_result", "watch_cycle"])
    return [e for e in rows if e.get("session_id") == sid][:limit]


# ── connectors (integration status for the Connections panel) ──────────────

@app.get("/connectors")
def connectors():
    """Status of each integration connector (Google Calendar, Discord).

    Lazy + graceful: if Composio isn't configured, every connector reads
    connected:false with its CLI link command — the panel still renders.
    """
    try:
        from backend.integrations import composio_client

        return composio_client.connectors_status()
    except Exception as e:  # noqa: BLE001
        print(f"[app] warning: connectors_status failed: {e}")
        # Hard fallback so the UI always has something to show.
        return [
            {
                "key": "googlecalendar",
                "label": "Google Calendar",
                "connected": False,
                "instructions": "composio connected-accounts link googlecalendar",
            },
            {
                "key": "discordbot",
                "label": "Discord",
                "connected": False,
                "instructions": "composio connected-accounts link discordbot",
            },
        ]


# ── vault ────────────────────────────────────────────────────────────────────

@app.get("/vault")
def vault_index(user_id: str = Depends(current_user)):
    return vault.list_files(user_id=user_id)


@app.get("/vault/file")
def vault_file(path: str, user_id: str = Depends(current_user)):
    try:
        return {"path": path, "content": vault.read(path, user_id=user_id)}
    except (FileNotFoundError, ValueError):
        raise HTTPException(status_code=404, detail=f"no such vault file: {path}")


class VaultFileIn(BaseModel):
    path: str
    content: str


@app.put("/vault/file")
def vault_file_write(body: VaultFileIn, user_id: str = Depends(current_user)):
    """Persist an edited vault note. vault.write logs a memory_write event so the
    user's hand-edit shows up in the event log just like the agent's writes."""
    try:
        vault.write(body.path, body.content, source="ui-edit", user_id=user_id)
        return {"path": body.path, "content": vault.read(body.path, user_id=user_id)}
    except ValueError:
        # _full_path refuses paths that escape the vault root
        raise HTTPException(status_code=400, detail=f"bad vault path: {body.path}")


# ── lint findings ────────────────────────────────────────────────────────────

def _lint_worker():
    """Lazy import — another agent is writing backend/worker/lint_worker.py."""
    from backend.worker import lint_worker

    return lint_worker


@app.get("/findings")
def findings():
    try:
        lw = _lint_worker()
    except ImportError:
        return _findings_from_jsonl()
    for name in ("list_findings", "get_findings", "load_findings"):
        fn = getattr(lw, name, None)
        if callable(fn):
            try:
                return fn()
            except NotImplementedError:
                return []
            except Exception as e:
                print(f"[app] warning: lint_worker.{name} failed ({e}); reading JSONL")
                break
    return _findings_from_jsonl()


def _findings_from_jsonl():
    if not FINDINGS_JSONL.exists():
        return []
    by_id = {}
    for i, line in enumerate(FINDINGS_JSONL.read_text(encoding="utf-8").splitlines()):
        line = line.strip()
        if not line:
            continue
        try:
            finding = json.loads(line)
        except ValueError:
            continue
        by_id[finding.get("id", i)] = finding  # last write wins
    return list(by_id.values())


@app.post("/lint/run")
def lint_run():
    try:
        lw = _lint_worker()
    except ImportError as e:
        raise HTTPException(status_code=503, detail=f"lint worker not available yet: {e}")
    try:
        return lw.run_lint()
    except NotImplementedError as e:
        raise HTTPException(status_code=503, detail=f"lint worker not implemented yet: {e}")


@app.post("/findings/{finding_id}/apply")
def apply_finding(finding_id: str):
    return _resolve_finding(finding_id, "apply")


@app.post("/findings/{finding_id}/reject")
def reject_finding(finding_id: str):
    return _resolve_finding(finding_id, "reject")


def _resolve_finding(finding_id: str, action: str):
    try:
        lw = _lint_worker()
    except ImportError as e:
        raise HTTPException(status_code=503, detail=f"lint worker not available yet: {e}")
    for name in (f"{action}_finding", f"{action}", f"resolve_finding"):
        fn = getattr(lw, name, None)
        if callable(fn):
            try:
                return fn(finding_id) if name != "resolve_finding" else fn(finding_id, action)
            except NotImplementedError as e:
                raise HTTPException(status_code=503, detail=str(e))
            except KeyError:
                raise HTTPException(status_code=404, detail=f"no such finding: {finding_id}")
    raise HTTPException(status_code=503, detail=f"lint worker has no {action}_finding yet")


# ── onboarding (interactive: the interview IS the agent) ────────────────────

class OnboardingIn(BaseModel):
    session_id: str | None = None
    message: str
    question: str = ""  # the interview question currently on screen


@app.post("/onboarding/turn")
def onboarding_turn(body: OnboardingIn, user_id: str = Depends(current_user)):
    """One interactive onboarding exchange: the real agent replies (it can answer
    questions back), and the answer is distilled into the vault in the same call."""
    session_id = body.session_id or store.create_session(
        kind="onboarding", title="Onboarding", user_id=user_id
    )
    system = prompts.ONBOARDING
    if body.question:
        system += f'\n\nThe interview question on screen: "{body.question}"'
    reply = _run_turn(session_id, body.message, system, user_id=user_id)

    planted = []
    try:
        from backend.watches import runner

        planted = runner.distill_text(body.message, source="onboarding", user_id=user_id)
    except Exception as e:
        print(f"[app] warning: onboarding distill failed: {e}")
    return {"session_id": session_id, "reply": reply, "written": planted}


# ── distill (onboarding + any free text → preference vault) ─────────────────

class DistillIn(BaseModel):
    text: str
    source: str = "onboarding"


@app.post("/distill")
def distill(body: DistillIn, user_id: str = Depends(current_user)):
    events.log_event("user_msg", {"text": body.text, "source": body.source}, user_id=user_id)
    try:
        from backend.watches import runner

        return {"written": runner.distill_text(body.text, body.source, user_id=user_id)}
    except Exception as e:
        print(f"[app] warning: distill failed: {e}")
        return {"written": [], "error": str(e)}


# ── events ───────────────────────────────────────────────────────────────────

@app.get("/events/recent")
def events_recent(limit: int = 50):
    return events.recent_events(limit=limit)


# ── demo fixture (docs/watch-layer.md: the can't-fail on-camera watch target) ─

DEMO_LISTINGS = ROOT / "data" / "demo_listings.json"

_DEMO_SEED = [
    {"mls": "10298344", "address": "2811 Robinhood St, Houston TX 77005", "price": 749000, "beds": 2, "sqft": 1320},
    {"mls": "10298757", "address": "3415 Plumb St, Houston TX 77005", "price": 815000, "beds": 2, "sqft": 1410},
]

_DEMO_NEW = {"mls": "10299912", "address": "4106 Coleridge St, Houston TX 77005", "price": 1185000, "beds": 4, "sqft": 2350}


@app.get("/demo/listings")
def demo_listings():
    if not DEMO_LISTINGS.exists():
        DEMO_LISTINGS.parent.mkdir(parents=True, exist_ok=True)
        DEMO_LISTINGS.write_text(json.dumps(_DEMO_SEED, indent=2))
    return json.loads(DEMO_LISTINGS.read_text())


@app.post("/demo/listings/add")
def demo_listings_add():
    listings = demo_listings()
    if not any(l["mls"] == _DEMO_NEW["mls"] for l in listings):
        listings.append(_DEMO_NEW)
        DEMO_LISTINGS.write_text(json.dumps(listings, indent=2))
    return {"count": len(listings), "added": _DEMO_NEW}
