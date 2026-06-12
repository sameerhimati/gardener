"""Unified diff make/apply for vault files.

make_diff produces a standard unified diff (difflib). apply_diff reconstructs
the new content by applying the hunks to the current vault file and writes it
back through vault.write (which logs the memory_write event).

Note: content should be newline-terminated (vault markdown always is) — a
missing trailing newline on the final line is difflib's classic blind spot.
"""

import difflib
import re

from backend.core import vault

_HUNK_RE = re.compile(r"@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


def make_diff(path: str, old: str, new: str) -> str:
    return "".join(
        difflib.unified_diff(
            old.splitlines(keepends=True),
            new.splitlines(keepends=True),
            fromfile=f"a/{path}",
            tofile=f"b/{path}",
        )
    )


def apply_diff(path: str, diff: str) -> None:
    """Apply a unified diff (as produced by make_diff) to a vault file."""
    try:
        old = vault.read(path)
    except FileNotFoundError:
        old = ""
    new = _apply_unified(old, diff)
    vault.write(path, new, source="apply_diff")


def _apply_unified(old: str, diff: str) -> str:
    """Reconstruct the new text from old text + unified diff hunks."""
    old_lines = old.splitlines(keepends=True)
    out: list[str] = []
    pos = 0  # cursor into old_lines
    in_hunk = False

    for raw in diff.splitlines(keepends=True):
        if not in_hunk and (raw.startswith("---") or raw.startswith("+++")):
            continue  # file headers
        if raw.startswith("@@"):
            m = _HUNK_RE.match(raw)
            if not m:
                continue
            old_start = int(m.group(1))
            old_count = int(m.group(2)) if m.group(2) is not None else 1
            # for a pure-insert hunk (-N,0) the insert point is AFTER line N
            start = old_start if old_count == 0 else old_start - 1
            out.extend(old_lines[pos:start])
            pos = start
            in_hunk = True
        elif not in_hunk:
            continue
        elif raw.startswith("+"):
            out.append(raw[1:])
        elif raw.startswith("-"):
            pos += 1
        elif raw.startswith(" "):
            out.append(raw[1:])
            pos += 1
        # anything else ("\ No newline at end of file", blanks) — skip

    out.extend(old_lines[pos:])
    return "".join(out)
