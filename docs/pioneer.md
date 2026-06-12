# Pioneer (Fastino Labs) — Build-Ready Guide

## 1. What It Is

**Pioneer** (by [Fastino Labs](https://pioneer.ai/)) is an adaptive inference and fine-tuning platform for open-source small language models, launched May 2026. Its signature feature is **Adaptive Inference**: models you deploy on Pioneer are automatically and continuously retrained on their own live production traffic, with improved checkpoints validated and promoted without human intervention. You pay only for inference; the retraining loop is bundled. **This is the right Pioneer** — Fastino Labs, inference startup, hackathon sponsor, "improves with your traffic" pitch. Confidence: high (verified against official docs and the Harness hackathon Devpost page, June 12 2026).

---

## 2. Setup: Account and API Key

1. Go to [pioneer.ai](https://pioneer.ai) and create an account.
2. **Settings → API Keys** → **Create key**.
3. Name the key and **copy it immediately** — Pioneer does not store the full value after creation.
4. Store in env (never commit):
   ```bash
   export PIONEER_API_KEY="pk_..."
   ```

**Hackathon promo (Harness Engineering Hack, June 2026):** Pioneer offers a promo code for the Pro plan, which includes **$1,500 in inference credits**.

---

## 3. API for Our Use Case

### Base URL and Auth

```
Base URL: https://api.pioneer.ai/v1
Auth header: X-API-Key: <your-key>
```

Pioneer is **OpenAI-compatible** — point the OpenAI Python SDK at it, no other changes.

### Python Snippet — Chat Completion (lint agent use case)

```python
import os
from openai import OpenAI

client = OpenAI(
    api_key=os.environ["PIONEER_API_KEY"],
    base_url="https://api.pioneer.ai/v1",
)

response = client.chat.completions.create(
    model="Qwen/Qwen3-8B",          # or "meta-llama/Llama-3.1-8B", "google/gemma-3-4b", etc.
    messages=[
        {"role": "system", "content": "You are a vault lint agent. Audit the following note and return a JSON diff proposal."},
        {"role": "user",   "content": vault_note_content},
    ],
    response_format={"type": "json_object"},  # JSON mode via OpenAI-compat path
)

diff_proposal = response.choices[0].message.content
```

For structured extraction, use Pioneer's native schema endpoint via `extra_body`:

```python
response = client.chat.completions.create(
    model="job_abc123",             # a fine-tuned checkpoint ID, once you have one
    messages=[{"role": "user", "content": vault_note_content}],
    extra_body={
        "schema": {
            "structures": {
                "lint_diff": {
                    "fields": ["action", "target_file", "reason", "proposed_text"]
                }
            }
        }
    },
)
```

### Available Decoder Models (June 2026)

- `Qwen/Qwen3-8B` (and other Qwen3 sizes)
- `meta-llama/Llama-3.*` variants
- `google/gemma-3-*` variants
- `deepseek-ai/DeepSeek-*` variants
- `nvidia/Nemotron-*`
- `MoonshotAI/Kimi-K2.6`

Live catalog: `GET https://api.pioneer.ai/base-models`.

### Structured Output / JSON Mode

- **OpenAI-compat JSON mode**: `response_format={"type": "json_object"}` on decoder models.
- **Pioneer native schema**: `extra_body={"schema": {...}}` with `entities`, `classifications`, `structures`, or `relations` — encoder-optimized extraction path with F1/precision/recall metrics returned.

Both the OpenAI-compatible and Anthropic-compatible endpoints support **streaming**.

---

## 4. Gotchas, Free-Tier Limits, Pricing

| Plan | Cost | Inference Allowance | Notes |
|------|------|---------------------|-------|
| Hobby | $5/month | $30/month included | Entry tier; no downloadable weights |
| Pro | $20/user/month | $50/day, $1,500/month | Weight downloads, deep research mode |
| Enterprise | Custom | Custom (H100 fleet, BYO VPC) | 24/7 SLA |

- **No true free tier** — Hobby at $5/mo is the floor. Hackathon attendees get the Pro promo ($1,500 credits).
- **Per-token pricing not published prominently** — subscription + allowance-based. Third-party estimates: ~$0.0005–$0.005 per 1k input tokens, $0.0005–$0.025 per 1k output depending on model size.
- **Model IDs mutate**: when a new checkpoint is promoted via Adaptive Inference, your `model_id` stays the same but weights change. Pin a job ID (`job_abc123`) for a frozen baseline.
- **Evaluation is required before promotion** — improvement cycle latency is hours, not seconds.
- **Encoders vs decoders**: GLiNER encoders are for NER/classification, not generative text. For prose diffs use decoder models.

---

## 5. The "Improves With Your Traffic" Mechanism

Adaptive Inference runs five stages automatically:

1. **Observe**: Every inference call to `POST /inference` is logged.
2. **Signal capture**: Ambiguous/low-confidence traces flagged as high-signal training candidates.
3. **Curriculum + retrain**: Captured traces (+ explicit corrections POSTed to the feedback endpoint) become labeled training data → new LoRA checkpoint.
4. **Gate**: Automated evaluation against a held-out set; regressions are NOT promoted.
5. **Promote**: You review and approve; your `model_id` serves improved weights. Cycle ~weekly.

**Explicit corrections are the highest-quality signal** — POST a correction (`verdict` + `corrected_output`) referencing an `inference_id`.

**Why this rhymes with Gardener**: Gardener's thesis is "a vault that gardens itself." Pioneer's is "a model that improves itself from its own usage." Structurally identical feedback loops: observe → identify signal → retrain/update → verify → promote. Running the lint agent on Pioneer means the lint agent's own inference behavior becomes the training signal — the vault and the linter co-evolve. A genuine narrative lock, not a stretch.

---

## 6. Verdict

Pioneer is **load-bearing for the wedge** — the lint agent running on Pioneer means the agent that writes diffs improves on the diffs it writes, closing the self-improvement loop that is Gardener's core thesis.

---

## 7. Links (fetched June 12, 2026)

- [pioneer.ai — product homepage](https://pioneer.ai/)
- [docs.pioneer.ai — documentation index](https://docs.pioneer.ai/)
- [docs.pioneer.ai/concepts/inference — API formats, Python examples](https://docs.pioneer.ai/concepts/inference)
- [docs.pioneer.ai/guides/adaptive-inference — deep dive](https://docs.pioneer.ai/guides/adaptive-inference)
- [docs.pioneer.ai/authentication — API key setup](https://docs.pioneer.ai/authentication)
- [pioneer.ai/pricing — plan tiers](https://pioneer.ai/pricing)
- [pioneer.ai/blog/behind-pioneer — architecture and story](https://pioneer.ai/blog/behind-pioneer)
- [PRNewswire — Pioneer launch announcement (May 2026)](https://www.prnewswire.com/news-releases/fastino-launches-pioneer-the-first-agent-for-fine-tuning-and-inference-of-llms-302748105.html)
- [harness-hack.devpost.com — Pioneer as sponsor](https://harness-hack.devpost.com/)
