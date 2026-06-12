"""The markdown memory vault. Root = <repo>/vault, paths relative like
"preferences/housing.md". Every write logs a memory_write event with provenance.
"""

import difflib
import re
from datetime import datetime, timezone
from pathlib import Path

from backend.core import events

ROOT = Path(__file__).resolve().parents[2]
VAULT_ROOT = ROOT / "vault"


def _ensure_root() -> None:
    VAULT_ROOT.mkdir(parents=True, exist_ok=True)


def _full_path(path: str) -> Path:
    """Resolve a vault-relative path and refuse escapes outside the vault."""
    _ensure_root()
    full = (VAULT_ROOT / path).resolve()
    if not str(full).startswith(str(VAULT_ROOT.resolve())):
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


def list_files() -> list[dict]:
    """[{path, title, updated}] for every markdown file in the vault."""
    _ensure_root()
    files = []
    for full in sorted(VAULT_ROOT.rglob("*.md")):
        try:
            content = full.read_text(encoding="utf-8")
        except OSError:
            content = ""
        files.append(
            {
                "path": str(full.relative_to(VAULT_ROOT)),
                "title": _title_for(full, content),
                "updated": datetime.fromtimestamp(full.stat().st_mtime, tz=timezone.utc).isoformat(),
            }
        )
    return files


def read(path: str) -> str:
    full = _full_path(path)
    if not full.is_file():
        raise FileNotFoundError(path)
    return full.read_text(encoding="utf-8")


def write(path: str, content: str, source: str) -> None:
    """Write a vault file and log a memory_write event (source = provenance)."""
    full = _full_path(path)
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
    )


def all_files() -> dict[str, str]:
    _ensure_root()
    return {
        str(full.relative_to(VAULT_ROOT)): full.read_text(encoding="utf-8")
        for full in sorted(VAULT_ROOT.rglob("*.md"))
    }
