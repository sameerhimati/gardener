"""Composio integration — the watch-hit → act bridge (Calendar + Discord).

Fully OPTIONAL and lazy. The whole app must run with only ANTHROPIC_API_KEY:
- If COMPOSIO_API_KEY is unset or the SDK imports fail, available() is False,
  tool_schemas() returns [], and execute() returns a clean ERROR string.
- Nothing here ever raises into the agent loop.

Scoped tightly to two action slugs (keeps the model's token count sane):
    GOOGLECALENDAR_CREATE_EVENT, DISCORDBOT_CREATE_MESSAGE.

Gmail was dropped — Google OAuth for restricted Gmail scopes is hard-blocked.
Calendar and Discord both have clean Composio auth
(`composio link googlecalendar` / `composio link discordbot`).

See docs/composio.md (v3 SDK, composio + composio-anthropic 0.13.1). Trust that
guide over any older Composio knowledge: string slugs, AnthropicProvider,
connected_accounts.link() for onboarding.
"""

from __future__ import annotations

import os

# Stable internal user id — single source so multi-tenant is a param swap, not a
# rewrite. (docs/composio.md §4: never use "default".)
USER_ID = "sameer"

# The ONLY slugs we expose. Scope tightly: 2 write-actions for the demo loop.
# DISCORDBOT_CREATE_MESSAGE: verified v3 slug (toolkit DISCORDBOT) — required
# input is `channel_id`; `content` carries the message text (max 2000 chars).
SCOPED_SLUGS = [
    "GOOGLECALENDAR_CREATE_EVENT",
    "DISCORDBOT_CREATE_MESSAGE",
]
_TOOLKITS = ["GOOGLECALENDAR", "DISCORDBOT"]

# Lazy caches.
_composio = None  # Composio client instance
_schemas: list[dict] | None = None  # cached Anthropic tool-schema dicts
_slug_set: set[str] | None = None  # registered slug names (from the schemas)


# Connector metadata for the in-app Connections panel. Toolkit slug → label +
# the interactive CLI command that links a real account (docs/composio.md §4:
# connect via `composio link <toolkit>`).
_CONNECTORS = [
    {
        "key": "googlecalendar",
        "label": "Google Calendar",
        "toolkit": "GOOGLECALENDAR",
        "instructions": "composio link googlecalendar",
    },
    {
        "key": "discordbot",
        "label": "Discord",
        "toolkit": "DISCORDBOT",
        "instructions": "composio link discordbot",
    },
]


def connectors_status(user_id: str = USER_ID) -> list[dict]:
    """Status of each integration connector for the Connections panel.

    Returns one dict per connector: {key, label, connected, instructions}.
    Graceful: when COMPOSIO_API_KEY / the SDK is missing, every connector reads
    `connected: False` with its link command. Never raises.
    """
    base = [
        {
            "key": c["key"],
            "label": c["label"],
            "connected": False,
            "instructions": c["instructions"],
        }
        for c in _CONNECTORS
    ]
    if not available():
        return base

    # Find which toolkits have an active connected account for this user.
    connected_toolkits: set[str] = set()
    try:
        composio = _client()
        accounts = composio.connected_accounts.list(user_ids=[user_id])
        items = getattr(accounts, "items", None)
        if items is None and isinstance(accounts, dict):
            items = accounts.get("items", [])
        for acct in items or []:
            data = acct.model_dump() if hasattr(acct, "model_dump") else acct
            if not isinstance(data, dict):
                continue
            # Only count live accounts. Toolkit slug can surface a few ways
            # across SDK shapes — check the common ones.
            status = str(data.get("status", "")).upper()
            if status and status not in ("ACTIVE", "ENABLED", "CONNECTED"):
                continue
            toolkit = (
                data.get("toolkit")
                or data.get("appName")
                or data.get("app_name")
                or (data.get("toolkit_slug") if isinstance(data.get("toolkit_slug"), str) else None)
                or ""
            )
            if isinstance(toolkit, dict):
                toolkit = toolkit.get("slug") or toolkit.get("name") or ""
            if toolkit:
                connected_toolkits.add(str(toolkit).upper())
    except Exception as e:  # noqa: BLE001 — optional dep, degrade gracefully
        print(f"[composio] connectors_status failed, reporting all disconnected: {e}")
        return base

    for row, meta in zip(base, _CONNECTORS):
        row["connected"] = meta["toolkit"].upper() in connected_toolkits
    return base


def available() -> bool:
    """True only if COMPOSIO_API_KEY is set AND both SDK packages import cleanly."""
    if not os.environ.get("COMPOSIO_API_KEY"):
        return False
    try:
        import composio  # noqa: F401
        import composio_anthropic  # noqa: F401
    except Exception:
        return False
    return True


