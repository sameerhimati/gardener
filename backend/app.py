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

from fastapi import FastAPI, HTTPException  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from pydantic import BaseModel  # noqa: E402

from backend.agent import loop_stub, prompts  # noqa: E402
from backend.core import ch, events, store, vault  # noqa: E402

FINDINGS_JSONL = ROOT / "data" / "findings.jsonl"


@asynccontextmanager
async def lifespan(app: FastAPI):
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


class ChatIn(BaseModel):
    session_id: str | None = None
    message: str


class WatchIn(BaseModel):
    task: str
    cadence_sec: int = 120


class MessageIn(BaseModel):
    message: str


class WatchPatch(BaseModel):
    task: str | None = None
    cadence_sec: int | None = None


def _run_turn(session_id: str, message: str, system: str | None = None) -> str:
    """Sameer's loop if it exists, else the stub. Reimported fresh each request
    so his edits land immediately under uvicorn --reload."""
    import backend.agent.loop as loop

    loop = importlib.reload(loop)
    try:
        return loop.run_turn(session_id, message, system)
    except NotImplementedError:
        return loop_stub.run_turn(session_id, message, system)


# ── chat ─────────────────────────────────────────────────────────────────────

@app.post("/chat")
def chat(body: ChatIn):
    session_id = body.session_id or store.create_session(kind="main")
    reply = _run_turn(session_id, body.message)
    return {"session_id": session_id, "reply": reply}


@app.get("/sessions/{session_id}/messages")
def session_messages(session_id: str):
    return store.get_messages(session_id)


# ── watches ──────────────────────────────────────────────────────────────────

@app.get("/watches")
def watches():
    return store.list_watches()


@app.post("/watches")
def create_watch(body: WatchIn):
    watch = store.create_watch(body.task, body.cadence_sec)
    events.log_event(
        "watch_spawn",
        {"watch_id": watch["id"], "task": body.task, "cadence_sec": body.cadence_sec, "manual": True},
        watch["session_id"],
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
    events.log_event("watch_steer", {"watch_id": watch_id, "text": body.message}, watch["session_id"])

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


# ── vault ────────────────────────────────────────────────────────────────────

@app.get("/vault")
def vault_index():
    return vault.list_files()


@app.get("/vault/file")
def vault_file(path: str):
    try:
        return {"path": path, "content": vault.read(path)}
    except (FileNotFoundError, ValueError):
        raise HTTPException(status_code=404, detail=f"no such vault file: {path}")


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
def onboarding_turn(body: OnboardingIn):
    """One interactive onboarding exchange: the real agent replies (it can answer
    questions back), and the answer is distilled into the vault in the same call."""
    session_id = body.session_id or store.create_session(kind="onboarding", title="Onboarding")
    system = prompts.ONBOARDING
    if body.question:
        system += f'\n\nThe interview question on screen: "{body.question}"'
    reply = _run_turn(session_id, body.message, system)

    planted = []
    try:
        from backend.watches import runner

        planted = runner.distill_text(body.message, source="onboarding")
    except Exception as e:
        print(f"[app] warning: onboarding distill failed: {e}")
    return {"session_id": session_id, "reply": reply, "written": planted}


# ── distill (onboarding + any free text → preference vault) ─────────────────

class DistillIn(BaseModel):
    text: str
    source: str = "onboarding"


@app.post("/distill")
def distill(body: DistillIn):
    events.log_event("user_msg", {"text": body.text, "source": body.source})
    try:
        from backend.watches import runner

        return {"written": runner.distill_text(body.text, body.source)}
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
