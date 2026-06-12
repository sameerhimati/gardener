# Composio Integration Guide — Gardener Agent (Gmail + Google Calendar)

> Fetched from composio.dev / docs.composio.dev — June 12, 2026

---

## 1. What It Is

Composio is a tool-execution layer for AI agents: it handles OAuth connections to 1,000+ third-party apps, normalises their APIs into LLM-friendly tool schemas, and executes tool calls on behalf of your agent. You feed the tool schemas to Claude, Claude decides which tool to call, and you hand the resulting tool-use block back to Composio to execute — no custom OAuth code, no raw HTTP clients per app. As of mid-2026 it is on SDK v3 (session-based architecture, `composio` + provider packages), and `composio-anthropic` 0.13.1 ships full native Anthropic Messages API support.

---

## 2. Setup

### 2.1 Account and API key

1. Sign up at <https://app.composio.dev> — free tier, no credit card.
2. Dashboard → API Keys → copy your `COMPOSIO_API_KEY`.

### 2.2 Python install

```bash
pip install composio composio-anthropic anthropic
# Python ≥3.10 required; composio-anthropic 0.13.1 is current (May 2026)
```

```bash
export COMPOSIO_API_KEY=your_key
export ANTHROPIC_API_KEY=your_key
```

### 2.3 Connect Gmail and Google Calendar — do this ONCE before any demo

**Option A: CLI (fastest for personal/internal use)**

```bash
curl -fsSL https://composio.dev/install | bash
composio login                                         # opens browser

# Connect accounts — each opens a browser OAuth consent screen
composio connected-accounts link gmail
composio connected-accounts link googlecalendar

# Verify both are ACTIVE
composio connected-accounts list --toolkits gmail
composio connected-accounts list --toolkits googlecalendar
```

**Option B: Programmatic (for onboarding real users)**

```python
from composio import Composio

composio = Composio(api_key="...")

# Get auth_config_id from Composio dashboard → Auth Configs

connection = composio.connected_accounts.link(
    user_id="sameer",                  # stable ID — not email
    auth_config_id="ac_XXXXXXXXXXXX",  # Gmail auth config
    callback_url="http://localhost:8000/oauth/callback",
)
print(connection.redirect_url)         # open in browser; user completes Google consent

account = connection.wait_for_connection()
print(account.status)                  # "ACTIVE"
print(account.id)                      # ca_XXXXXXXXXX
```

Repeat with the Google Calendar `auth_config_id`. Connected accounts persist (Composio handles token refresh) until the user revokes access.

---

## 3. SDK Usage: Tool Schemas + Execution Loop

### 3.1 Fetch tool definitions in Anthropic format

```python
from composio import Composio
from composio_anthropic import AnthropicProvider
import anthropic

composio = Composio(provider=AnthropicProvider())
client   = anthropic.Anthropic()

# Scope to only Gmail + Google Calendar — keeps token count sane
session = composio.create(
    user_id="sameer",
    toolkits=["GMAIL", "GOOGLECALENDAR"],
)
tools = session.tools()          # list[dict] in Anthropic tool-use schema format
```

Filter to a subset of actions:

```python
tools = composio.tools.get(
    "sameer",
    toolkits=["GMAIL", "GOOGLECALENDAR"],
    search="send email draft read calendar events create",
)
```

### 3.2 Full Claude tool-use loop

```python
import json

messages = [{"role": "user", "content": "Draft an email to arjun@example.com about tomorrow's Atlas sync."}]

response = client.messages.create(
    model="claude-opus-4-5",
    max_tokens=4096,
    tools=tools,
    messages=messages,
)

while response.stop_reason == "tool_use":
    results = composio.provider.handle_tool_calls(
        user_id="sameer",
        response=response,        # full Anthropic Message object
    )

    messages.append({"role": "assistant", "content": response.content})

    tool_use_blocks = [b for b in response.content if b.type == "tool_use"]
    messages.append({
        "role": "user",
        "content": [
            {
                "type": "tool_result",
                "tool_use_id": tool_use_blocks[i].id,
                "content": json.dumps(result),
            }
            for i, result in enumerate(results)
        ],
    })

    response = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=4096,
        tools=tools,
        messages=messages,
    )

for block in response.content:
    if block.type == "text":
        print(block.text)
```

### 3.3 Manually execute a single tool (no LLM in the loop)

```python
result = composio.tools.execute(
    "GMAIL_SEND_EMAIL",
    user_id="sameer",
    arguments={
        "recipient_email": "arjun@example.com",
        "subject": "Atlas sync",
        "body": "Let's connect at 10am.",
    },
)
```

### 3.4 Key action slugs

**Gmail**
| Slug | What it does |
|------|-------------|
| `GMAIL_SEND_EMAIL` | Send immediately |
| `GMAIL_CREATE_EMAIL_DRAFT` | Create draft (no send) |
| `GMAIL_FETCH_EMAILS` | List/search inbox with filters |
| `GMAIL_REPLY_TO_THREAD` | Reply in thread |
| `GMAIL_FETCH_MESSAGE_BY_THREAD_ID` | Read full thread |

