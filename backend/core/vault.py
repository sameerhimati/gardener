"""The markdown memory vault. Root = <repo>/vault, paths relative like
"preferences/housing.md". Every write logs a memory_write event with provenance.

Multi-tenant: each user has an isolated garden under vault/<user_id>/. The
default user_id is "sameer" — the committed seed lives at vault/sameer/, so the
existing single-user demo (and any header-less caller: curl, the cron lint
worker, diffs.apply_diff) keeps working unchanged. A new user's vault/<uid>/
starts empty and onboarding fills it.
"""

import difflib
import re
from datetime import datetime, timezone
from pathlib import Path

from backend.core import events

ROOT = Path(__file__).resolve().parents[2]
VAULT_ROOT = ROOT / "vault"

DEFAULT_USER = "sameer"


def _user_root(user_id: str) -> Path:
    """Per-user garden root: vault/<user_id>/. Sanitizes user_id so a hostile
    token can't escape the vault (no slashes, dots, etc.)."""
    safe = re.sub(r"[^a-zA-Z0-9_-]+", "", user_id or "") or DEFAULT_USER
    root = VAULT_ROOT / safe
    return root


def _ensure_root(user_id: str = DEFAULT_USER) -> Path:
    root = _user_root(user_id)
    root.mkdir(parents=True, exist_ok=True)
    return root


def _full_path(path: str, user_id: str = DEFAULT_USER) -> Path:
    """Resolve a vault-relative path under the user's garden and refuse escapes."""
    root = _ensure_root(user_id)
    full = (root / path).resolve()
    if not str(full).startswith(str(root.resolve())):
        raise ValueError(f"path escapes vault: {path}")
    return full


def _title_for(path: Path, content: str) -> str:
    m = re.search(r"(?m)^topic:\s*(.+)$", content)
    if m:
        return m.group(1).strip()
    m = re.search(r"(?m)^#\s+(.+)$", content)
    if m:
        return m.group(1).strip()
    return path.stem


def list_files(user_id: str = DEFAULT_USER) -> list[dict]:
    """[{path, title, updated}] for every markdown file in the user's vault."""
    root = _ensure_root(user_id)
    files = []
    for full in sorted(root.rglob("*.md")):
        try:
            content = full.read_text(encoding="utf-8")
        except OSError:
            content = ""
        files.append(
            {
                "path": str(full.relative_to(root)),
                "title": _title_for(full, content),
                "updated": datetime.fromtimestamp(full.stat().st_mtime, tz=timezone.utc).isoformat(),
            }
        )
    return files


def read(path: str, user_id: str = DEFAULT_USER) -> str:
    full = _full_path(path, user_id)
    if not full.is_file():
        raise FileNotFoundError(path)
    return full.read_text(encoding="utf-8")


def write(path: str, content: str, source: str, user_id: str = DEFAULT_USER) -> None:
    """Write a vault file and log a memory_write event (source = provenance)."""
    full = _full_path(path, user_id)
    old = full.read_text(encoding="utf-8") if full.is_file() else ""
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_text(content, encoding="utf-8")

    if old:
        preview = "".join(
            difflib.unified_diff(
                old.splitlines(keepends=True),
                content.splitlines(keepends=True),
                fromfile=f"a/{path}",
                tofile=f"b/{path}",
            )
        )
    else:
        preview = content
    events.log_event(
        "memory_write",
        {"path": path, "source": source, "diff_preview": preview[:300]},
        user_id=user_id,
    )


def all_files(user_id: str = DEFAULT_USER) -> dict[str, str]:
    root = _ensure_root(user_id)
    return {
        str(full.relative_to(root)): full.read_text(encoding="utf-8")
        for full in sorted(root.rglob("*.md"))
    }
