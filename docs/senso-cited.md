# Senso + cited.md: Build-Ready Hackathon Guide

> Fetched live: June 12, 2026. Sources at end.

---

## 1. What Senso Is + What cited.md Is

**Senso** (`senso.ai`) is a context layer (CMS) for AI agents. It ingests raw sources (PDFs, DOCX, Markdown, Confluence, Notion, public websites), compiles them into a governed, version-controlled knowledge base, and exposes ingest / query / generate endpoints. Every answer is scored against verified ground truth and ships with a citation trace. (Senso.ai Inc., Toronto, 2018; targets regulated industries, now opening to developers.)

**cited.md** is an open, agent-native publishing domain operated by Senso. Compile a knowledge base in Senso, run `senso engine publish`, and your content is live at:

```
cited.md/<your-handle>/<slug>
```

in two formats: (1) human-readable HTML, (2) structured markdown + JSON metadata for machine consumption. Other agents — and AI search engines (ChatGPT, Perplexity, Claude, Google AI Overviews) — can discover, fetch, and cite it.

"Publish your agent's output to cited.md" = run your agent, ingest its output into Senso, compile, publish → a citable endpoint on the agentic web.

---

## 2. Setup: Account + API Key

**Step 1 — Sign up:** senso.ai → "Get Started". Free tier: **$100 in credits, no card required**. API keys start with `tgr_`.

**Step 2 — Install the CLI:**
```bash
npm install -g @senso-ai/cli
export SENSO_API_KEY="tgr_YOUR_KEY_HERE"
```

**Step 3 — Verify:**
```bash
senso whoami
senso org get
```

**Step 4 — Onboarding skill (optional):**
```bash
npx @senso-ai/shipables install senso-ai/senso-onboarding
```

Quickstart: https://docs.senso.ai/docs/hello-world

---

## 3. Publishing Agent Output — API + CLI

### Authentication (all REST calls)
```
Header: X-API-Key: tgr_YOUR_KEY
Base:   https://apiv2.senso.ai/api/v1
```

### 3a. Ingest raw text (REST)
```python
import os, requests

KEY     = os.environ["SENSO_API_KEY"]
BASE    = "https://apiv2.senso.ai/api/v1"
HEADERS = {"X-API-Key": KEY, "Content-Type": "application/json"}

resp = requests.post(f"{BASE}/content/raw", headers=HEADERS, json={
    "title":       "Weekly Research Digest — 2026-06-12",
    "body":        "## Key findings\n\n...",          # agent's markdown output
    "tags":        ["research", "digest", "weekly"],
    "provenance":  "vault/inbox/research-2026-06-12.md",
    "handle":      "yourhandle",
    "slug":        "weekly-digest-2026-06-12"
})
print(resp.json())   # content ID + processing status
```

### 3b. Query the knowledge base (REST)
```python
resp = requests.post(f"{BASE}/org/search", headers=HEADERS, json={
    "query": "What did the agent find about X?"
})
# cited passages with source IDs, relevance scores
```

### 3c. Generate + publish (CLI — primary hackathon path)
```bash
senso kb create-folder --name "research-vault"
senso kb create-raw --title "Digest" --body "$(cat brief.md)"
senso brand-kit set --file brand.json
senso generate run --content-type article
senso engine publish        # ← THE deliverable; content goes live on cited.md
```

### Citation schema
Required fields per article: `title`, `handle`, `slug`, `body`, `tags`, `provenance`. Platform auto-adds version, review date, author, structured metadata.

---

## 4. Consumption Side + Monetization

**Who reads cited.md content:** AI engines crawl + cite it; other agents query the endpoint; humans via HTML.

**Monetization — four composable rails (all optional for the hackathon):**

| Rail | Role |
|------|------|
| Coinbase CDP | Identity — server wallets for agents |
| Coinbase x402 | Transport — HTTP 402 micropayments per fetch |
| Stripe MPP | Fiat settlement — subscriptions/bulk |
| agentic.market | Discovery + price formation |

The free public layer satisfies "publish to cited.md."

---

## 5. Gotchas + Limits

- **Docs are thin.** Several public API-reference paths 404. **The CLI is the battle-tested entry point** — don't rely on raw REST without verifying endpoints live.
- **API key format:** must start with `tgr_` — otherwise wrong org or old v1 system.
- **$100 free credits:** generation calls consume more than ingest/search.
- **cited.md is Senso's publishing layer, not a standalone API** — no direct POST to cited.md.
- **`senso engine publish` is the magic command** — without it, content sits in the KB unpublished.
- **Content is public by default.**
- **MCP server** at `docs.senso.ai/mcp2` — use Senso as a tool call inside the agent if preferred.

---

## 6. Verdict for the Hackathon

**Required output target for the Senso prize track** ($2,000 credits; the challenge slide names it). Fit for Gardener: (1) agent synthesizes output with provenance → (2) `senso kb create-raw` → (3) `senso engine publish`. Make it the final step of the output pipeline, not the core. Budget 30–60 min. Risk: sparse docs — use the CLI, not raw REST.

---

## 7. Links (fetched June 12, 2026)

- [Senso homepage](https://www.senso.ai/)
- [cited.md product page](https://www.senso.ai/cited-md)
- [Senso SDK docs](https://docs.senso.ai)
- [Authentication docs](https://docs.senso.ai/docs/authentication)
- [Quickstart](https://docs.senso.ai/docs/hello-world)
- [cited.md landing](https://cited.md/)
- [Publishing guide](https://cited.md/article/how-do-i-publish-content-that-ai-agents-can-cite-and-pay-for)
- [cited.md architecture](https://cited.md/article/cited-md-an-endpoint-for-agents-on-the-agentic-web)
- [Citeables overview](https://cited.md/article/what-is-citeables)
- [Hackathon challenge page](https://ship-to-prod.devpost.com/)
