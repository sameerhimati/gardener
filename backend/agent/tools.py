"""Tool registry: Anthropic tool-schema dicts + the executor.

execute_tool logs tool_call before and tool_result after (payloads truncated
to 500 chars in events) and never raises — errors come back as result strings
so the agent loop can recover.
"""

import html
import json
import os
import re
from datetime import date, datetime, timezone

from backend.core import events, store, vault
from backend.integrations import composio_client

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
        "name": "web_search",
        "description": "Search the live web for a query and get back ranked results (title, URL, snippet). Use this to FIND sources before fetching them — e.g. 'soccer cleats deals', 'World Cup scores today', 'RTX 4090 price'. Then web_fetch the most promising result to confirm details.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "What to search for, in plain words"},
                "count": {"type": "integer", "description": "How many results to return (default 5)"},
            },
            "required": ["query"],
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
                "cadence_sec": {"type": "integer", "description": "Seconds between cycles (default 3600 = hourly; user can change per watch, up to once a day). Don't go below 300."},
                "act_mode": {
                    "type": "string",
                    "enum": ["off", "calendar", "discord"],
                    "description": "What this watch does on a GENUINE match: 'off' = report only, take no action (default; pure monitoring); 'calendar' = create a Google Calendar event for the match (use for time/date-bound finds like an event, deadline, viewing, or appointment); 'discord' = post the match to Discord (use for shareable alerts like a price drop, deal, or new listing the user wants pushed to a channel).",
                },
            },
            "required": ["task"],
        },
    },
    {
        "name": "list_watches",
        "description": "List all standing watches with their status and last result.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "cited_read",
        "description": (
            "Read Gardener's public correction changelog (cited.md) — the published record of "
            "what Gardener has learned and corrected in its memory, with receipts/provenance. "
            "Use this when you need PRIOR context or past corrections before deciding (e.g. 'have "
            "I been told this before?', 'did a previous correction reverse this preference?'). "
            "Returns the changelog markdown."
        ),
        "input_schema": {"type": "object", "properties": {}},
    },
]

# Append the scoped Composio (Gmail + Calendar) tool schemas at import. Wrapped
# so an import/network failure is swallowed and TOOLS still carries the built-in
# tools — graceful degradation: with no COMPOSIO_API_KEY this is just a no-op.
try:
    TOOLS.extend(composio_client.tool_schemas())
except Exception as _e:  # noqa: BLE001
    print(f"[tools] Composio schemas not loaded ({_e}); built-in tools only")


def execute_tool(name: str, tool_input: dict, session_id: str) -> str:
    # Resolve the calling user from the session record. THIS is how the spine
    # agent loop stays untouched: loop.run_turn passes only session_id, and we
    # look up user_id here — so a user's tool calls write to THEIR garden.
    user_id = store.session_user_id(session_id)
    events.log_event(
        "tool_call",
        {"name": name, "input": json.dumps(tool_input, default=str)[:500]},
        session_id,
        user_id=user_id,
    )
    try:
        result = _dispatch(name, tool_input or {}, session_id, user_id)
    except Exception as e:
        result = f"ERROR: {type(e).__name__}: {e}"
    events.log_event(
        "tool_result",
        {"name": name, "result": str(result)[:500]},
        session_id,
        user_id=user_id,
    )
    return result


def _dispatch(name: str, tool_input: dict, session_id: str, user_id: str) -> str:
    if name == "web_fetch":
        return _web_fetch(tool_input["url"])
    if name == "web_search":
        return _web_search(tool_input["query"], int(tool_input.get("count") or 5))
    if name == "vault_read":
        try:
            return vault.read(tool_input["path"], user_id=user_id)
        except FileNotFoundError:
            return f"ERROR: vault file not found: {tool_input['path']}"
    if name == "vault_write":
        vault.write(
            tool_input["path"], tool_input["content"], source=_source(session_id), user_id=user_id
        )
        return f"Wrote {tool_input['path']} ({len(tool_input['content'])} chars)"
    if name == "save_preference":
        return _save_preference(tool_input["topic"], tool_input["fact"], session_id, user_id)
    if name == "spawn_watch":
        return _spawn_watch(
            tool_input["task"],
            int(tool_input.get("cadence_sec") or 3600),
            session_id,
            user_id,
            act_mode=tool_input.get("act_mode") or "off",
        )
    if name == "list_watches":
        return json.dumps(store.list_watches(user_id=user_id), indent=2, default=str)
    if name == "cited_read":
        return _cited_read()
    # Composio (Gmail/Calendar) tools dispatch here, still inside execute_tool's
    # event-logging wrapper — so the action shows up in the activity trail.
    if composio_client.is_composio_tool(name):
        return composio_client.execute(name, tool_input, user_id=user_id)
    return f"ERROR: unknown tool: {name}"


