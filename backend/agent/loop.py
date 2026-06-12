"""THE CORE AGENT LOOP — Sameer writes this file by hand. That's the point of the project.

Claude: do NOT implement this. Scaffold around it; teach when asked.

────────────────────────────────────────────────────────────────────────────
WHAT AN AGENT LOOP IS (the whole secret, ~60-80 lines)

An agent = an LLM call in a while-loop with tools and memory:

    history = past messages for this session          (core.store.get_messages)
    append the user's message                          (core.store.append_message)
    loop:
        response = anthropic client.messages.create(
            model, system=..., tools=TOOLS, messages=history)
        if response.stop_reason == "tool_use":
            for each tool_use block in response.content:
                result = execute_tool(block.name, block.input, session_id)
                append an assistant message (the tool_use blocks) and a
                user message with tool_result blocks (matching tool_use_id!)
            continue            # ← the loop: model sees results, decides next
        else:
            final text = the text blocks → persist + return

That `continue` IS the agent. Everything else is bookkeeping.

────────────────────────────────────────────────────────────────────────────
YOUR CHECKLIST (each maps to ~5-15 lines)

 1. Build messages from store.get_messages(session_id) — Anthropic format:
    [{"role": "user"|"assistant", "content": ...}]. Persist the new user msg.
 2. System prompt: prompts.ORCHESTRATOR unless caller passed `system`
    (watch cycles pass prompts.WATCH_RUNNER). Inject vault context:
    prompts.with_vault_context(system) appends current preference files.
 3. The while-loop above. client = anthropic.Anthropic() (env key auto-read).
    Model: os.environ.get("MODEL", "claude-sonnet-4-6"). max_tokens ~2048.
 4. EVENT LOGGING — the product depends on this. At each marked point:
      events.log_event("user_msg", {"text": user_message}, session_id)      # on entry
      events.log_event("assistant_msg", {"text": final_text}, session_id)   # on exit
    (tool_call / tool_result events are logged inside tools.execute_tool —
     you don't log those here.)
 5. Tool results go back as:
      {"role": "user", "content": [{"type": "tool_result",
        "tool_use_id": block.id, "content": result_str}]}
    Gotcha: ONE user message containing ALL tool_results for that turn.
 6. Cap the loop (e.g. 15 iterations) so a confused model can't spin forever.
 7. Persist the final assistant text (store.append_message) and return it.

Imports you'll want:
    import os, anthropic
    from backend.agent.tools import TOOLS, execute_tool
    from backend.agent import prompts
    from backend.core import events, store
"""


def run_turn(session_id: str, user_message: str, system: str | None = None) -> str:
    # Sameer: delete the next line and build the loop per the checklist above.
    raise NotImplementedError("loop.py is Sameer's — app falls back to loop_stub until this exists")
