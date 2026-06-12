"""Publish Gardener's correction changelog to cited.md via the Senso CLI.

Builds "What Gardener learned and corrected, with receipts" from lint findings
and recent memory_write events, writes it to data/changelog.md, then ships it
with the Senso CLI per docs/senso-cited.md (kb create-raw → engine publish).

Gracefully no-ops (with instructions) if SENSO_API_KEY is unset or the `senso`
CLI is not installed. Run from the repo root: python publish/senso_publish.py
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

# Load .env so SENSO_API_KEY is picked up when run standalone (the backend app
# loads it too, but this script runs on its own — without this it silently no-ops).
try:
    from dotenv import load_dotenv

    load_dotenv(REPO_ROOT / ".env")
except ImportError:
    pass

DATA_DIR = REPO_ROOT / "data"
CHANGELOG_PATH = DATA_DIR / "changelog.md"
FINDINGS_JSONL = DATA_DIR / "findings.jsonl"
EVENTS_JSONL = DATA_DIR / "events.jsonl"

SRC_RE = re.compile(r"\(src:\s*([^)]+)\)")


# ── data loading (lazy imports, JSONL fallbacks) ────────────────────────────


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows: list[dict] = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def load_findings() -> list[dict]:
    """Lint findings via backend.worker.lint_worker.list_findings(), else JSONL."""
    try:
        from backend.worker.lint_worker import list_findings  # lazy import

        findings = list_findings()
        return [
            f.model_dump() if hasattr(f, "model_dump") else dict(f) for f in findings
        ]
    except Exception as exc:
        print(f"[senso_publish] lint_worker not usable ({exc}); reading {FINDINGS_JSONL}")
        return _read_jsonl(FINDINGS_JSONL)


def load_memory_writes(limit: int = 50) -> list[dict]:
    """Recent memory_write events via backend.core.events, else JSONL."""
    try:
        from backend.core.events import recent_events  # lazy import

        return recent_events(limit=limit, kinds=["memory_write"])
    except Exception as exc:
        print(f"[senso_publish] events module not usable ({exc}); reading {EVENTS_JSONL}")
        rows = [e for e in _read_jsonl(EVENTS_JSONL) if e.get("kind") == "memory_write"]
        return rows[-limit:]


# ── changelog rendering ──────────────────────────────────────────────────────


def extract_sources(*texts: str) -> list[str]:
    """Pull provenance out of '(src: ...)' suffixes, deduped, order-preserving."""
    seen: list[str] = []
    for text in texts:
        for match in SRC_RE.findall(text or ""):
            src = match.strip()
            if src and src not in seen:
                seen.append(src)
    return seen


def build_changelog(findings: list[dict], memory_writes: list[dict]) -> str:
    today = date.today().isoformat()
    lines: list[str] = [
        "# What Gardener learned and corrected, with receipts",
        "",
        f"_Correction changelog generated {today} by Gardener's self-linting memory loop._",
        "",
        "Gardener keeps a markdown preference vault and an append-only event log.",
        "A lint worker audits the vault against recent events; when a belief is",
        "contradicted by newer evidence, it proposes (or auto-applies) a diff.",
        "Every correction below carries its provenance.",
        "",
    ]

    if findings:
        lines += ["## Corrections", ""]
        for i, f in enumerate(findings, 1):
            summary = f.get("summary") or "(no summary)"
            lines += [
                f"### {i}. {summary}",
                "",
                f"- **Rule:** {f.get('rule', 'unknown')}",
                f"- **Vault file:** `{f.get('vault_path', '?')}`",
                f"- **Confidence:** {f.get('confidence', '?')} · **Severity:** "
                f"{f.get('severity', '?')} · **Status:** {f.get('status', '?')}",
                f"- **When:** {f.get('ts', '?')}",
                "",
            ]
            diff = f.get("diff") or ""
            if diff:
                lines += ["```diff", diff.rstrip("\n"), "```", ""]
            sources = extract_sources(summary, diff)
            if sources:
                lines += ["**Receipts:** " + " · ".join(f"`{s}`" for s in sources), ""]
    else:
        lines += [
            "## Corrections",
            "",
            "_No lint findings yet — run the lint worker "
            "(`python -m backend.worker.lint_worker`) first._",
            "",
        ]

    if memory_writes:
        lines += ["## Recent memory writes", ""]
        for ev in memory_writes:
            payload = ev.get("payload") or {}
            if isinstance(payload, str):
                try:
                    payload = json.loads(payload)
                except json.JSONDecodeError:
                    payload = {"text": payload}
            path = payload.get("path", "?")
            source = payload.get("source", "")
            ts = ev.get("ts", "?")
            entry = f"- `{path}` — {ts}"
            if source:
                entry += f" (source: {source})"
            lines.append(entry)
        lines.append("")

    lines += [
        "---",
        "",
        "_Published from the Gardener event log via Senso → cited.md._",
        "",
    ]
    return "\n".join(lines)


# ── Senso CLI publish (docs/senso-cited.md §3c) ──────────────────────────────


def publish_to_senso(changelog: str, title: str) -> bool:
    if not os.environ.get("SENSO_API_KEY"):
        print(
            "[senso_publish] SENSO_API_KEY not set — skipping publish.\n"
            "  To publish: sign up at https://senso.ai ($100 free credits, no card),\n"
            "  grab your tgr_... key, then:\n"
            "    npm install -g @senso-ai/cli\n"
            '    export SENSO_API_KEY="tgr_..."\n'
            "    python publish/senso_publish.py"
        )
        return False
    if shutil.which("senso") is None:
        print(
            "[senso_publish] `senso` CLI not found on PATH — skipping publish.\n"
            "  Install it with: npm install -g @senso-ai/cli\n"
            "  Verify with:     senso whoami"
        )
        return False

    # Per docs/senso-cited.md: create-raw puts it in the KB, engine publish
    # is the magic command that actually puts it live on cited.md.
    for cmd in (
        ["senso", "kb", "create-raw", "--title", title, "--body", changelog],
        ["senso", "engine", "publish"],
    ):
        print(f"[senso_publish] running: {' '.join(cmd[:4])} ...")
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.stdout.strip():
            print(result.stdout.strip())
        if result.returncode != 0:
            print(f"[senso_publish] command failed ({result.returncode}):")
            if result.stderr.strip():
                print(result.stderr.strip())
            return False
    print("[senso_publish] published — check cited.md/<your-handle>/")
    return True


def main() -> int:
    findings = load_findings()
    memory_writes = load_memory_writes()
    changelog = build_changelog(findings, memory_writes)

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    CHANGELOG_PATH.write_text(changelog)
    print(
        f"[senso_publish] wrote {CHANGELOG_PATH} "
        f"({len(findings)} corrections, {len(memory_writes)} memory writes)"
    )

    title = f"What Gardener learned and corrected — {date.today().isoformat()}"
    publish_to_senso(changelog, title)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