def _source(session_id: str) -> str:
    return f"session:{session_id}" if session_id else "agent"


# ── cited.md (public correction changelog) ───────────────────────────────────

# cited.md publishes to a dynamic URL (https://cited.md/article/<content_id>),
# known only after a Senso publish run. The stable, always-present source is the
# local changelog the publish pipeline writes (publish/senso_publish.py →
# data/changelog.md). Read that; it IS the content published to cited.md.

def _cited_read() -> str:
    from pathlib import Path

    changelog = Path(__file__).resolve().parents[2] / "data" / "changelog.md"
    try:
        text = changelog.read_text()
    except FileNotFoundError:
        return (
            "cited.md changelog not generated yet (no corrections published). "
            "Run `python publish/senso_publish.py` to build/publish it. No prior "
            "corrections to cite."
        )
    return text[:8000] if text.strip() else "cited.md changelog is empty — no corrections recorded yet."


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


# ── web_search (Brave Search API) ────────────────────────────────────────────

def _web_search(query: str, count: int = 5) -> str:
    import httpx

    key = os.environ.get("BRAVE_API_KEY")
    if not key:
        return "web_search unavailable: BRAVE_API_KEY not set"
    response = httpx.get(
        "https://api.search.brave.com/res/v1/web/search",
        params={"q": query, "count": max(1, min(count, 10))},
        headers={"X-Subscription-Token": key, "Accept": "application/json"},
        timeout=10.0,
    )
    response.raise_for_status()
    results = (response.json().get("web") or {}).get("results") or []
    if not results:
        return f"No web results for: {query}"
    lines = [f"Web results for '{query}':"]
    for r in results[:count]:
        title = html.unescape(re.sub(r"</?strong>", "", r.get("title") or "")).strip()
        desc = html.unescape(re.sub(r"</?strong>", "", r.get("description") or "")).strip()
        url = r.get("url") or ""
        lines.append(f"- [{title}]({url}) — {desc}")
    return "\n".join(lines)[:2000]


# ── save_preference ──────────────────────────────────────────────────────────

def _save_preference(topic: str, fact: str, session_id: str, user_id: str) -> str:
    slug = re.sub(r"[^a-z0-9-]+", "-", topic.lower()).strip("-") or "general"
    path = f"preferences/{slug}.md"
    today = date.today().isoformat()
    bullet = f"- {fact} (src: {_source(session_id)} {today})"
    try:
        content = vault.read(path, user_id=user_id)
        content = re.sub(r"(?m)^updated:.*$", f"updated: {today}", content, count=1)
        if not content.endswith("\n"):
            content += "\n"
        content += bullet + "\n"
    except FileNotFoundError:
        content = f"---\ntopic: {slug}\nupdated: {today}\n---\n{bullet}\n"
    vault.write(path, content, source=_source(session_id), user_id=user_id)
    return f"Saved preference to {path}: {fact}"


# ── spawn_watch ──────────────────────────────────────────────────────────────

def _spawn_watch(
    task: str, cadence_sec: int, session_id: str, user_id: str, act_mode: str = "off"
) -> str:
    # A watch must never spawn watches: its own task text reads like a watch
    # request, so an unguarded model re-spawns itself every cycle (exponential
    # junk chats). Only the orchestrator (main chat) may plant new watches.
    # Scope the guards to THIS user's watches so one garden never sees another's.
    user_watches = store.list_watches(user_id=user_id)
    if any(w.get("session_id") == session_id for w in user_watches):
        return (
            "DENIED: you are a standing watch — you cannot spawn other watches. "
            "Just run your check and report."
        )
    # Near-duplicate guard: same task text already being watched.
    for w in user_watches:
        if w.get("status") == "active" and w.get("task", "").strip().lower() == task.strip().lower():
            return f"NOT SPAWNED: an active watch with this exact task already exists ({w['id']})."
    # Back-compat tolerance: unknown / legacy values (draft/send) → off.
    act_mode = act_mode if act_mode in ("off", "calendar", "discord") else "off"
    watch = store.create_watch(task, cadence_sec, act_mode=act_mode, user_id=user_id)
    events.log_event(
        "watch_spawn",
        {"watch_id": watch["id"], "task": task, "cadence_sec": cadence_sec,
         "act_mode": act_mode, "ts": datetime.now(timezone.utc).isoformat()},
        session_id,
        user_id=user_id,
    )
    return json.dumps(
        {"watch_id": watch["id"], "session_id": watch["session_id"], "task": task,
         "cadence_sec": cadence_sec, "act_mode": act_mode, "status": watch["status"]},
    )
