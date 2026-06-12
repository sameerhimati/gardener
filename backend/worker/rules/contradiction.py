"""THE CONTRADICTION LINT RULE — the gardener half of the spine.

(Originally reserved for Sameer; Claude wrote it 2026-06-12 ~1:00 PM under deadline.
Post-hackathon: rewrite by hand alongside loop.py.)

Given recent events (what the user actually said/steered) and the vault (what the
agent currently believes), find beliefs the events invalidate and produce the
corrected file as a unified diff. The lint worker handles storage and auto-apply.
"""

import json
import re

from backend.core import diffs, llm

# Only these event kinds carry user intent worth auditing beliefs against.
INTENT_KINDS = {"user_msg", "watch_steer", "memory_write"}

SYSTEM = """You are the Gardener's memory auditor. You receive (a) the assistant's \
memory vault (markdown files of beliefs about the user, one fact per bullet with a \
provenance suffix) and (b) a recent event log of what the user actually said and did.

Find beliefs that the events CONTRADICT or INVALIDATE — e.g. the vault says "any \
size is fine" but the user later said "only 3+ bedrooms". Ignore beliefs the events \
merely don't mention. An empty answer is a good answer.

Reply with STRICT JSON only — an array (possibly empty) of:
{"vault_path": "<path exactly as given>",
 "summary": "<one sentence: which belief is contradicted by what>",
 "corrected_content": "<the FULL corrected file content>",
 "confidence": <0.0-1.0, how certain the contradiction is real>}

Rules for corrected_content: keep the file's frontmatter and untouched bullets \
byte-identical; remove or rewrite only the contradicted bullets; every bullet keeps \
a "(src: ...)" provenance suffix — cite the contradicting event source on lines you \
change. No markdown fences, no commentary outside the JSON."""


def find_contradictions(events: list[dict], vault: dict[str, str]) -> list:
    from backend.worker.lint_worker import Finding  # lazy: avoids circular import

    # Newest last so the model reads the story in order; cap for prompt size.
    relevant = sorted(
        (e for e in events if e.get("kind") in INTENT_KINDS),
        key=lambda e: str(e.get("ts", "")),
    )[-50:]
    if not relevant or not vault:
        return []

    vault_section = "\n\n".join(
        f"### {path}\n{content}" for path, content in sorted(vault.items())
    )
    event_lines = "\n".join(
        f"- [{e.get('kind')}] {_event_text(e)}" for e in relevant
    )
    prompt = (
        f"## Memory vault\n\n{vault_section}\n\n"
        f"## Recent events (oldest first)\n\n{event_lines}\n\n"
        "Audit the vault against the events. JSON array only."
    )

    items = _parse_json_array(llm.complete(prompt, system=SYSTEM))

    findings = []
    for item in items:
        path = str(item.get("vault_path", "")).strip()
        corrected = item.get("corrected_content")
        if path not in vault or not isinstance(corrected, str):
            continue  # hallucinated path or malformed item — drop, don't crash
        diff = diffs.make_diff(path, vault[path], corrected)
        if not diff.strip():
            continue  # "correction" that changes nothing isn't a finding
        try:
            confidence = max(0.0, min(1.0, float(item.get("confidence", 0.5))))
        except (TypeError, ValueError):
            confidence = 0.5
        findings.append(
            Finding(
                rule="contradiction",
                vault_path=path,
                summary=str(item.get("summary", "contradicted belief")).strip(),
                diff=diff,
                confidence=confidence,
                severity="warn",
            )
        )
    return findings


def _event_text(event: dict) -> str:
    payload = event.get("payload") or {}
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except ValueError:
            return payload[:300]
    text = payload.get("text") or payload.get("summary") or json.dumps(payload)
    return str(text)[:300]


def _parse_json_array(raw: str) -> list[dict]:
    """Tolerate fenced/wrapped output; on any parse failure return [] — the
    lint worker must never crash because a model got chatty."""
    raw = raw.strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", raw, re.DOTALL)
    if fenced:
        raw = fenced.group(1).strip()
    start, end = raw.find("["), raw.rfind("]")
    if start == -1 or end <= start:
        return []
    try:
        data = json.loads(raw[start : end + 1])
    except ValueError:
        return []
    return [x for x in data if isinstance(x, dict)]
