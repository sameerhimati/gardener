"""Fine-tuned GLiNER2 housing-preference extractor (Pioneer).

Replaces the general-LLM distiller call for housing steering text. A 205M
encoder fine-tune that extracts typed spans deterministically — no malformed
JSON, no hallucinated fields, ~CPU-cheap. Memory writes are exactly where a
hallucinated field corrupts the vault, so this is the right call to harden.

Activated only when GLINER_MODEL_ID is set; otherwise distill_text uses the
LLM path unchanged. On any error we return None so the caller falls back.

Pipeline that produced the model: scripts/pioneer_finetune.py.
"""

from __future__ import annotations

import os
import re

import httpx

BASE = "https://api.pioneer.ai"
LABELS = [
    "neighborhood", "city", "min_bedrooms", "min_bathrooms",
    "min_sqft", "max_price", "property_type", "must_have_feature",
]

# label -> (vault topic, fact template). {v} is the extracted span; {n} is its
# digits only (for numeric criteria). All housing criteria land in one file so
# the contradiction lint can audit them against prior beliefs.
_RENDER = {
    "neighborhood":     ("housing", "Prefers the {v} neighborhood"),
    "city":             ("housing", "Searching in {v}"),
    "min_bedrooms":     ("housing", "Wants at least {n} bedrooms"),
    "min_bathrooms":    ("housing", "Wants at least {n} bathrooms"),
    "min_sqft":         ("housing", "Wants at least {n} sqft"),
    "max_price":        ("housing", "Budget up to {v}"),
    "property_type":    ("housing", "Wants a {v}"),
    "must_have_feature": ("housing", "Must have: {v}"),
}


# Housing-domain gate. This model is HOUSING-ONLY — every label renders to the
# "housing" topic — but distill_text feeds it ALL onboarding/steering text. Run
# it on non-housing text and it mislabels: GPU "$500" -> "Budget up to $500",
# stock "165" -> "Wants at least 165 sqft", bare zip "94115" -> a neighborhood.
# So we only fire when the text is clearly housing-domain; otherwise return None
# and let the general LLM distiller handle it. Precision over recall: when in
# doubt, gate OUT (return None) — the LLM path is the safe default.
_HOUSING_TERMS = (
    "house", "home", "homes", "housing", "bedroom", "bed ", "beds",
    "bathroom", "bath ", "baths", "sqft", "sq ft", "square feet", "square foot",
    "neighborhood", "neighbourhood", "zillow", "redfin", "trulia", "realtor",
    "apartment", "condo", "townhouse", "townhome", "duplex", "rent", "rental",
    "lease", "mortgage", "hoa", "listing", "realty", "real estate", "property",
    "zip code", "zipcode", "zip ", "postal code", "studio", "loft",
    "move in", "move-in", "for sale", "open house", "broker", "landlord",
)
# Word-ish patterns where a bare substring would false-match (e.g. "bed" in
# "embedding"). Matched on token boundaries instead.
_HOUSING_WORDS = (
    "bed", "beds", "bath", "baths", "house", "home", "homes", "rent",
    "lease", "condo", "loft", "studio", "zip", "zipcode", "hoa",
)


def is_housing_text(text: str) -> bool:
    """True only when text is clearly housing-domain. Conservative gate in
    front of the housing-only extractor; non-housing text -> False -> caller
    falls back to the safe LLM distiller."""
    if not text:
        return False
    low = text.lower()
    if any(term in low for term in _HOUSING_TERMS):
        return True
    # token-boundary check for short words that substring-match too eagerly
    tokens = set(re.findall(r"[a-z]+", low))
    return any(w in tokens for w in _HOUSING_WORDS)


def model_id() -> str | None:
    return os.environ.get("GLINER_MODEL_ID") or None


def available() -> bool:
    return bool(model_id() and os.environ.get("PIONEER_API_KEY"))


def _conf(d: dict) -> float:
    v = d.get("confidence", d.get("score", 1.0))
    try:
        return float(v)
    except (TypeError, ValueError):
        return 1.0


