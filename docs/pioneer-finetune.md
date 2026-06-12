# Pioneer fine-tune — $500 "Best Use" track

> Captured 2026-06-12 from the design-session discussion + Pioneer's data-generation docs.
> **SHIPPED 2026-06-12 — see "## SHIPPED" at the bottom for what was actually built
> (real API shapes + results). The plan below is preserved for context.**

---

## SHIPPED — fine-tuned GLiNER2 housing-preference extractor

**What it replaces:** the distiller's general-LLM call (`backend/watches/runner.distill_text`
→ `core/llm.complete`) that turns steering chat into `{topic, fact}` preferences and writes
them to the memory vault. That call occasionally hallucinated fields/malformed JSON — and
this is a *memory write*, the worst place for that.

**The model:** `fastino/gliner2-base-v1` (205M encoder) fine-tuned via LoRA on a synthetic
NER dataset we generated from our own domain. Trained on Pioneer (Modal `g4dn.xlarge`),
5 epochs, 20% held-out validation. Best validation loss **3.04 → 2.72**.

**Pipeline (all reproducible — `scripts/pioneer_finetune.py`):**
1. `POST https://api.pioneer.ai/generate` `task_type:"ner"`, 250 synthetic examples,
   labels `[neighborhood, city, min_bedrooms, min_bathrooms, min_sqft, max_price,
   property_type, must_have_feature]`. Poll `GET /generate/jobs/:id` → `ready`.
2. `POST https://api.pioneer.ai/felix/training-jobs` (`training_type:"lora"`, `nr_epochs:5`,
   `learning_rate:5e-5`). Poll `GET /felix/training-jobs/:id` → `complete`.
3. Inference: `POST https://api.pioneer.ai/inference` with `model_id` = the training job
   UUID, `schema:{entities:[...labels]}`, `threshold:0.5`. Response is
   `result.data.entities = {label: [{text, confidence, start, end}]}`.
4. Wired into `distill_text` via `backend/core/gliner.py`, gated on `GLINER_MODEL_ID`;
   Anthropic distiller stays as automatic fallback on any miss/error.

**Real IDs (state mirror in gitignored `data/pioneer_finetune.json`):**
- dataset job: `f4dbf8b2-416d-403a-9db5-b31c6cbb4146` (`gardener-housing-prefs-v1`)
- training job / inference `model_id`: **`fd96007f-690f-4044-b36a-e3a5bdf65723`**
- **To go live:** add `GLINER_MODEL_ID=fd96007f-690f-4044-b36a-e3a5bdf65723` to `.env`.

**Results vs the Anthropic call (held-out steering messages):**
- Latency: GLiNER **~135 ms** model compute vs Anthropic **~2030 ms** — **~15× faster**.
- Deterministic structured output; zero malformed-JSON risk on memory writes.
- A lightly-trained GLiNER leaks overlapping labels (e.g. `$5000`→max_price *and* `5000`
  →min_sqft); we resolve it with greedy span **non-max suppression** in `gliner.py`
  (keep highest-confidence label, drop overlapping spans). After NMS, eval set is clean
  and off-domain text ("what's the weather") correctly extracts nothing.

**On-thesis kicker for the writeup:** Pioneer's Adaptive Inference ("a model that improves
from its own traffic") rhymes exactly with Gardener's thesis ("a vault that gardens itself").
Same loop — observe → signal → retrain → gate → promote.

---

## Original plan (context)

## The idea

Replace one general-LLM call in Gardener's pipeline with a fine-tuned **GLiNER2**
(`fastino/gliner2-base-v1`, 205M) — deterministic, fast, no hallucinated JSON. The Pioneer
prize track explicitly wants a fine-tuned model replacing a general LLM call; our current
OpenAI-compatible inference wiring (core/llm.py) is the weak/fallback use — keep it as fallback.

Two candidate targets, pick ONE:

1. **Preference extraction in the distiller** (`watches/runner.distill_text`):
   steering text → structured JSON preferences. GLiNER2 does JSON extraction + NER natively.
2. **Contradiction classification in the lint worker**: (new_pref, existing_pref) →
   {contradicts, refines, unrelated} as text classification. (The full lint rule still needs
   an LLM for the corrected-file rewrite; GLiNER2 would be the cheap pre-filter that decides
   WHICH pairs to send to the big model.)

Account status: **Pro plan already redeemed** (promo `SFJune2026Tokens`), key in `.env`.

## Path (≈ 20 min of API calls + a few hundred examples)

1. **Synthetic dataset from our own domain** — `POST https://api.pioneer.ai/generate`
   (X-API-Key auth), e.g. for target 2:
   ```json
   {
     "task_type": "classification",
     "dataset_name": "gardener-contradictions",
     "labels": ["contradicts", "refines", "unrelated"],
     "num_examples": 300,
     "domain_description": "Pairs of personal-preference statements from an AI assistant's memory vault (housing criteria, shopping constraints, schedules). Decide whether the second statement contradicts, refines, or is unrelated to the first.",
     "prompt": "Format each input as 'EXISTING: <belief> || NEW: <statement>'."
   }
   ```
   Async: poll `GET /generate/jobs/:job_id` until `"complete"`.
2. **Bonus realism:** auto-label REAL steering text from our event log via
   `POST /generate/classification/label-existing` (`labels` + `inputs`, ≤1,000 strings,
   synchronous; rate limit 120 req/min). We have thousands of real `user_msg`/`watch_steer`
   payloads in ClickHouse/data/events.jsonl to draw from.
3. **Train:** `POST /felix/training-jobs` with
   `{"model_name": "gardener-contradiction-clf", "base_model": "fastino/gliner2-base-v1",
   "datasets": [{"name": "gardener-contradictions"}], "training_type": "lora",
   "nr_epochs": 5, "learning_rate": 5e-5}`.
4. **Eval** against the current Anthropic call on a held-out set; if it wins on
   accuracy/latency, **wire the deployed model in via the existing Pioneer client** in
   `core/llm.py` (one routing branch), Anthropic stays as fallback.
5. On-thesis kicker for the writeup: Pioneer's **Adaptive Inference** generates training
   data from live traffic — "a model that improves as you use it" rhymes exactly with
   Gardener's memory thesis. Name that in the submission.

## Why this fits the judging

- Pioneer "$500 Best Use" wants a fine-tune replacing a general LLM call — this is literally that.
- Trained on data shaped by OUR product's event log (not a toy dataset).
- Deterministic structured output where hallucination hurts most (memory writes).
