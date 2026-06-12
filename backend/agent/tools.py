"""Tool registry: Anthropic tool-schema dicts + the executor.

execute_tool logs tool_call before and tool_result after (payloads truncated
to 500 chars in events) and never raises — errors come back as result strings
so the agent loop can recover.
"""

import html
import json
import re
from datetime import date, datetime, timezone

from backend.core import events, store, vault

TOOLS: list[dict] = [
    {
        "name": "web_fetch",
        "description": "Fetch a URL and return its readable text content (HTML stripped, truncated to 8000 chars). Use for checking listings, articles, prices, any web source.",
        "input_schema": {
            "type": "object",
            "properties": {"url": {"type": "string", "description": "Absolute URL to fetch"}},
            "required": ["url"],
        },
    },
    {
        "name": "vault_read",
        "description": "Read a file from the memory vault (markdown). Paths are vault-relative, e.g. 'preferences/housing.md'.",
        "input_schema": {
            "type": "object",
            "properties": {"path": {"type": "string", "description": "Vault-relative path"}},
            "required": ["path"],
        },
    },
    {
        "name": "vault_write",
        "description": "Write (create or overwrite) a file in the memory vault. Use for structured notes; for single durable preference facts prefer save_preference.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Vault-relative path"},
                "content": {"type": "string", "description": "Full new file content (markdown)"},
            },
            "required": ["path", "content"],
        },
    },
    {
        "name": "save_preference",
        "description": "Save one durable user preference fact to the vault under preferences/<topic>.md. Use whenever the user states a lasting preference, constraint, or fact about themselves.",
        "input_schema": {
            "type": "object",
            "properties": {
                "topic": {"type": "string", "description": "Short topic slug, e.g. 'housing', 'food'"},
                "fact": {"type": "string", "description": "One short preference fact, e.g. 'Wants 3+ bedrooms'"},
            },
            "required": ["topic", "fact"],
        },
    },
    {
        "name": "spawn_watch",
        "description": "Spawn a standing watch — an ongoing monitoring task that runs on a cadence in its own chat. Use when the user asks to watch/monitor/track something over time.",
        "input_schema": {
            "type": "object",
            "properties": {
                "task": {"type": "string", "description": "What to watch, in plain language, including sources if known"},
                "cadence_sec": {"type": "integer", "description": "Seconds between cycles (default 120)"},
            },
            "required": ["task"],
        },
    },
    {
        "name": "list_watches",
        "description": "List all standing watches with their status and last result.",
        "input_schema": {"type": "object", "properties": {}},
    },
]


def execute_tool(name: str, tool_input: dict, session_id: str) -> str:
    events.log_event(
        "tool_call",
        {"name": name, "input": json.dumps(tool_input, default=str)[:500]},
        session_id,
    )
    try:
        result = _dispatch(name, tool_input or {}, session_id)
    except Exception as e:
        result = f"ERROR: {type(e).__name__}: {e}"
    events.log_event(
        "tool_result",
        {"name": name, "result": str(result)[:500]},
        session_id,
    )
    return result


def _dispatch(name: str, tool_input: dict, session_id: str) -> str:
    if name == "web_fetch":
        return _web_fetch(tool_input["url"])
    if name == "vault_read":
        try:
            return vault.read(tool_input["path"])
        except FileNotFoundError:
            return f"ERROR: vault file not found: {tool_input['path']}"
    if name == "vault_write":
        vault.write(tool_input["path"], tool_input["content"], source=_source(session_id))
        return f"Wrote {tool_input['path']} ({len(tool_input['content'])} chars)"
    if name == "save_preference":
        return _save_preference(tool_input["topic"], tool_input["fact"], session_id)
    if name == "spawn_watch":
        return _spawn_watch(tool_input["task"], int(tool_input.get("cadence_sec") or 120), session_id)
    if name == "list_watches":
        return json.dumps(store.list_watches(), indent=2, default=str)
    return f"ERROR: unknown tool: {name}"


def _source(session_id: str) -> str:
    return f"session:{session_id}" if session_id else "agent"


# ── web_fetch ────────────────────────────────────────────────────────────────

def _web_fetch(url: str) -> str:
    import httpx

    response = httpx.get(
        url,
        timeout=10.0,
        follow_redirects=True,
        headers={"User-Agent": "Mozilla/5.0 (compatible; Gardener/0.1)"},
    )
    response.raise_for_status()
    content_type = response.headers.get("content-type", "")
    text = response.text
    if "html" in content_type or text.lstrip()[:1] == "<":
        text = _strip_html(text)
    return text[:8000]


def _strip_html(raw: str) -> str:
    text = re.sub(r"(?is)<(script|style|noscript|svg|head)[^>]*>.*?</\1>", " ", raw)
    text = re.sub(r"(?i)<br\s*/?>|</p>|</div>|</li>|</tr>|</h[1-6]>", "\n", text)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    text = html.unescape(text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n\n", text)
    return text.strip()


# ── save_preference ──────────────────────────────────────────────────────────

def _save_preference(topic: str, fact: str, session_id: str) -> str:
    slug = re.sub(r"[^a-z0-9-]+", "-", topic.lower()).strip("-") or "general"
    path = f"preferences/{slug}.md"
    today = date.today().isoformat()
    bullet = f"- {fact} (src: {_source(session_id)} {today})"
    try:
        content = vault.read(path)
        content = re.sub(r"(?m)^updated:.*$", f"updated: {today}", content, count=1)
        if not content.endswith("\n"):
            content += "\n"
        content += bullet + "\n"
    except FileNotFoundError:
        content = f"---\ntopic: {slug}\nupdated: {today}\n---\n{bullet}\n"
    vault.write(path, content, source=_source(session_id))
    return f"Saved preference to {path}: {fact}"


# ── spawn_watch ──────────────────────────────────────────────────────────────

def _spawn_watch(task: str, cadence_sec: int, session_id: str) -> str:
    watch = store.create_watch(task, cadence_sec)
    events.log_event(
        "watch_spawn",
        {"watch_id": watch["id"], "task": task, "cadence_sec": cadence_sec,
         "ts": datetime.now(timezone.utc).isoformat()},
        session_id,
    )
    return json.dumps(
        {"watch_id": watch["id"], "session_id": watch["session_id"], "task": task,
         "cadence_sec": cadence_sec, "status": watch["status"]},
    )
