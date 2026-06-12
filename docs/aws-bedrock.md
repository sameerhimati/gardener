# AWS Bedrock for Claude — Build-Ready Guide

_Verified against live AWS and Anthropic docs, June 12, 2026._
_**Status for this project: CUT** (Sameer: not a requirement; confirmed garnish). Kept for reference._

---

## 1. What It Is

Amazon Bedrock is a managed inference API that hosts Anthropic's Claude models on AWS infrastructure, billed through your AWS account. For Gardener it would be a fallback `llm()` path — same Messages API shape, different client object and credential chain.

---

## 2. Setup

### 2a. AWS Account
Sign up at <https://portal.aws.amazon.com/billing/signup>.

### 2b. Model Access Enablement — the hackathon killer

Model access is **per-region, per-model**, explicit opt-in:

1. [AWS Console > Bedrock > Model Access](https://console.aws.amazon.com/bedrock/home?region=us-east-1#/modelaccess) — open access in `us-east-1` first (widest coverage).
2. **Modify model access** → check Claude models → accept Anthropic's terms per model → submit.
3. Verify status shows **Access granted** before running code. Missing access = `AccessDeniedException` at inference time, not client construction.

Common failure modes: wrong region; forgot to accept terms (separate checkbox); Claude Fable 5 requires an additional data-retention opt-in (§4); Claude Mythos Preview is invitation-only.

### 2c. Credentials

Hackathon-fast path — long-term API key (bearer token):
```bash
# AWS Console > Bedrock > API Keys > Create long-term API key
export AWS_BEARER_TOKEN_BEDROCK="<your key>"
export AWS_REGION="us-east-1"
```

IAM keys:
```bash
export AWS_ACCESS_KEY_ID="AKIA..."
export AWS_SECRET_ACCESS_KEY="..."
export AWS_REGION="us-east-1"
```

---

## 3. SDK Choice and Code

| | `AnthropicBedrockMantle` | `AnthropicBedrock` (legacy) | boto3 `converse()` |
|---|---|---|---|
| API shape | Identical to `anthropic.Anthropic` | Identical | AWS-native dict/JSON |
| Models | All current (Fable 5, Opus 4.8…) | Legacy only (Opus 4.6, Sonnet 4.6, Haiku 4.5) | All |
| Swappable with `Anthropic()` | Yes — same `.messages.create()` | Yes | No |
| Endpoint | `bedrock-mantle.{region}.api.aws` | `bedrock-runtime.{region}.amazonaws.com` | bedrock-runtime |

**Recommendation: `AnthropicBedrockMantle`** — current endpoint, all models, identical call signature.

```bash
pip install -U "anthropic[bedrock]"
```

### The swappable `llm()` abstraction

```python
import os
from anthropic import Anthropic, AnthropicBedrockMantle

def make_client():
    """Prefer direct API; fall back to Bedrock."""
    if os.getenv("ANTHROPIC_API_KEY"):
        return Anthropic()
    return AnthropicBedrockMantle(aws_region=os.getenv("AWS_REGION", "us-east-1"))

CLIENT = make_client()
DIRECT_MODEL  = "claude-opus-4-8"
BEDROCK_MODEL = "anthropic.claude-opus-4-8"  # bedrock uses anthropic. prefix

def llm(messages: list[dict], tools: list[dict] | None = None, **kwargs):
    model = BEDROCK_MODEL if isinstance(CLIENT, AnthropicBedrockMantle) else DIRECT_MODEL
    return CLIENT.messages.create(
        model=model,
        max_tokens=kwargs.pop("max_tokens", 4096),
        messages=messages,
        tools=tools or [],
        **kwargs,
    )
```

Tool use works identically to the direct API (tool_use blocks, tool_result follow-ups).

### Current model IDs (June 2026)

| Model | Bedrock ID | Context | Notes |
|---|---|---|---|
| Claude Fable 5 | `anthropic.claude-fable-5` | 1M | Requires `provider_data_share` opt-in |
| Claude Opus 4.8 | `anthropic.claude-opus-4-8` | 1M | Best for agent loop |
| Claude Opus 4.7 | `anthropic.claude-opus-4-7` | 1M | bedrock-mantle only |
| Claude Haiku 4.5 | `anthropic.claude-haiku-4-5-20251001-v1:0` | 200k | Fast/cheap for lint worker |
| Claude Sonnet 4.6 | `anthropic.claude-sonnet-4-6` | 1M | Legacy endpoint |

**Cross-region prefixes** (prepend to model ID): `global.` (no premium, recommended) · `us.` / `eu.` / `jp.` (10% premium geo routing).

---

## 4. Gotchas

- Model access per-region; Fable 5 In-Region only from `us-east-1`/`eu-north-1` (else use `global.`).
- **Fable 5 data retention**: must set `data_retention_mode: provider_data_share` via the Data Retention API before inference succeeds. Not required for Opus 4.8.
- **Tokenizer change**: Fable 5 and Opus 4.7+ produce ~30% more tokens for the same text vs pre-4.7 models.
- Quotas: 2M input TPM default (4M without Anthropic approval). RPM via AWS support.
- Pricing: same per-token rates as direct API on standard tier; CRIS endpoints +10%; prompt caching supported (5-min/1-hour TTLs).
- **Not on Bedrock**: Files API, URL image sources, server-side tools (web search, code exec), Message Batches API, Models API, server-side fallbacks.

---

## 5. What Changed Since Early 2025

- **Bedrock Mantle endpoint** launched mid-2025 — full Messages API w/ SSE streaming; legacy `AnthropicBedrock` path now "legacy."
- **Claude Fable 5** (June 9, 2026) — first Mythos-class model on Bedrock; `temperature` must be 1.0/unset; `top_k` unsupported.
- **Global/geo prefix system** replaced cross-region inference profile ARNs.
- **Sonnet 4 / Opus 4 deprecated**, retiring June 15, 2026.
- **Bearer token auth** (`AWS_BEARER_TOKEN_BEDROCK`) added — good for hackathons.

---

## 6. Verdict

**Garnish — and CUT for this project.** The wedge works identically on direct Anthropic API; Bedrock adds credential overhead with no capability gain at hackathon scale. Wire in as a one-line client swap only if ever needed.

---

## 7. Links (fetched June 12, 2026)

- [Claude in Amazon Bedrock (current)](https://platform.claude.com/docs/en/build-with-claude/claude-in-amazon-bedrock)
- [Claude on Amazon Bedrock (legacy)](https://platform.claude.com/docs/en/build-with-claude/claude-on-amazon-bedrock-legacy)
- [Models overview with Bedrock IDs](https://platform.claude.com/docs/en/about-claude/models/overview)
- [Claude Fable 5 model card on AWS](https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-anthropic-claude-fable-5.html)
- [Supported foundation models](https://docs.aws.amazon.com/bedrock/latest/userguide/models-supported.html)
- [Converse API tool use examples](https://docs.aws.amazon.com/bedrock/latest/userguide/tool-use-examples.html)
- [Bedrock pricing](https://aws.amazon.com/bedrock/pricing/)
