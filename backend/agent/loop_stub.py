"""Echo loop with real plumbing — used until Sameer's loop.py lands.

Same signature as loop.run_turn. Persists messages, logs events, and (if the
message mentions a watch) actually spawns one so the UI flow is testable
end-to-end before the real agent exists.
"""

import json

from backend.agent.tools import execute_tool
from backend.core import events, store


def run_turn(session_id: str, user_message: str, system: str | None = None) -> str:
    events.log_event("user_msg", {"text": user_message}, session_id)
    store.append_message(session_id, "user", user_message)

    extra = ""
    if "watch" in user_message.lower():
        result = execute_tool("spawn_watch", {"task": user_message, "cadence_sec": 120}, session_id)
        try:
            watch = json.loads(result)
            extra = f" I spawned watch {watch['watch_id']} for that (its own chat: session {watch['session_id']})."
        except (ValueError, KeyError):
            extra = f" Tried to spawn a watch: {result[:200]}"

    reply = (
        f'You said: "{user_message}".{extra} '
        "[stub loop — Sameer's loop.py not written yet]"
    )

    store.append_message(session_id, "assistant", reply)
    events.log_event("assistant_msg", {"text": reply}, session_id)
    return reply
