# Gardener — project context for Claude Code sessions

An assistant whose memory takes care of itself. Three pieces, one product:

1. **One main agent you chat with** — the orchestrator. It acts on the open web.
2. **Standing watches run as visible subagent chats** — when the agent spawns a watch ("watch Zillow for houses in my neighborhood"), it appears as its own conversation you can open and steer mid-task ("only 3+ bedrooms, 1500+ sqft").
3. **Steering distills into durable preference memory** — a plain-markdown vault you can read. A background lint agent keeps that memory clean: it catches contradictions and staleness against the event log, proposes diffs with receipts, auto-applies high-confidence fixes, and publishes its correction changelog publicly.

## Source of truth

- `docs/architecture.md` — the build contract (module layout, interfaces, API, schemas). Read it before writing any code.
- `docs/<sponsor>.md` — live-verified integration guides with hard-won gotchas (Composio is v3, all older tutorials are wrong; Senso publishes via CLI not REST; Render background work = cron job, not Workflows beta; etc.). Do not rediscover these.
- `PRD-gardener.md` — the original hackathon PRD. Reference, not roadmap.

## Build rules

- **Sameer hand-writes the spine**: `backend/agent/loop.py` (the core agent loop) and `backend/worker/rules/contradiction.py` (the contradiction lint rule). Claude scopes, teaches, and builds everything around them — do NOT autonomously generate those two files.
- Parallelize the grunt work (integrations, UI, deploy, peripheral lint rules) with subagents; the spine stays hand-built.
- Ship beats re-architect. Simplest solution that solves the problem.
