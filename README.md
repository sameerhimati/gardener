# Gardener

**An assistant whose memory takes care of itself.**

Everyone who uses AI with memory has hit the moment it remembers wrong: the diet you quit, the job you left, the gym you canceled. The longer you use today's AI, the more wrong it gets about you — and you can't see or fix what it believes.

Gardener is the opposite, built from three pieces that turn out to be one product:

1. **One agent you chat with**, acting for you on the open web.
2. **Standing watches as visible, steerable conversations.** Ask it to "watch Zillow for houses in my neighborhood" and the watch appears as its own chat you can open and steer mid-task — "only 3+ bedrooms, 1500+ sqft." Watches keep running unattended.
3. **Memory that gardens itself.** Your steering distills into a plain-markdown preference vault you can read — every fact with provenance. A background lint agent audits the vault against the event log, catches contradictions and staleness, fixes them with receipts (auto-applying high-confidence diffs, queueing risky ones for one-click approval), and publishes its correction changelog publicly with sources.

The more you use it, the better it knows you — the opposite of every assistant today.

## The loop

```
chat / steer a watch  →  every turn, tool call, memory write logged as events
        ↓                                   ↓
preference vault (markdown + provenance)    lint worker mines events
        ↑                                   ↓
auto-applied diffs  ←  contradiction/staleness findings + unified diffs
        ↓
public correction changelog (cited.md)
```

## Stack

FastAPI + hand-written Anthropic SDK agent loop · ClickHouse Cloud (events + lint findings) · Next.js (chat / watches / vault / lint feed) · Render (web + cron worker) · Senso CLI → cited.md (public changelog) · Pioneer (lint-agent inference) · Composio (real-world actions) · Langfuse (tracing).

See `docs/architecture.md` for the build contract and `docs/` for per-sponsor integration guides.

Built at the Harness Engineering Hackathon, June 2026.
