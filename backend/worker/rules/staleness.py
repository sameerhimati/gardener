"""Staleness lint rule (garnish): pure-LLM check for beliefs that have likely
gone stale — bullets whose provenance date is old AND whose subject matter is
volatile (listings, prices, availability...). Findings are capped at
confidence 0.6 so they QUEUE for approval rather than auto-apply.
"""

import json
import re
from datetime import datetime, timezone

MAX_AGE_DAYS = 7
CONFIDENCE_CAP = 0.6

_SRC_DATE = re.compile(r"\(src:[^)]*?(\d{4}-\d{2}-\d{2})\)")

_SYSTEM = """You audit a markdown preference vault for STALE beliefs.
A belief is stale only if it is time-sensitive/volatile (e.g. listings, prices,
availability, schedules, "currently X") AND its provenance date is old.
Durable preferences (e.g. "wants 3+ bedrooms") are NOT stale regardless of age.

Return STRICT JSON only — a list (empty list is a good answer):
[{"vault_path": "<path>", "summary": "<why it is stale>",
  "corrected_content": "<full new file content with the stale bullet removed
or rewritten; keep all (src: ...) provenance suffixes intact on kept lines>",
  "confidence": 0.0-1.0}]"""


def _old_bullet_files(vault: dict[str, str], today: datetime) -> dict[str, str]:
    """Vault files that contain at least one bullet older than MAX_AGE_DAYS."""
    stale = {}
    for path, content in vault.items():
        for match in _SRC_DATE.finditer(content):
            try:
                src_date = datetime.strptime(match.group(1), "%Y-%m-%d")
            except ValueError:
                continue
            if (today - src_date.replace(tzinfo=timezone.utc)).days > MAX_AGE_DAYS:
                stale[path] = content
                break
    return stale


def _parse(raw: str) -> list[dict]:
    text = (raw or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\s*", "", text)
        text = re.sub(r"\s*```$", "", text).strip()
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return []
    if not isinstance(data, list):
        return []
    return [item for item in data if isinstance(item, dict)]


def find_stale_beliefs(events: list[dict], vault: dict[str, str]) -> list:
    from backend.core import diffs, llm
    from backend.worker.lint_worker import Finding

    candidates = _old_bullet_files(vault, datetime.now(timezone.utc))
    if not candidates:
        return []

    blocks = "\n\n".join(
        f"### {path}\n{content}" for path, content in candidates.items()
    )
    prompt = (
        f"Today is {datetime.now(timezone.utc):%Y-%m-%d}. "
        f"Beliefs older than {MAX_AGE_DAYS} days are candidates.\n\n"
        f"Vault files:\n\n{blocks}"
    )

    findings = []
    for item in _parse(llm.complete(prompt, system=_SYSTEM)):
        path = item.get("vault_path", "")
        corrected = item.get("corrected_content", "")
        if path not in vault or not corrected:
            continue
        diff = diffs.make_diff(path, vault[path], corrected)
        if not diff.strip():
            continue
        try:
            confidence = min(float(item.get("confidence", 0.5)), CONFIDENCE_CAP)
        except (TypeError, ValueError):
            confidence = 0.5
        findings.append(Finding(
            rule="staleness",
            vault_path=path,
            summary=str(item.get("summary", "stale belief")),
            diff=diff,
            confidence=confidence,
            severity="info",
        ))
    return findings
