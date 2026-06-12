# Hackathon Intelligence Brief — Harness Engineering Hack (June 12, 2026)

**Compiled:** June 12, 2026 | Sources fetched live (see §8)

---

## 1. Logistics & Submission Requirements

| Field | Verified Detail |
|---|---|
| **Devpost URL** | https://harness-hack.devpost.com/ (bit.ly/devpost-june12 → 301 to same) |
| **Deadline** | June 12, 2026 @ 4:30 PM PDT — hard cutoff, late submissions rejected |
| **Demo format** | 3-minute demo recording (pre-recorded, via Devpost) + live demos 4:30–5:00 PM |
| **Required submission** | (1) 3-minute demo recording, (2) Public GitHub repo, (3) all Devpost fields |
| **Team size** | Max 4 people |
| **Eligibility** | 18+, government ID, register on AWS, AWS Code of Conduct |
| **No prior projects** | Explicitly prohibited — new work only |

**Slide vs Devpost:** "publish to cited.md" and "monetize with x402/MPP/CDP/agentic.market" do NOT appear in the Devpost submission checklist or judging criteria — organizer recommendations, not enforced gates.

---

## 2. Judging Criteria (Verbatim, 20% each)

1. **Autonomy** — "How well does the agent act on real-time data without manual intervention?"
2. **Idea** — "Does the solution have the potential to solve a meaningful problem or demonstrate real-world value?"
3. **Technical Implementation** — "How well was the solution implemented?"
4. **Tool Use** — "Did the solution effectively use sponsor tools?" (3+ required)
5. **Presentation (Demo)** — "Demonstration of the solution in 3 minutes"

Judges: engineers/architects from Anthropic, Pioneer, AWS, Stripe, others.

---

## 3. Prize Tracks — Per-Sponsor

| Sponsor | Prize | What They Reward |
|---|---|---|
| **Guild.ai** | $2,800 cash (1×$1k, 2×$500, 4×$200) | Most Innovative Use of Agents |
| **OpenUI** | $2,000 (1×$1k, 1×$500, 5×$100 HM) | Best Use of OpenUI |
| **Airbyte** | $1,750 cash ($1k/$500/$250) | Best Use of Airbyte's Agent Engine ("Conquer with Context") |
| **ClickHouse** | $1,600 (1st: $1k + $500 credits; 2nd: $500 credits + $250; **bonus $350 best Langfuse use**) | Best Use of ClickHouse |
| **Pioneer** | $500 cash + $1,500 inference credits promo | Best Use of Pioneer |
| **Render** | $1,000/$600/$400 Render credits | Best Use of Render |
| **TrueFoundry** | $1,000 platform credits | Best Use of TrueFoundry |
| **Composio** | $200 Amazon gift card | Best Agent Execution |
| **Senso.ai** | $2,000 credits | Best Use of Senso.ai |
| **AWS / Anthropic** | No separate prize listed | Sponsors/judges only |

---

## 4. Shipables.dev

A registry/marketplace for AI agent skills — "the npm for Agent Skills," built on the open Agent Skills standard (agentskills.io), sponsored by Senso.ai.

- Package a `SKILL.md` + scripts; publish via CLI (`npx @senso-ai/shipables install [skill-name]` to install; publish at shipables.dev/publish).
- **Not in judging criteria** — a community/ecosystem ask. Ties to the Senso prize track (Senso-backed).

---

## 5. cited.md

An "agent-first content layer" — endpoint for AI agents to retrieve verified information, search structured content, execute transactions. Powered by Senso. NOT in scored criteria, but publishing there demonstrates real-world agent action (boosts Autonomy + Tool Use perception) and ties to the Senso prize track.

---

## 6. Payment Rails

x402 (Coinbase/AWS, production on Bedrock AgentCore) · MPP (Stripe + Tempo, GA March 2026) · CDP (Coinbase facilitators for Base/Solana/Stellar) · agentic.market. **None appear in judging criteria.** Implementing one strengthens Technical Implementation/Autonomy perception but is not required.

---

## 7. Read-Between-the-Lines: What a Winning Entry Looks Like

**Load-bearing prize tracks (size + judging weight):**
1. **Guild.ai** ($2,800, largest cash) — "most innovative use of agents," not tool-specific. Target with genuinely novel agent architecture.
2. **OpenUI** ($2,000) — agent output as live rendered UI, not CLI.
3. **Airbyte** ($1,750) — "Agent Engine" framing wants data ingestion powering real agent decisions.
4. **ClickHouse** ($1,600 + $350 Langfuse) — store/query agent actions or web data AND instrument with Langfuse.
5. **Composio** ($200) — decorative unless already your action layer.

**Autonomy is the differentiator:** four of five criteria are table stakes. Judges from Anthropic/AWS will skew toward agents that genuinely loop on live web data, not fetch-once-and-display.

**cited.md + Shipables = soft Senso play:** ~30-min add capturing a $2k prize track and signaling you read the room.

**Payment rails = high-effort, low-scored.**

**Demo is 20% and 3 minutes hard:** script to 2:45; show the agent doing something real and autonomous.

---

## 8. Verification Log

| Source | Status |
|---|---|
| https://harness-hack.devpost.com/ | Fetched, full content (June 12, 2026) |
| https://bit.ly/devpost-june12 | 301 → harness-hack.devpost.com |
| https://harness-hack.devpost.com/rules | Fetched, full content |
| https://luma.com/harnesshack | Fetched, partial (schedule, judges) |
| https://shipables.dev | Fetched, full content |
| https://cited.md/ | Fetched, full content |
| https://ship-to-prod.devpost.com/ | Prior event — format cross-reference only |
| harness-hack.devpost.com/prizes | 404 — prizes from main page |

**Could NOT verify:** per-sponsor scoring rubrics beyond prize names; agentic.market as distinct live platform; AWS/Anthropic prize tracks; whether Shipables/cited.md are scored vs recommended.
