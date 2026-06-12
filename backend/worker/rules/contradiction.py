"""THE CONTRADICTION LINT RULE — Sameer writes this file by hand (the Gardener spine).

Claude: do NOT implement this. The worker plumbing (lint_worker.py) calls it and
handles NotImplementedError gracefully until it exists.

────────────────────────────────────────────────────────────────────────────
WHAT THIS RULE DOES

Given (a) recent events — what the user actually said/did/steered — and
(b) the vault — what the agent currently believes — find beliefs the events
contradict, and produce a corrected version of the file as a unified diff.

Canonical demo case: vault says "Wants any house in 77005"; a watch_steer
event says "only 3+ bedrooms, 1500+ sqft" → the older, broader belief is
stale/contradicted → diff replaces it, with provenance pointing at the event.

────────────────────────────────────────────────────────────────────────────
THE SHAPE (~50-70 lines)

 1. Filter events to the kinds that carry user intent:
    user_msg, watch_steer, memory_write. Keep the last ~50, newest last.
 2. Build ONE prompt containing: the vault files (path + content) and the
    event excerpts, asking the model to return STRICT JSON:
       [{"vault_path": ..., "summary": ...,
         "corrected_content": <full new file content>,
         "confidence": 0.0-1.0}]
    Tell it: only report REAL contradictions (an event that invalidates a
    written belief) — an empty list is a good answer. Keep provenance
    suffixes "(src: ...)" intact, update them on changed lines.
 3. Call core.llm.complete(prompt, system=...) — routes to Pioneer if keyed,
    else Anthropic. Parse the JSON (strip ```json fences; on parse failure
    return [] — never crash the worker).
 4. For each item, build the Finding:
       diff = diffs.make_diff(vault_path, vault[vault_path], corrected_content)
       Finding(rule="contradiction", vault_path=..., summary=...,
               diff=diff, confidence=..., severity="warn")
    Skip items whose vault_path isn't in the vault, or whose diff is empty.
 5. Return the list. (lint_worker handles storage, auto-apply >= 0.8,
    and the lint_finding/lint_apply events — not your job here.)

Imports you'll want:
    import json
    from backend.core import llm, diffs
    from backend.worker.lint_worker import Finding
"""


def find_contradictions(events: list[dict], vault: dict[str, str]) -> list:
    # Sameer: delete the next line and build the rule per the shape above.
    raise NotImplementedError("contradiction.py is Sameer's — lint worker skips this rule until it exists")
