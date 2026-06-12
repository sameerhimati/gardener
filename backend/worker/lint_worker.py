"""Lint worker plumbing: load context -> run rules -> store findings -> auto-apply.

Per docs/architecture.md. The rules themselves live in backend/worker/rules/
(contradiction.py is Sameer's, hand-written). This module never crashes on a
missing or broken rule — it skips and reports.

Storage: ClickHouse `lint_findings` (via core.ch) when CLICKHOUSE_URL is set,
else data/findings.jsonl (append-only; status updates append a new row and
list_findings() dedupes by id keeping the latest).

Render cron entrypoint: `python -m backend.worker.lint_worker`
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel, Field

REPO_ROOT = Path(__file__).resolve().parents[2]
FINDINGS_PATH = REPO_ROOT / "data" / "findings.jsonl"


def _new_id() -> str:
    return f"f_{uuid.uuid4().hex[:8]}"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class Finding(BaseModel):
    id: str = Field(default_factory=_new_id)
    rule: str
    vault_path: str
    summary: str
    diff: str
    confidence: float
    severity: str = "warn"
    status: str = "open"  # open | auto_applied | approved | rejected
    ts: str = Field(default_factory=_now_iso)


# ── storage ──────────────────────────────────────────────────────────────────


def _use_clickhouse() -> bool:
    return bool(os.environ.get("CLICKHOUSE_URL"))


def _ch_save(row: dict) -> None:
    from backend.core import ch

    # Prefer a helper if core.ch exposes one; else generic client insert.
    for name in ("save_finding", "insert_finding"):
        fn = getattr(ch, name, None)
        if callable(fn):
            fn(row)
            return
    client_fn = getattr(ch, "get_client", None)
    client = client_fn() if callable(client_fn) else getattr(ch, "client", None)
    if client is None:
        raise RuntimeError("core.ch exposes no save_finding/insert_finding/get_client")
    cols = ["id", "ts", "rule", "vault_path", "summary", "diff",
            "confidence", "severity", "status"]
    client.insert("lint_findings", [[row[c] for c in cols]], column_names=cols)


def _ch_list() -> list[dict]:
    from backend.core import ch

    fn = getattr(ch, "list_findings", None)
    if callable(fn):
        return fn()
    client_fn = getattr(ch, "get_client", None)
    client = client_fn() if callable(client_fn) else getattr(ch, "client", None)
    if client is None:
        raise RuntimeError("core.ch exposes no list_findings/get_client")
    result = client.query("SELECT * FROM lint_findings FINAL ORDER BY ts DESC")
    return [dict(zip(result.column_names, r)) for r in result.result_rows]


def _jsonl_rows() -> list[dict]:
    if not FINDINGS_PATH.exists():
        return []
    rows = []
    with open(FINDINGS_PATH) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def save_finding(finding: "Finding | dict") -> None:
    row = finding.model_dump() if isinstance(finding, Finding) else dict(finding)
    if _use_clickhouse():
        try:
            _ch_save(row)
            return
        except Exception as exc:
            print(f"[lint] ClickHouse save failed ({exc}); falling back to JSONL")
    FINDINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(FINDINGS_PATH, "a") as f:
        f.write(json.dumps(row) + "\n")


def list_findings() -> list[dict]:
    """All findings, newest first, deduped by id keeping the latest status."""
    if _use_clickhouse():
        try:
            rows = _ch_list()
        except Exception as exc:
            print(f"[lint] ClickHouse list failed ({exc}); falling back to JSONL")
            rows = _jsonl_rows()
    else:
        rows = _jsonl_rows()
    latest: dict[str, dict] = {}
    for row in rows:  # file order = write order; later rows win
        if row.get("id"):
            latest[row["id"]] = row
    return sorted(latest.values(), key=lambda r: str(r.get("ts", "")), reverse=True)


def get_finding(finding_id: str) -> dict | None:
    for row in list_findings():
        if row.get("id") == finding_id:
            return row
    return None


def update_finding_status(finding_id: str, status: str) -> dict | None:
    row = get_finding(finding_id)
    if row is None:
        return None
    row["status"] = status
    save_finding(row)
    return row


# ── lint run ─────────────────────────────────────────────────────────────────


def run_lint(auto_apply_threshold: float = 0.8) -> list[dict]:
    """Gather context, run every rule, store findings, auto-apply confident ones."""
    from backend.core import diffs, events, vault
    # imported lazily: rules import Finding from this module (avoid circularity)
    from backend.worker.rules import RULES

    events.log_event("lint_run", {"rules": [name for name, _ in RULES]})

    recent = events.recent_events(200)
    files = vault.all_files()

    findings: list[Finding] = []
    ran, skipped = 0, []
    for name, rule_fn in RULES:
        try:
            produced = rule_fn(recent, files) or []
            ran += 1
        except NotImplementedError:
            skipped.append(name)
            print(f"[lint] rule '{name}' not implemented yet — skipped")
            continue
        except Exception as exc:
            print(f"[lint] rule '{name}' failed: {exc}")
            continue
        for item in produced:
            try:
                findings.append(item if isinstance(item, Finding) else Finding(**dict(item)))
            except Exception as exc:
                print(f"[lint] rule '{name}' produced a bad finding: {exc}")

    results: list[dict] = []
    for finding in findings:
        events.log_event("lint_finding", {
            "id": finding.id,
            "rule": finding.rule,
            "vault_path": finding.vault_path,
            "summary": finding.summary,
            "confidence": finding.confidence,
        })
        save_finding(finding)
        if finding.confidence >= auto_apply_threshold:
            try:
                diffs.apply_diff(finding.vault_path, finding.diff)
                finding.status = "auto_applied"
                events.log_event("lint_apply", {
                    "id": finding.id, "vault_path": finding.vault_path, "auto": True,
                })
                save_finding(finding)
            except Exception as exc:
                print(f"[lint] auto-apply failed for {finding.id}: {exc}")
        results.append(finding.model_dump())

    print(f"[lint] {ran} rule(s) ran, {len(skipped)} skipped "
          f"({', '.join(skipped) or 'none'}), {len(results)} finding(s)")
    return results


def apply_finding(finding_id: str) -> dict | None:
    """One-click approval from the UI: apply the diff, mark approved."""
    from backend.core import diffs, events

    row = get_finding(finding_id)
    if row is None:
        return None
    diffs.apply_diff(row["vault_path"], row["diff"])
    row = update_finding_status(finding_id, "approved")
    events.log_event("lint_apply", {
        "id": finding_id, "vault_path": row["vault_path"], "auto": False,
    })
    return row


def reject_finding(finding_id: str) -> dict | None:
    return update_finding_status(finding_id, "rejected")


if __name__ == "__main__":
    try:
        from dotenv import load_dotenv
        load_dotenv(REPO_ROOT / ".env")
    except ImportError:
        pass
    findings = run_lint()
    auto = sum(1 for f in findings if f.get("status") == "auto_applied")
    print(f"lint run complete: {len(findings)} finding(s), {auto} auto-applied")
