"""Lint rule registry. Each rule: fn(events: list[dict], vault: dict[str, str]) -> list[Finding].

Later rules append (name, fn) tuples to RULES.
"""

RULES: list[tuple] = []

# ★ contradiction — Sameer's hand-written spine rule. The skeleton raises
# NotImplementedError; lint_worker skips it gracefully until it lands.
from backend.worker.rules.contradiction import find_contradictions  # noqa: E402

RULES.append(("contradiction", find_contradictions))

# staleness — optional garnish, low-confidence queue-only findings.
try:
    from backend.worker.rules.staleness import find_stale_beliefs

    RULES.append(("staleness", find_stale_beliefs))
except Exception:
    pass
