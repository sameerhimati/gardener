"""Pioneer GLiNER2 fine-tune pipeline — the $500 "Best Use of Pioneer" track.

We replace one general-purpose LLM call (the distiller: chat text -> JSON
preferences, in backend/watches/runner.distill_text) with a fine-tuned 205M GLiNER2
that extracts the same fields deterministically, on CPU, with no malformed JSON.
Memory writes are exactly where a hallucinated field hurts most.

v1 (gardener-housing-prefs-v1) was housing-only, so it mislabeled everything else
as housing (a GPU "$500" became "500 sqft"). v2 (gardener-broad-extractor) is a
BROAD, task-agnostic dataset spanning every domain Gardener watches care about —
housing, stocks/crypto, travel, shopping, weather, packages, events/tickets, plus
generic preference/constraint — so one GLiNER2 head extracts domain-correct spans
across all of them. The label names match backend/core/gliner.py's task-agnostic
renderer (_GENERAL_RENDER / route_topic) so wiring the trained model in is a flip.

End-to-end, reproducible. State (job IDs) lives in data/pioneer_finetune.json.

    python scripts/pioneer_finetune.py gen            # POST /generate (broad synthetic NER dataset)
    python scripts/pioneer_finetune.py gen-status     # poll dataset generation
    python scripts/pioneer_finetune.py train          # POST /felix/training-jobs
    python scripts/pioneer_finetune.py train-status    # poll training + show metrics
    python scripts/pioneer_finetune.py deploy <id>    # record the deployed model_id for inference
    python scripts/pioneer_finetune.py eval           # fine-tuned GLiNER vs Anthropic, side by side

Add `housing` as an extra arg to gen/train to target the legacy housing-only
config instead of the broad one (e.g. `gen housing`).
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

BASE_MODEL = "fastino/gliner2-base-v1"

# ── Legacy housing-only config (v1) — kept for reference / reproduction. ──────
HOUSING_DATASET_NAME = "gardener-housing-prefs-v1"
HOUSING_MODEL_NAME = "gardener-housing-extractor-v1"
HOUSING_LABELS = [
    "neighborhood", "city", "min_bedrooms", "min_bathrooms",
    "min_sqft", "max_price", "property_type", "must_have_feature",
]
HOUSING_DOMAIN = (
    'Short first-person chat messages where a person tells an AI home-search '
    'assistant what they want in a property — e.g. "only 3+ bedrooms, at least '
    '1500 sqft, under $4000/mo in West University" or "looking for a townhouse '
    'in Houston 77005 with a garage". Casual, varied phrasing; some messages '
    'mention only one or two criteria, some several. Extract each stated '
    'criterion as the matching entity span.'
)

# ── BROAD task-agnostic config (v2) — the demo deliverable. ───────────────────
# Label names match backend/core/gliner.py: HOUSING_LABELS + _GENERAL_RENDER keys
# (product, brand, budget, price_target, ticker, direction, flight, airline,
# route, location, zip, carrier, tracking_id, event_name, venue, quantity, date,
# constraint, preference). One head, every Gardener domain, domain-correct spans.
DATASET_NAME = "gardener-broad-extractor"
MODEL_NAME = "gardener-broad-extractor-v1"
BROAD_LABELS = [
    # housing
    "neighborhood", "city", "min_bedrooms", "min_bathrooms",
    "min_sqft", "max_price", "property_type", "must_have_feature",
    # stocks / crypto
    "ticker", "price_target", "direction",
    # travel
    "flight", "airline", "route", "date",
    # shopping
    "product", "brand", "budget", "condition",
    # weather / location
    "location", "zip",
    # packages
    "carrier", "tracking_id",
    # events / tickets
    "event_name", "venue",
    # generic
    "preference", "constraint", "quantity",
]
LABELS = BROAD_LABELS  # back-compat for any importer
BROAD_DOMAIN = (
    "Short first-person chat messages where a person tells an AI personal-watch "
    "assistant what to monitor across MANY domains. Examples span: HOUSING "
    "(\"3+ bedrooms, 1500+ sqft under $4000/mo in West University 77005, needs a "
    "garage\"); STOCKS/CRYPTO (\"ping me if SPCX crosses $165\", \"watch NVDA, "
    "alert me when it drops below 800\", \"BTC above 70k\"); TRAVEL (\"track "
    "flight UA328\", \"United SFO to JFK on March 3\", \"alert me on fare drops "
    "LAX-NRT\"); SHOPPING (\"GPU under $500\", \"used RTX 4090, MSI or ASUS, in "
    "stock\", \"a quiet mechanical keyboard below $120\"); WEATHER (\"rain in "
    "Austin this weekend\"); PACKAGES (\"track UPS 1Z999, where is my order\", "
    "\"FedEx tracking 7712 3344\"); EVENTS/TICKETS (\"Taylor Swift at SoFi "
    "Stadium\", \"tickets for the Warriors game June 14\"). Casual, varied "
    "phrasing; some messages state one criterion, some several. Extract each "
    "stated item as the matching entity span: ticker symbols as `ticker`, a "
    "price level like \"$165\" or \"800\" as `price_target`, \"above/below/"
    "crosses/drops\" as `direction`; flight numbers as `flight`, airlines as "
    "`airline`, \"SFO to JFK\" as `route`; the thing being shopped as `product`, "
    "its maker as `brand`, a spend cap as `budget`, \"used/new/refurbished\" as "
    "`condition`; a city/area as `location`, a 5-digit zip as `zip`; shipping "
    "carriers (UPS/FedEx/USPS/DHL) as `carrier`, a tracking number as "
    "`tracking_id`; an event/artist/team as `event_name`, a venue as `venue`; "
    "any date as `date`, a count as `quantity`, and free-form likes/dislikes as "
    "`preference` or hard limits as `constraint`. Housing keeps its dedicated "
    "fields (neighborhood, city, min_bedrooms, min_bathrooms, min_sqft, "
    "max_price, property_type, must_have_feature)."
)

# Held-out eval messages — NOT in the synthetic training set. Real steering
# phrasing across domains; includes the four acceptance strings from the brief.
EVAL_MESSAGES = [
    "GPU under $500",
    "Ping me if SPCX crosses $165",
    "houses in 77005, 3+ bd, 1500+ sqft",
    "track flight UA328",
    "Looking for a used RTX 4090, MSI or ASUS, in stock under $1800.",
    "Watch NVDA and alert me if it drops below 800.",
    "Where's my UPS package, tracking 1Z999AA10123456784?",
    "Taylor Swift tickets at SoFi Stadium for June 14.",
]


def _cfg(which: str | None) -> tuple[str, str, list[str], str]:
    """(dataset_name, model_name, labels, domain) for 'housing' or broad (default)."""
    if which == "housing":
        return HOUSING_DATASET_NAME, HOUSING_MODEL_NAME, HOUSING_LABELS, HOUSING_DOMAIN
    return DATASET_NAME, MODEL_NAME, BROAD_LABELS, BROAD_DOMAIN


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


def gen(which: str | None = None) -> None:
    dataset_name, _model, labels, domain = _cfg(which)
    # Broad dataset needs more examples to cover ~8 domains credibly; housing 250.
    num_examples = 250 if which == "housing" else 600
    r = requests.post(
        f"{BASE}/generate",
        headers=_headers(),
        json={
            "task_type": "ner",
            "dataset_name": dataset_name,
            "labels": labels,
            "num_examples": num_examples,
            "domain_description": domain,
        },
        timeout=60,
    )
    r.raise_for_status()
    data = r.json()
    print(json.dumps(data, indent=2))
    state = _state()
    state["dataset_job_id"] = data["job_id"]
    state["dataset_name"] = dataset_name
    state["labels"] = labels
    _save(state)


def gen_status() -> None:
    job = _state().get("dataset_job_id")
    r = requests.get(f"{BASE}/generate/jobs/{job}", headers=_headers(), timeout=30)
    data = r.json()
    print(f"status={data.get('status')} count={data.get('count')} error={data.get('error')}")


def train(which: str | None = None) -> None:
    dataset_name, model_name, labels, _domain = _cfg(which)
    r = requests.post(
        f"{BASE}/felix/training-jobs",
        headers=_headers(),
        json={
            "model_name": model_name,
            "base_model": BASE_MODEL,
            "datasets": [{"name": dataset_name}],
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
    state["model_name"] = model_name
    state["labels"] = labels
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
    labels = _state().get("labels") or LABELS
    r = requests.post(
        f"{BASE}/inference",
        headers=_headers(),
        json={"model_id": model_id, "text": text, "schema": {"entities": labels}, "threshold": 0.4},
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
    elif sys.argv[1] in ("gen", "train"):
        # optional 2nd arg selects the legacy housing config; default is broad.
        CMDS[sys.argv[1]](sys.argv[2] if len(sys.argv) > 2 else None)
    else:
        CMDS[sys.argv[1]]()