**Google Calendar**
| Slug | What it does |
|------|-------------|
| `GOOGLECALENDAR_EVENTS_LIST` | List events on a calendar |
| `GOOGLECALENDAR_EVENTS_LIST_ALL_CALENDARS` | Unified view across calendars |
| `GOOGLECALENDAR_CREATE_EVENT` | Create event with time/duration |
| `GOOGLECALENDAR_PATCH_EVENT` | Update specific fields |
| `GOOGLECALENDAR_FIND_EVENT` | Natural-language event search |

---

## 4. Gotchas

**`initiate()` is dead for Composio-managed OAuth.** As of 2026-05-08 (new orgs) / 2026-07-03 (all orgs), `composio.connected_accounts.initiate()` on a Composio-managed OAuth config returns 400. Use `link()` exclusively. Custom OAuth configs still work on `initiate()`.

**Google refresh-token expiry on unverified apps.** With Composio-managed OAuth (default), Google may invalidate refresh tokens after 7 days if the consent screen is in "Testing" mode with <100 users. For a personal agent, add yourself as a test user in Google Cloud Console and the token survives. Production: register your own app + Google verification.

**Shared quota on managed auth.** Composio's default Gmail/Calendar OAuth app shares Google API quota across all Composio customers. If you hit limits, create a custom auth config (own Google Cloud project).

**Free tier rate limit.** 20,000 tool calls/month free; 100 calls/min. $29/month → 200K calls/month.

**`user_id="default"` anti-pattern.** Use a stable internal ID from day one even for a single-user agent.

**Tool count and context.** `session.tools()` without `toolkits=` scoping returns up to ~20 toolkits worth of schemas. Always scope or pass `search=`.

**Toolkit versioning (SDK ≥0.9.0).** If `composio.tools.execute()` throws a versioning error, add `toolkit_version="latest"` or pin to the version from `composio tools info <SLUG>`.

---

## 5. What Changed Since Early 2025

The 2025 v3 SDK is a near-complete rewrite of v1. **Do not follow any tutorial dated before mid-2025.**

| Old (v1) | New (v3) | Notes |
|----------|----------|-------|
| `ComposioToolSet` | `Composio` class + `AnthropicProvider` | `ComposioToolSet` deprecated |
| `apps=` parameter | `toolkits=` | Renamed everywhere |
| `Action.GMAIL_*` enums | string slugs `"GMAIL_SEND_EMAIL"` | 1,545 slugs renamed to `APP_VERB_NOUN` |
| Entity ID | `user_id` | Explicit on every call |
| `ToolSet.get_tools()` | `session.tools()` or `composio.tools.get()` | Session is the recommended entry point |
| `connected_accounts.initiate()` | `connected_accounts.link()` | `initiate()` deprecated for managed OAuth May 2026 |
| UUID resource IDs | nano IDs (`ca_xxx`, `ac_xxx`) | Short IDs everywhere |
| `integration_id` | `auth_config_id` | Integrations renamed to auth configs |
| `toolsets` concept | `providers` | `composio_anthropic` exports `AnthropicProvider` |

The `composio-anthropic` package (not `composio_openai` + `base_url` hack) is the correct import for the raw Anthropic Messages API.

---

## 6. Verdict

Composio is **load-bearing** for Gardener: it eliminates the OAuth plumbing that would otherwise dominate the first sprint, and its `handle_tool_calls` closes the agentic loop in one line — freeing you to focus on the vault-event schema and lint worker, which are the actual wedge.

---

## 7. Links (fetched June 12, 2026)

- [Anthropic Provider — Composio Docs](https://docs.composio.dev/docs/providers/anthropic)
- [Fetching Tools and Toolkits](https://docs.composio.dev/docs/toolkits/fetching-tools-and-toolkits)
- [Executing Tools](https://docs.composio.dev/docs/tools-direct/executing-tools)
- [Authenticating Tools](https://docs.composio.dev/docs/tools-direct/authenticating-tools)
- [Connected Accounts](https://docs.composio.dev/docs/auth-configuration/connected-accounts)
- [Users and Sessions](https://docs.composio.dev/docs/users-and-sessions)
- [Migration Guide: v1 → v3](https://docs.composio.dev/docs/migration-guide/new-sdk)
- [Managed vs Custom Auth](https://docs.composio.dev/docs/custom-app-vs-managed-app)
- [Gmail Toolkit](https://docs.composio.dev/toolkits/gmail)
- [Google Calendar Toolkit](https://docs.composio.dev/toolkits/googlecalendar)
- [composio-anthropic on PyPI (v0.13.1, May 14 2026)](https://pypi.org/project/composio-anthropic/)
- [Composio Pricing](https://composio.dev/pricing)
