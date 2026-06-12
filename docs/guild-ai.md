# Guild AI — Build-Ready Integration Guide

**As of:** June 12, 2026 | Sources fetched live

---

## 1. What It Is

Guild.ai (guild.ai) is an **agent control plane** that launched in open beta on April 29, 2026 with a $44M Series A (Google Ventures, Khosla, NFX). It is a centralized governance and observability layer that sits between your agent code and your tools/LLMs — enforcing identity, scoped credentials, cost controls, audit trails, and human-in-the-loop approval gates at runtime.

**Confidence: High.** This is definitively NOT the old `guildai` ML experiment-tracking Python library (github.com/guildai/guildai, PyPI `guildai`) — that's a separate, older project by a different team. The control-plane Guild is led by former Meta Engineering VP James Everingham. The name collision is a genuine gotcha.

---

## 2. Setup: Account and Install

### Account
1. [app.guild.ai](https://app.guild.ai) — no credit card for Free tier.
2. Sign up, create an organization and workspace.

### CLI Install (Node.js 18+ required)
```bash
npm install -g @guildai/cli
guild auth login          # opens browser
guild auth status         # verify
```

### Initialize an agent project
```bash
mkdir my-agent && cd my-agent
guild agent init --name my-agent --template LLM
```

> **Python note:** The Guild SDK is TypeScript-only (`@guildai/agents-sdk`). No official Python SDK as of June 2026.

---

## 3. Minimal Integration for Gardener (Python)

### Option A — LLM Proxy Gateway (recommended for Python)

Guild operates a model-agnostic proxy that mediates all LLM calls. Point the `anthropic` SDK at Guild's gateway URL — cost tracking, rate limits, audit trails with only a base URL swap.

The gateway URL is provisioned per workspace: `app.guild.ai` → **Workspace → LLM Settings**.

```python
import anthropic

client = anthropic.Anthropic(
    api_key="your-anthropic-key",        # still your own key
    base_url="https://gateway.guild.ai/ws/<your-workspace-id>/anthropic",  # from workspace settings
    default_headers={"X-Guild-Token": "<guild-api-token>"},
)
```

> **Verification needed:** the URL pattern above is inferred from Guild's architecture docs, not a published endpoint spec — confirm in your workspace's LLM settings page.

### Option B — Register Python Agent as a Custom Integration

```bash
guild integration add --name gardener-lint \
  --url https://your-gardener-host/api/lint \
  --auth bearer
```

Surfaces your Python worker as a governed callable tool in Guild's agent registry. Overkill for a purely Python-internal project.

**Hackathon recommendation:** Option A — two-line change, gives the "governed agent" story without a TypeScript rewrite.

---

## 4. Gotchas and Pricing

| Plan        | Price   | Automations/mo | Users     | Notes                          |
|-------------|---------|----------------|-----------|--------------------------------|
| Free        | $0      | 100            | 1         | Manual runs only, no triggers  |
| Individual  | $20/mo  | 1,000          | 1         | Persistent automations         |
| Team        | $200/mo | 100,000        | Unlimited | Audit logs, shared workspace   |
| Enterprise  | Custom  | Custom         | Unlimited | RBAC, SSO, 5yr audit logs      |

- **TypeScript-first.** Python projects use the LLM proxy or HTTP registration — neither documented as deeply as the native SDK path.
- **Name collision.** `pip install guildai` installs the old ML experiment tracker. The new Guild has no PyPI package.
- **Free tier is manual-only** — persistent triggers (cron, webhooks) need the $20 Individual plan.
- **Node.js 18+ needed** even for Python projects (CLI for workspace/credential management).
- **Gateway URL not publicly documented** — provision the workspace before any demo.

---

## 5. New Guild.ai vs Old guildai

| Dimension | Old guildai (pre-2025) | New Guild.ai (2026) |
|-----------|------------------------|----------------------|
| What it does | ML experiment tracking | Agent control plane: governance, credentials, audit |
| Language | Python | TypeScript SDK; language-agnostic via proxy |
| Install | `pip install guildai` | `npm install -g @guildai/cli` |
| Focus | Researchers training models | Teams deploying production agents |
| Company | Open-source (TensorLab) | Funded startup, James Everingham (ex-Meta) |

Entirely different products sharing a name.

---

## 6. Verdict

**Garnish for the hackathon, not load-bearing** — the wedge runs fine without it, and the Python proxy integration needs a gateway URL provisioned from their UI first. **However:** Guild's $2,800 prize is "Most Innovative Use of Agents" — judged on agent architecture novelty, NOT on Guild integration. The self-gardening loop itself is the entry.

---

## 7. Links (fetched June 12, 2026)

- [Homepage](https://www.guild.ai/)
- [Control Plane overview](https://www.guild.ai/controlplane)
- [Docs](https://docs.guild.ai/)
- [Quickstart](https://docs.guild.ai/quickstart)
- [Pricing](https://www.guild.ai/pricing)
- [Launch announcement](https://www.guild.ai/knowledge/news/the-control-plane-for-ai-agents-is-now-open)
- [$44M raise](https://www.guild.ai/knowledge/news/guild-raises-44m-agent-control-plane)
- [GlobeNewswire launch PR](https://www.globenewswire.com/news-release/2026/04/29/3284142/0/en/guild-ai-introduces-the-first-control-plane-for-ai-agents.html)
- [What is an AI agent control plane](https://www.guild.ai/knowledge/product/what-is-an-ai-agent-control-plane)
- [Old guildai (NOT this product)](https://github.com/guildai/guildai)
