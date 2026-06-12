# TrueFoundry AI Gateway — Build-Ready Guide (Gardener)

*Researched June 12, 2026. All claims verified against live docs.*

---

## 1. What It Is

TrueFoundry's AI Gateway is a hosted (SaaS or self-hosted) proxy layer that sits between your application and upstream LLM providers — Anthropic, OpenAI, Bedrock, Vertex, 250+ models total — under a single endpoint and key. It exposes an OpenAI-compatible `/chat/completions` surface **and** a native Anthropic `/messages` surface, adding unified cost tracking, request logging, rate/budget limits, and automatic fallbacks with ~10 ms added latency. As of mid-2026 it has expanded to include an MCP Gateway and Agent Gateway layer on top of the core LLM Gateway.

---

## 2. Setup

### 2a. Account

1. Go to [signup.truefoundry.com](https://signup.truefoundry.com) — no credit card required.
2. Verify email → TrueFoundry dashboard.
3. **Developer tier is free**: 50,000 requests/month, logs, traces, playground.

### 2b. Register an Anthropic Provider Account

1. Dashboard → **AI Gateway** → **Providers** → **Add Provider Account**.
2. Select **Anthropic**, enter your Anthropic API key, name it (e.g., `anthropic-main`).
3. The gateway exposes your Claude models as `anthropic-main/<model-id>`:
   - `anthropic-main/claude-sonnet-4-20250514`
   - `anthropic-main/claude-haiku-4-20250514`
   - `anthropic-main/claude-opus-4-20250514`

   *(Use the Playground's **Code Snippets** tab to copy the exact model string.)*

### 2c. Get Your Gateway Key

Dashboard → **Access** → **Create Token**: **PAT** for local dev, **VAT** for production apps.

**SaaS Base URL:** `https://gateway.truefoundry.ai`

---

## 3. API — Python Snippets

### 3a. Native Anthropic SDK (recommended for the agent loop)

```python
import os
from anthropic import Anthropic

GATEWAY_URL = "https://gateway.truefoundry.ai"
TFY_KEY = os.environ["TRUEFOUNDRY_API_KEY"]

client = Anthropic(
    api_key=TFY_KEY,
    base_url=GATEWAY_URL,
    default_headers={"Authorization": f"Bearer {TFY_KEY}"},
)

response = client.messages.create(
    model="anthropic-main/claude-sonnet-4-20250514",
    max_tokens=4096,
    system="You are Gardener, a personal memory agent...",
    messages=[{"role": "user", "content": "What did I learn last week?"}],
    tools=[
        {
            "name": "search_vault",
            "description": "Search the markdown vault",
            "input_schema": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
        }
    ],
)
```

`tools`, `tool_choice`, `tool_result` blocks, extended thinking, prompt caching, streaming — all pass through natively (`/messages` is a transparent proxy).

### 3b. OpenAI-compat surface

```python
from openai import OpenAI

client = OpenAI(api_key=TFY_KEY, base_url=GATEWAY_URL)

response = client.chat.completions.create(
    model="anthropic-main/claude-haiku-4-20250514",
    messages=[{"role": "user", "content": "Audit this vault note..."}],
    tools=[...],  # OpenAI tool format — gateway translates
)
```

### 3c. Tracing You Get for Free (Developer tier)

- Every request logged: model, tokens in/out, latency, cost in USD, timestamp.
- Dashboard: per-model cost breakdown, request volume, error rates. No code changes.
- `X-TFY-LOGGING-CONFIG` header to tag requests with metadata (e.g., `{"agent": "lint-worker"}`).

---

## 4. Gotchas, Limits, Latency, Pricing

| Item | Detail |
|---|---|
| **Free tier** | 50,000 req/month, 5 MCP servers, 10 saved prompts, community support. No fallbacks, no advanced routing, no budget alerts on free. |
| **Pro** | $499/month, 1M req/month, fallbacks, multi-endpoint, alerts. |
| **Latency overhead** | ~10 ms published (3–4 ms in some benchmarks). |
| **Prompt caching** | Passes through — min prefix 1024 tokens (Sonnet/Opus), 2048 (Haiku). |
| **Tool use** | Native passthrough on `/messages`; OpenAI-compat endpoint translates automatically. |
| **Model naming** | Must use `provider-account/model-id` format, not bare Anthropic IDs. |
| **Structured outputs** | JSON schema works; Anthropic-unsupported numeric constraints silently dropped — validate schemas. |
| **Fallbacks** | Only on Pro+. On free, overloaded errors propagate to caller. |
| **Self-hosted** | ~$600–$1,000/month infra. Not needed for us. |

---

## 5. What Changed Since Early 2025

- **Native Anthropic SDK support** (`/messages` endpoint) added — previously OpenAI-compat only.
- **Agent Gateway** and **MCP Gateway** launched alongside the core LLM Gateway.
- **Claude Fable 5** added to model catalogue on launch day (June 2026).
- Gartner Hype Cycle for Platform Engineering 2026 recognition.
- Developer (free) tier formalized with explicit 50K req/month cap.

---

## 6. Verdict

Garnish, not load-bearing — the gateway adds unified cost visibility and a single key across agent + lint worker (genuinely useful for a two-agent system), but Gardener's core wedge works identically direct-to-Anthropic; the free tier covers hackathon throughput, and adopting it later is a one-line `base_url` change. **Sameer's note (session close): the agent↔LLM routing layer with fallbacks is conceptually interesting beyond the hackathon — revisit.**

---

## 7. Links (fetched June 12, 2026)

- [TrueFoundry AI Gateway product page](https://www.truefoundry.com/ai-gateway)
- [Quick Start Guide](https://www.truefoundry.com/docs/ai-gateway/quick-start)
- [Anthropic integration docs](https://www.truefoundry.com/docs/ai-gateway/anthropic)
- [Native SDK Support docs](https://www.truefoundry.com/docs/ai-gateway/native-sdk-support)
- [Making LLM Requests via Gateway](https://www.truefoundry.com/docs/ai-gateway/making-llm-requests-via-gateway)
- [Proxy API docs](https://www.truefoundry.com/docs/ai-gateway/proxy-api)
- [Pricing page](https://www.truefoundry.com/pricing)
- [Cost tracking Claude Code blog post](https://www.truefoundry.com/blog/cost-tracking-claude-code-with-truefoundrys-ai-gateway)
- [AI Gateways in 2026 comparison](https://www.truefoundry.com/blog/a-definitive-guide-to-ai-gateways-in-2026-competitive-landscape-comparison)
