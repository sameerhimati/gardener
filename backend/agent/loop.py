"""THE CORE AGENT LOOP.

(Originally reserved for Sameer to hand-write; under deadline pressure Claude wrote
it 2026-06-12 ~1:00 PM. The post-hackathon plan stands: rewrite this by hand as the
learning exercise — it's the single most teachable file in the repo.)

An agent = an LLM call in a while-loop with tools and memory. The `continue`
in the middle of run_turn IS the agent: the model asks to act, our code acts,
the model sees the result and decides what's next — until it has nothing left
to do but speak.
"""

import os

import anthropic

from backend.agent import prompts
from backend.agent.tools import TOOLS, execute_tool
from backend.core import events, store

# A confused model could ask for tools forever; cap the loop.
MAX_ITERATIONS = 15


def run_turn(session_id: str, user_message: str, system: str | None = None) -> str:
    # 1. The event trail starts here — the lint agent audits these later.
    events.log_event("user_msg", {"text": user_message}, session_id)
    store.append_message(session_id, "user", user_message)

    # 2. Durable history is plain text (user/assistant turns). Tool exchanges
    #    live only inside this turn's `messages` — Claude needs them to reason,
    #    but they'd bloat the stored transcript.
    messages = [
        {"role": m["role"], "content": m["content"]}
        for m in store.get_messages(session_id)
        if m.get("role") in ("user", "assistant") and m.get("content")
    ]

    # 3. System prompt: orchestrator by default; watch cycles pass WATCH_RUNNER.
    #    with_vault_context() appends the current memory vault — this is how the
    #    agent "remembers" you without any vector DB: the memory is just markdown.
    sys_prompt = prompts.with_vault_context(system or prompts.ORCHESTRATOR)

    client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from env
    model = os.environ.get("MODEL", "claude-sonnet-4-6")

    final_text = "(no response)"
    for _ in range(MAX_ITERATIONS):
        response = client.messages.create(
            model=model,
            max_tokens=2048,
            system=sys_prompt,
            tools=TOOLS,
            messages=messages,
        )

        if response.stop_reason == "tool_use":
            # The model wants to act. Execute every tool it asked for, then hand
            # ALL results back in ONE user message (tool_use_id must match) and
            # loop — the model sees what happened and decides the next move.
            # execute_tool logs the tool_call/tool_result events for the trail.
            results = [
                {
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": execute_tool(block.name, dict(block.input), session_id),
                }
                for block in response.content
                if block.type == "tool_use"
            ]
            messages.append({"role": "assistant", "content": response.content})
            messages.append({"role": "user", "content": results})
            continue  # ← this line is the whole secret

        # No tools requested: the model is done acting and is just talking.
        final_text = "\n".join(
            block.text for block in response.content if block.type == "text"
        ).strip() or "(no response)"
        break
    else:
        final_text = "I hit my action limit for one turn — say 'continue' and I'll pick it back up."

    # 4. Close the trail: persist + log the reply, mirror of step 1.
    store.append_message(session_id, "assistant", final_text)
    events.log_event("assistant_msg", {"text": final_text}, session_id)
    return final_text
