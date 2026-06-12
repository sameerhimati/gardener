"""Pioneer GLiNER2 fine-tune pipeline — the $500 "Best Use of Pioneer" track.

We replace one general-purpose LLM call (the distiller: chat text -> JSON housing
preferences, in backend/watches/runner.distill_text) with a fine-tuned 205M GLiNER2
that extracts the same fields deterministically, on CPU, with no malformed JSON.
Memory writes are exactly where a hallucinated field hurts most.

End-to-end, reproducible. State (job IDs) lives in data/pioneer_finetune.json.

    python scripts/pioneer_finetune.py gen            # POST /generate (synthetic NER dataset)
    python scripts/pioneer_finetune.py gen-status     # poll dataset generation
    python scripts/pioneer_finetune.py train          # POST /felix/training-jobs
    python scripts/pioneer_finetune.py train-status    # poll training + show metrics
    python scripts/pioneer_finetune.py deploy <id>    # record the deployed model_id for inference
    python scripts/pioneer_finetune.py eval           # fine-tuned GLiNER vs Anthropic, side by side
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import requests

try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
except Exception:
    pass

BASE = "https://api.pioneer.ai"
STATE_PATH = Path(__file__).resolve().parents[1] / "data" / "pioneer_finetune.json"

DATASET_NAME = "gardener-housing-prefs-v1"
BASE_MODEL = "fastino/gliner2-base-v1"
MODEL_NAME = "gardener-housing-extractor-v1"
LABELS = [
    "neighborhood", "city", "min_bedrooms", "min_bathrooms",
    "min_sqft", "max_price", "property_type", "must_have_feature",
]
DOMAIN = (
    'Short first-person chat messages where a person tells an AI home-search '
    'assistant what they want in a property — e.g. "only 3+ bedrooms, at least '
    '1500 sqft, under $4000/mo in West University" or "looking for a townhouse '
    'in Houston 77005 with a garage". Casual, varied phrasing; some messages '
    'mention only one or two criteria, some several. Extract each stated '
    'criterion as the matching entity span.'
)

# Held-out eval messages — NOT in the synthetic training set. Real steering phrasing.
EVAL_MESSAGES = [
    "Actually — only show me 3+ bedrooms, 1500+ sqft minimum. Nothing smaller.",
    "Looking for a townhouse in West University under $5000 a month, needs a garage.",
    "Houston 77005, at least 2 bathrooms, and I really want a backyard.",
    "Anything condo-ish downtown is fine, budget's around 3k.",
    "Min 4 beds, 2500 square feet plus, pool would be a huge plus.",
]


def _headers() -> dict:
    key = os.environ.get("PIONEER_API_KEY")
    if not key:
        sys.exit("PIONEER_API_KEY not set (check .env)")
    return {"X-API-Key": key, "Content-Type": "application/json"}


def _state() -> dict:
    if STATE_PATH.exists():
        return json.loads(STATE_PATH.read_text())
    return {}


def _save(state: dict) -> None:
    STATE_PATH.write_text(json.dumps(state, indent=2) + "\n")


def gen() -> None:
    r = requests.post(
        f"{BASE}/generate",
        headers=_headers(),
        json={
            "task_type": "ner",
            "dataset_name": DATASET_NAME,
            "labels": LABELS,
            "num_examples": 250,
            "domain_description": DOMAIN,
        },
        timeout=60,
    )
    r.raise_for_status()
    data = r.json()
    print(json.dumps(data, indent=2))
    state = _state()
    state["dataset_job_id"] = data["job_id"]
    state["dataset_name"] = DATASET_NAME
    _save(state)


def gen_status() -> None:
    job = _state().get("dataset_job_id")
    r = requests.get(f"{BASE}/generate/jobs/{job}", headers=_headers(), timeout=30)
    data = r.json()
    print(f"status={data.get('status')} count={data.get('count')} error={data.get('error')}")


def train() -> None:
    r = requests.post(
        f"{BASE}/felix/training-jobs",
        headers=_headers(),
        json={
            "model_name": MODEL_NAME,
            "base_model": BASE_MODEL,
            "datasets": [{"name": DATASET_NAME}],
            "training_type": "lora",
            "training_algorithm": "sft",
            "nr_epochs": 5,
            "learning_rate": 5e-5,
        },
        timeout=60,
    )
    r.raise_for_status()
    data = r.json()
    print(json.dumps(data, indent=2))
    state = _state()
    state["training_job_id"] = data["id"]
    _save(state)


def train_status() -> None:
    job = _state().get("training_job_id")
    r = requests.get(f"{BASE}/felix/training-jobs/{job}", headers=_headers(), timeout=30)
    data = r.json()
    print(
        f"status={data.get('normalized_status') or data.get('status')} "
        f"epoch={data.get('current_epoch')}/{data.get('nr_epochs')} "
        f"progress={data.get('progress_percent')} "
        f"deployment={data.get('deployment_status')}"
    )
    if data.get("metrics"):
        print("metrics:", json.dumps(data["metrics"], indent=2))
    if data.get("error_message"):
        print("error:", data["error_message"])
    # The id you use for inference is the deployed model id. Record it when present.
    dep = data.get("provider_deployments") or data.get("trained_model_path")
    if dep:
        print("deployment info:", json.dumps(dep, indent=2) if isinstance(dep, (dict, list)) else dep)


def deploy(model_id: str) -> None:
    state = _state()
    state["deployed_model_id"] = model_id
    _save(state)
    print(f"recorded deployed_model_id = {model_id}")
    print("Set GLINER_MODEL_ID in .env to flip the distiller onto the fine-tune.")


def _gliner_extract(text: str, model_id: str) -> dict:
    r = requests.post(
        f"{BASE}/inference",
        headers=_headers(),
        json={"model_id": model_id, "text": text, "schema": {"entities": LABELS}, "threshold": 0.4},
        timeout=30,
    )
    return {"http": r.status_code, "body": r.json() if r.ok else r.text}


def _anthropic_distill(text: str) -> str:
    """The call we're replacing — current general-LLM distiller path."""
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from backend.agent import prompts
    from backend.core import llm

    return llm.complete(text, system=prompts.DISTILLER)


def eval_() -> None:
    model_id = _state().get("deployed_model_id")
    if not model_id:
        sys.exit("No deployed_model_id yet. Run `train-status` until deployed, then `deploy <id>`.")
    for msg in EVAL_MESSAGES:
        print("\n" + "=" * 78)
        print("MSG:", msg)
        t0 = time.time()
        g = _gliner_extract(msg, model_id)
        gt = time.time() - t0
        print(f"\n-- GLiNER2 fine-tune ({gt*1000:.0f} ms) --")
        print(json.dumps(g["body"], indent=2) if isinstance(g["body"], dict) else g["body"])
        t0 = time.time()
        a = _anthropic_distill(msg)
        at = time.time() - t0
        print(f"\n-- Anthropic distiller ({at*1000:.0f} ms) --")
        print(a)


CMDS = {
    "gen": gen, "gen-status": gen_status, "train": train,
    "train-status": train_status, "eval": eval_,
}

if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in CMDS and sys.argv[1] != "deploy":
        sys.exit(__doc__)
    if sys.argv[1] == "deploy":
        deploy(sys.argv[2])
    else:
        CMDS[sys.argv[1]]()