def _normalize(body: dict | list) -> list[tuple[str, str, float, object]]:
    """Coax Pioneer's /inference response into [(label, span, score, span_key)].

    span_key is (start, end) offsets when present (so identical numbers at
    different positions stay distinct), else the span text. Real shape is
    result.data.entities = {label: [{text, confidence, start, end}]}; we also
    tolerate list-of-entities and bare {label: [...]} map forms."""
    if isinstance(body, dict):
        for key in ("result", "data", "entities", "predictions", "output"):
            if key in body and isinstance(body[key], (dict, list)):
                return _normalize(body[key])
        # {label: [{text,confidence,start,end}]} or {label: ["span"]} map form
        out: list[tuple[str, str, float, object]] = []
        for label, spans in body.items():
            if label not in LABELS:
                continue
            for s in spans if isinstance(spans, list) else [spans]:
                if isinstance(s, dict):
                    text = str(s.get("text") or s.get("span") or s.get("value") or "")
                    key = (s.get("start"), s.get("end")) if s.get("start") is not None else text
                    out.append((label, text, _conf(s), key))
                else:
                    out.append((label, str(s), 1.0, str(s)))
        return out
    if isinstance(body, list):
        out = []
        for e in body:
            if not isinstance(e, dict):
                continue
            label = e.get("label") or e.get("entity") or e.get("type")
            span = e.get("text") or e.get("span") or e.get("value")
            if label in LABELS and span:
                key = (e.get("start"), e.get("end")) if e.get("start") is not None else str(span)
                out.append((label, str(span), _conf(e), key))
        return out
    return []


def _render(label: str, span: str) -> str | None:
    topic, template = _RENDER.get(label, (None, None))
    if not template:
        return None
    digits = re.sub(r"[^\d]", "", span)
    if "{n}" in template and not digits:
        return None  # numeric criterion with no number — drop rather than emit garbage
    return template.format(v=span.strip(), n=digits)


def extract(text: str) -> list[dict] | None:
    """Return distiller-shaped [{topic, fact}] from one message, or None to
    signal the caller to fall back to the LLM distiller."""
    mid = model_id()
    if not mid:
        return None
    # Housing-only model: only fire on clearly housing-domain text, else the
    # LLM distiller handles it. Prevents mislabeling GPU/stock/zip answers as
    # housing facts (see _HOUSING_TERMS note above).
    if not is_housing_text(text):
        return None
    try:
        r = httpx.post(
            f"{BASE}/inference",
            headers={"X-API-Key": os.environ["PIONEER_API_KEY"], "Content-Type": "application/json"},
            json={"model_id": mid, "text": text, "schema": {"entities": LABELS}, "threshold": 0.5},
            timeout=20,
        )
        r.raise_for_status()
        spans = _normalize(r.json())
    except Exception as e:
        print(f"[gliner] inference failed ({e}); falling back to LLM distiller")
        return None

    # A lightly-trained GLiNER tags the same (or overlapping) text with several
    # labels — e.g. "$5000" as max_price 0.69 while "5000" inside it is min_sqft
    # 0.59. Greedy span non-max suppression: take labels highest-confidence
    # first and drop any whose character span overlaps one already kept.
    kept: list[tuple[str, str, float, object]] = []
    for label, span, score, key in sorted(spans, key=lambda x: x[2], reverse=True):
        if isinstance(key, tuple) and key[0] is not None:
            s, e = key
            if any(
                isinstance(k, tuple) and k[0] is not None and s < k[1] and k[0] < e
                for *_x, k in kept
            ):
                continue
        kept.append((label, span, score, key))

    seen, items = set(), []
    for label, span, _score, _key in kept:
        fact = _render(label, span)
        topic = _RENDER.get(label, (None,))[0]
        if not fact or not topic:
            continue
        dedup = (topic, fact)
        if dedup in seen:
            continue
        seen.add(dedup)
        items.append({"topic": topic, "fact": fact})
    return items