def _client():
    """Lazily build (and cache) the Composio client with the Anthropic provider."""
    global _composio
    if _composio is not None:
        return _composio
    from composio import Composio
    from composio_anthropic import AnthropicProvider

    _composio = Composio(provider=AnthropicProvider())
    return _composio


def tool_schemas() -> list[dict]:
    """Anthropic tool-schema dicts for the scoped Gmail+Calendar actions.

    Returns [] when Composio is unavailable. Cached after first success. Never
    raises — a failure here must not stop the built-in tools from loading.
    """
    global _schemas, _slug_set
    if _schemas is not None:
        return _schemas
    if not available():
        return []
    try:
        composio = _client()
        # Ask for our exact slugs only — 3 write-actions, nothing else. (The v3
        # `tools.get` `tools=` param takes exact slugs; keeps token count minimal.)
        tools = composio.tools.get(USER_ID, tools=SCOPED_SLUGS)
        wanted = set(SCOPED_SLUGS)
        scoped = [t for t in tools if t.get("name") in wanted]
        # If the slug filter wiped everything (naming drift), keep whatever the
        # scoped fetch returned rather than crash.
        _schemas = scoped or list(tools)
        _slug_set = {t.get("name") for t in _schemas}
        return _schemas
    except Exception as e:  # noqa: BLE001 — optional dep, degrade gracefully
        print(f"[composio] tool_schemas failed, degrading to no-op: {e}")
        _schemas = []
        _slug_set = set()
        return _schemas


def is_composio_tool(name: str) -> bool:
    """True if `name` is one of our registered Composio slugs."""
    if _slug_set is None:
        # Ensure schemas are loaded (populates the slug set) before answering.
        tool_schemas()
    return bool(_slug_set) and name in _slug_set


def execute(name: str, arguments: dict, user_id: str = USER_ID) -> str:
    """Execute one Composio tool and return a concise human-readable result.

    Never raises — returns an "ERROR: ..." string on any failure so the agent
    loop recovers and can tell the user what went wrong.
    """
    if not available():
        return (
            "ERROR: Composio is not configured (set COMPOSIO_API_KEY and connect "
            "Gmail/Calendar). Action skipped."
        )
    try:
        composio = _client()
        # v3 signature: execute(slug, arguments, *, user_id=...). arguments is the
        # 2nd positional arg.
        # dangerously_skip_version_check=True is the manual-execution equivalent of
        # "latest" — without it, 0.13.1 raises ToolVersionRequiredError on direct
        # execute (docs/composio.md §4 versioning gotcha; "latest" is NOT accepted
        # for manual execution, only the skip flag or a pinned version is).
        result = composio.tools.execute(
            name, arguments or {}, user_id=user_id, dangerously_skip_version_check=True
        )
        return _summarize(name, arguments or {}, result)
    except TypeError:
        # Older signature without the skip flag — fall back to a plain call.
        try:
            result = _client().tools.execute(name, arguments or {}, user_id=user_id)
            return _summarize(name, arguments or {}, result)
        except Exception as e:  # noqa: BLE001
            return f"ERROR: Composio {name} failed: {type(e).__name__}: {e}"
    except Exception as e:  # noqa: BLE001
        return f"ERROR: Composio {name} failed: {type(e).__name__}: {e}"


def _summarize(name: str, arguments: dict, result) -> str:
    """Turn a raw Composio result into one human-readable line for the agent.

    `result` is a ToolExecutionResponse (Pydantic) in v3 — normalize to a dict so
    the successful/error check works whether the SDK hands back a model or a dict.
    """
    data = result
    if hasattr(result, "model_dump"):
        try:
            data = result.model_dump()
        except Exception:  # noqa: BLE001
            data = result
    successful = True
    if isinstance(data, dict):
        # Composio wraps results as {"successful": bool, "data": {...}, "error": ...}
        if data.get("successful") is False or data.get("error"):
            return f"ERROR: Composio {name} returned: {data.get('error') or data}"
        successful = data.get("successful", True)

    if name == "GOOGLECALENDAR_CREATE_EVENT":
        title = (arguments.get("summary") or arguments.get("title") or "").strip()
        start = arguments.get("start_datetime") or arguments.get("start_time") or ""
        return f'Calendar event created{f": {title}" if title else ""}{f" at {start}" if start else ""}.'
    if name == "DISCORDBOT_CREATE_MESSAGE":
        channel = (arguments.get("channel_id") or "").strip()
        content = (arguments.get("content") or "").strip()
        preview = (content[:80] + "…") if len(content) > 80 else content
        bits = [b for b in [f'"{preview}"' if preview else "", f"to channel {channel}" if channel else ""] if b]
        return f"Discord message posted{(' ' + ' '.join(bits)) if bits else ''}."
    return f"Composio {name} {'succeeded' if successful else 'completed'}."
