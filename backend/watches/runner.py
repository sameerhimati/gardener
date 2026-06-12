"""Watch cycle execution + asyncio scheduler + steering -> preference distillation.

Per docs/architecture.md:
- run_cycle(watch_id)      -> one agent turn on the watch's session, logged as watch_cycle
- distill_steering(...)    -> steering text -> durable preference bullets in the vault
- start_scheduler()        -> background asyncio task that runs due watches every 30s
"""

from __future__ import annotations

import asyncio
import json
import re
from datetime import datetime, timezone

SCHEDULER_TICK_SEC = 30
DEFAULT_CADENCE_SEC = 120

_scheduler_task: asyncio.Task | None = None


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _run_agent_turn(session_id: str, message: str, system: str) -> str:
    """Resolve the agent loop the same way app.py does: hand-written loop first,
    stub fallback until loop.py lands. Binds the watch owner into the ambient
    user context so prompts.with_vault_context injects THEIR vault (the spine
    loop stays untouched)."""
    from backend.agent import loop, loop_stub
    from backend.core import store

    token = store.set_current_user(store.session_user_id(session_id))
    try:
        try:
            return loop.run_turn(session_id, message, system=system)
        except NotImplementedError:
            return loop_stub.run_turn(session_id, message, system=system)
    finally:
        store.reset_current_user(token)


def run_cycle(watch_id: str) -> dict:
    """Run one check for a watch: one agent turn on the watch's own session."""
    from backend.agent import prompts
    from backend.core import events, store

    watch = store.get_watch(watch_id)
    act_mode = watch.get("act_mode", "off")
    cycle_prompt = (
        f"Task: {watch['task']}\n"
        f"act_mode: {act_mode}\n"
        "Run one check now and report. If — and only if — you find a GENUINE, "
        "confident match, act per act_mode (calendar = create a Google Calendar "
        "event for the match via GOOGLECALENDAR_CREATE_EVENT; discord = post the "
        "match and its link to Discord via DISCORDBOT_CREATE_MESSAGE; off = report "
        "only). Never act on a no-result cycle. If prior context might matter "
        "(was this corrected before?), call cited_read first."
    )

    reply = _run_agent_turn(watch["session_id"], cycle_prompt, prompts.WATCH_RUNNER)

    summary = (reply or "")[:300]
    events.log_event(
        "watch_cycle",
        {"watch_id": watch_id, "summary": summary},
        session_id=watch.get("session_id", ""),
    )
    store.update_watch(watch_id, last_run=_now().isoformat(), last_result=summary)
    return {"watch_id": watch_id, "reply": reply}


# ── steering → preference distillation ──────────────────────────────────────


def _parse_distilled(raw: str) -> list[dict]:
    """Parse the distiller's JSON output. Tolerates ``` fences and junk —
    returns [] on any failure (distillation is best-effort, never crashes)."""
    text = (raw or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\s*", "", text)
        text = re.sub(r"\s*```$", "", text).strip()
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return []
    if isinstance(data, dict):
        # tolerate {"preferences": [...]} style wrappers
        for value in data.values():
            if isinstance(value, list):
                data = value
                break
        else:
            data = [data]
    if not isinstance(data, list):
        return []
    return [item for item in data if isinstance(item, dict)]


def distill_steering(watch_id: str, message: str) -> None:
    """Distill a steering message into preference bullets in the watch owner's vault."""
    from backend.core import store

    watch = store.get_watch(watch_id)
    user_id = store.session_user_id(watch.get("session_id", ""))
    distill_text(message, source=f"watch:{watch_id}", user_id=user_id)


def distill_text(text: str, source: str, user_id: str = "sameer") -> list[dict]:
    """Distill any user text (steering, onboarding answers) into the vault.

    Each {topic, fact} becomes a provenance-suffixed bullet appended to
    vault preferences/<topic>.md (created with frontmatter if missing).
    Writes land in the given user's garden (default "sameer").
    Returns the list of {topic, fact} items written.
    """
    from backend.agent import prompts
    from backend.core import gliner, llm, vault

    # Fine-tuned GLiNER2 (Pioneer) handles housing steering deterministically —
    # no malformed JSON on memory writes. Returns None when inactive/unsure, so
    # we transparently fall back to the general-LLM distiller.
    items = gliner.extract(text) if gliner.available() else None
    if not items:
        raw = llm.complete(text, system=prompts.DISTILLER)
        items = _parse_distilled(raw)
    if not items:
        return []

    today = _now().strftime("%Y-%m-%d")
    written = []
    for item in items:
        topic = str(item.get("topic", "")).strip().lower().replace(" ", "-")
        fact = str(item.get("fact", "")).strip()
        if not topic or not fact:
            continue

        path = f"preferences/{topic}.md"
        bullet = f"- {fact} (src: {source} {today})"

        try:
            content = vault.read(path, user_id=user_id)
        except FileNotFoundError:
            content = f"---\ntopic: {topic}\nupdated: {today}\n---\n"

        if bullet in content:
            continue  # exact duplicate, nothing to add

        # bump the frontmatter `updated:` date, keep everything else
        content = re.sub(r"(?m)^updated:.*$", f"updated: {today}", content, count=1)
        content = content.rstrip("\n") + "\n" + bullet + "\n"
        vault.write(path, content, source=source, user_id=user_id)
        written.append({"topic": topic, "fact": fact})
    return written


# ── scheduler ────────────────────────────────────────────────────────────────


def _is_due(watch: dict) -> bool:
    last_run = watch.get("last_run")
    if not last_run:
        return True
    try:
        last = datetime.fromisoformat(str(last_run))
    except ValueError:
        return True
    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    try:
        cadence = int(watch.get("cadence_sec") or DEFAULT_CADENCE_SEC)
    except (TypeError, ValueError):
        cadence = DEFAULT_CADENCE_SEC
    return (_now() - last).total_seconds() >= cadence


async def _scheduler_loop() -> None:
    from backend.core import store

    while True:
        try:
            watches = store.list_watches(user_id=None) or []  # every user's watches
        except Exception as exc:  # one bad tick never kills the scheduler
            print(f"[scheduler] failed to list watches: {exc}")
            watches = []
        for watch in watches:
            try:
                if watch.get("status", "active") != "active":
                    continue
                if not _is_due(watch):
                    continue
                # run_cycle is sync (agent turn = blocking API calls);
                # run it in a thread so the event loop stays responsive.
                await asyncio.to_thread(run_cycle, watch["id"])
            except Exception as exc:
                print(f"[scheduler] cycle failed for watch {watch.get('id')}: {exc}")
        await asyncio.sleep(SCHEDULER_TICK_SEC)


def start_scheduler() -> None:
    """Spawn the background scheduler task. Idempotent; needs a running loop
    (call from FastAPI startup). Safe when no watches exist."""
    global _scheduler_task
    if _scheduler_task is not None and not _scheduler_task.done():
        return
    _scheduler_task = asyncio.get_running_loop().create_task(_scheduler_loop())
