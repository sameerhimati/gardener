# Pioneer GLiNER2 — what's done & how to show it

> Demo-facing cheat sheet for the $500 "Best Use of Pioneer" track.
> Full build log + reproducible pipeline: `docs/pioneer-finetune.md`, `scripts/pioneer_finetune.py`.

## What it is (one line)
We replaced the distiller's **general-LLM call** — the one that turns steering chat into
preference facts and **writes them to the memory vault** — with a **fine-tuned 205M GLiNER2**
encoder. Deterministic spans, ~15× faster, structurally incapable of malformed JSON on a
memory write.

## Status: ✅ built, trained, deployed, wired
- Base: `fastino/gliner2-base-v1` (205M encoder — **not** an LLM, not Qwen).
- Trained on Pioneer (Modal GPU), LoRA, 5 epochs, on a 250-example synthetic NER set we
  generated *from our own housing domain*. Best validation loss 3.04 → **2.72**.
- Deployed model_id: `fd96007f-690f-4044-b36a-e3a5bdf65723` (shows as
  `gardener-housing-extractor-v1 · Deployed` in the Pioneer playground).
- Wired into `backend/watches/runner.distill_text` via `backend/core/gliner.py`, gated on
  `GLINER_MODEL_ID`. Anthropic/Qwen distiller stays as automatic fallback on any miss.

**To turn it on:** add `GLINER_MODEL_ID=fd96007f-690f-4044-b36a-e3a5bdf65723` to `.env`.
The model is housing-only by design; off-domain text (e.g. "what's the weather") correctly
extracts nothing and falls back to the LLM.

## The numbers (held-out steering messages)
| | General-LLM distiller (Qwen3-8B via Pioneer) | GLiNER2 fine-tune |
|---|---|---|
| Latency | ~2030 ms | **~135 ms** (≈15×) |
| Output | generative JSON (can malform) | deterministic typed spans |
| Size | 8B | **205M**, CPU-capable |

Real eval — `Actually — only show me 3+ bedrooms, 1500+ sqft minimum in West University.`
→ `Wants at least 3 bedrooms` · `Wants at least 1500 sqft` · `Searching in West University`.

## How to show it (don't tour the playground)
The model is **invisible in the product flow** — it looks like any extractor. Make it visible:

1. **Main beat — narrate the latency over the live vault-write.** When you steer the watch
   and the facts plant, say:
   > "That landed in ~100 ms — and it's not an LLM. It's a 205M model we fine-tuned on
   > Pioneer this morning. Memory is the one place you can't afford a hallucinated field,
   > so the writer is deterministic and 15× faster than a frontier call."

2. **Receipt — 3-second flash** of the Pioneer **Inferences** dashboard in the closing
   montage (deployed model · real inferences · ~102 ms latency column). Not a tour.

3. **Kicker (verbal / Devpost):**
   > "Gardener is a vault that gardens itself. We built the extractor on Pioneer — a
   > platform whose models improve from their own traffic. The thing guarding the
   > self-maintaining memory is itself self-improving. Same loop, all the way down."

## Notes for the main agent
- The fine-tuned model only does **housing** extraction. Feed it housing steering text.
- The `pioneer/auto` **router** is unrelated — a cost-routing feature we deliberately don't
  use (we call our specific model by id). Ignore it.
- Pioneer playground default example is CRISPR researchers — paste a housing line or it
  looks broken.
