# Pioneer fine-tune plan — next-session parallel task ($500 "Best Use" track)

> Captured 2026-06-12 from the design-session discussion + Pioneer's data-generation docs
> (https://docs.pioneer.ai/llms.txt → /generate endpoints). NOT for today's demo — wedge first.

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
