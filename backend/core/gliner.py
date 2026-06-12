"""GLiNER2 preference extractor (Pioneer), with a task-agnostic schema path.

Replaces the general-LLM distiller call for steering text. A 205M encoder
(`fastino/gliner2-base-v1`, LoRA-fine-tuned on housing NER) extracts typed spans
deterministically — no malformed JSON, no hallucinated fields, ~CPU-cheap. Memory
writes are exactly where a hallucinated field corrupts the vault, so this is the
right call to harden.

Activated only when GLINER_MODEL_ID is set; otherwise distill_text uses the LLM
path unchanged. On any error we return None so the caller falls back.

Two checkpoints exist (both from scripts/pioneer_finetune.py):
  * v1 `gardener-housing-extractor-v1` — housing-only LoRA. Pair with the
    HOUSING-GATED mode below.
  * v2 `gardener-broad-extractor-v1` — BROAD, task-agnostic LoRA trained on the
    `gardener-broad-extractor` synthetic dataset (28 labels across housing,
    stocks/crypto, travel, shopping, weather, packages, events, generic). Pair
    with TASK-AGNOSTIC mode. This is the checkpoint that fixes the "everything is
    housing" bug.

Two modes:

  * HOUSING-GATED (default): run the model ONLY on clearly housing-domain text and
    render to housing facts. Non-housing text returns None → the safe LLM
    distiller handles it. This is the proven path; safe with EITHER checkpoint.

  * TASK-AGNOSTIC (opt-in via GLINER_TASK_AGNOSTIC=1): GLiNER2 is architecturally
    zero-shot — `schema:{entities:[...]}` is supplied at inference, so the label
    SET is dynamic, not baked into weights. We detect the message's topic, pass a
    topic-appropriate label set, and render domain-correct facts (a budget for a
    GPU, a price target for a ticker, a flight number, etc.). The housing gate is
    dropped in this mode because labels are chosen per-topic.

    *** Use this mode ONLY with the v2 broad checkpoint. ***
    A *housing-only* head (v1) ignores off-domain labels like `ticker` or `flight`
    and re-emits housing-shaped spans — the exact "everything is housing" bug the
    gate was built to stop — so this mode stays OPT-IN. The v2 broad checkpoint
    was verified live against the four acceptance strings ("GPU under $500" →
    shopping/product, "SPCX crosses $165" → stocks/ticker+price_target, the
    housing string → housing, "track flight UA328" → travel/flight). To go live:
    set GLINER_MODEL_ID to the v2 model id and GLINER_TASK_AGNOSTIC=1 in .env.

Pipeline that produced the models: scripts/pioneer_finetune.py.
"""

from __future__ import annotations

import os
import re

import httpx

BASE = "https://api.pioneer.ai"

# Housing label set — what the v1 housing-only checkpoint was fine-tuned on.
HOUSING_LABELS = [
    "neighborhood", "city", "min_bedrooms", "min_bathrooms",
    "min_sqft", "max_price", "property_type", "must_have_feature",
]

# Broad label set — what the v2 task-agnostic checkpoint
# (gardener-broad-extractor-v1) is fine-tuned on. Spans every Gardener domain so
# one head extracts domain-correct entities. Names match the Pioneer dataset and
# the renderers below. Used by the task-agnostic "general" fallback so the model
# can surface any trained entity even when no specific topic rule fires.
BROAD_LABELS = [
    "neighborhood", "city", "min_bedrooms", "min_bathrooms",
    "min_sqft", "max_price", "property_type", "must_have_feature",
    "ticker", "price_target", "direction",
    "flight", "airline", "route", "date",
    "product", "brand", "budget", "condition",
    "location", "zip",
    "carrier", "tracking_id",
    "event_name", "venue",
    "preference", "constraint", "quantity",
]

# Back-compat alias for callers/tests that imported the old name.
LABELS = HOUSING_LABELS


# ── Render templates ────────────────────────────────────────────────────────
# label -> (vault topic, fact template). {v} is the extracted span; {n} is its
# digits only (for numeric criteria). Housing facts all land in one "housing"
# file so the contradiction lint can audit them against prior beliefs; the
# general labels route to topic-appropriate files.
_HOUSING_RENDER = {
    "neighborhood":      ("housing", "Prefers the {v} neighborhood"),
    "city":              ("housing", "Searching in {v}"),
    "min_bedrooms":      ("housing", "Wants at least {n} bedrooms"),
    "min_bathrooms":     ("housing", "Wants at least {n} bathrooms"),
    "min_sqft":          ("housing", "Wants at least {n} sqft"),
    "max_price":         ("housing", "Budget up to {v}"),
    "property_type":     ("housing", "Wants a {v}"),
    "must_have_feature": ("housing", "Must have: {v}"),
}

# General, topic-agnostic labels. The vault topic is chosen by the topic router
# (so a "price" in a shopping message files under shopping, in a stock message
# under stocks). Templates read correctly regardless of domain. These label names
# match the broad Pioneer dataset (gardener-broad-extractor) the model is trained
# on, so the trained head and this renderer agree on the vocabulary.
_GENERAL_RENDER = {
    # shopping
    "product":        ("{topic}", "Interested in {v}"),
    "brand":          ("{topic}", "Prefers the brand {v}"),
    "budget":         ("{topic}", "Budget up to {v}"),
    "condition":      ("{topic}", "Condition: {v}"),
    # stocks / crypto
    "ticker":         ("stocks", "Watching ticker {v}"),
    "price_target":   ("{topic}", "Price target: {v}"),
    "direction":      ("{topic}", "Trigger direction: {v}"),
    # travel
    "flight":         ("travel", "Tracking flight {v}"),
    "airline":        ("travel", "Airline: {v}"),
    "route":          ("travel", "Route: {v}"),
    # packages
    "carrier":        ("packages", "Carrier: {v}"),
    "tracking_id":    ("packages", "Tracking number {v}"),
    # events / tickets
    "event_name":     ("events", "Watching event: {v}"),
    "venue":          ("events", "Venue: {v}"),
    # weather / generic location
    "location":       ("{topic}", "Location: {v}"),
    "zip":            ("{topic}", "Area: {v}"),
    # generic
    "quantity":       ("{topic}", "Quantity: {n}"),
    "date":           ("{topic}", "Date: {v}"),
    "constraint":     ("{topic}", "Constraint: {v}"),
    "preference":     ("{topic}", "Prefers: {v}"),
}


# ── Topic router ────────────────────────────────────────────────────────────
# Picks (topic, label_set) for a message. Each topic carries the entity labels
# that are *meaningful* for it, so GLiNER is never asked to find a sqft in a
# stock message. Order matters: first matching topic wins; housing first because
# its terms are the most specific. "general" is the catch-all.
_TOPIC_RULES: list[tuple[str, list[str], list[str]]] = [
    # (topic, trigger terms, labels to request for this topic)
    ("stocks", [
        "stock", "stocks", "ticker", "shares", "share price", "nasdaq", "nyse",
        "s&p", "etf", "crosses", "calls", "puts", "earnings", "dividend",
        "market cap", "$spy", "premarket", "crypto", "bitcoin", "btc", "eth",
        "ethereum", "coin", "above ", "below ", "drops below", "hits ",
    ], ["ticker", "price_target", "direction", "constraint", "date"]),
    ("travel", [
        "flight", "flights", "airline", "departure", "arrival", "layover",
        "boarding", "gate ", "terminal", "nonstop", "round trip", "one way",
        "fare", "fares", "united", "delta", "southwest", "jetblue", "to ",
    ], ["flight", "airline", "route", "location", "date", "price_target", "constraint"]),
    ("packages", [
        "package", "tracking", "track my", "carrier", "ups", "fedex", "usps",
        "dhl", "shipment", "shipped", "delivery", "out for delivery", "parcel",
        "where is my order", "where's my order",
    ], ["carrier", "tracking_id", "date", "constraint"]),
    ("events", [
        "ticket", "tickets", "concert", "show", "game", "tour", "festival",
        "venue", "stadium", "arena", "matinee", "playing at", "live at",
    ], ["event_name", "venue", "location", "date", "price_target", "quantity", "constraint"]),
    ("weather", [
        "weather", "forecast", "rain", "snow", "temperature", "heat wave",
        "storm", "hurricane", "wind", "humidity", "uv index",
    ], ["location", "date", "constraint", "preference"]),
    ("shopping", [
        "gpu", "graphics card", "cpu", "laptop", "monitor", "ssd", "phone",
        "headphones", "keyboard", "buy", "deal", "discount", "in stock",
        "restock", "msrp", "under $", "below $", "amazon", "newegg", "best buy",
        "gb ", "tb ", "ram", "vram", "used", "refurbished", "new ",
    ], ["product", "brand", "budget", "condition", "constraint", "quantity", "preference"]),
]

# Housing terms (gate + topic trigger). Kept from the proven gate.
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

# Generic fallback labels when no topic matches (general onboarding chatter).
# The broad checkpoint is trained jointly on all domains, so when no specific
# topic fires we still offer the cross-domain non-housing labels and let the
# model pick. Housing numeric fields are intentionally excluded here — they only
# fire under the housing gate, which prevents the "everything is housing" bug.
_GENERAL_FALLBACK_LABELS = [
    "product", "brand", "budget", "condition",
    "ticker", "price_target", "direction",
    "flight", "airline", "route",
    "carrier", "tracking_id",
    "event_name", "venue",
    "location", "zip", "quantity", "date", "constraint", "preference",
]


def is_housing_text(text: str) -> bool:
    """True only when text is clearly housing-domain. Conservative gate in
    front of the housing-only extractor; non-housing text -> False -> caller
    falls back to the safe LLM distiller (housing-gated mode only)."""
    if not text:
        return False
    low = text.lower()
    if any(term in low for term in _HOUSING_TERMS):
        return True
    # token-boundary check for short words that substring-match too eagerly
    tokens = set(re.findall(r"[a-z]+", low))
    return any(w in tokens for w in _HOUSING_WORDS)


def route_topic(text: str) -> tuple[str, list[str]]:
    """Pick (topic, label_set) for task-agnostic extraction.

    Housing is detected with the proven gate; other topics by trigger terms;
    anything else falls back to a generic label set under topic "general"."""
    if is_housing_text(text):
        return "housing", HOUSING_LABELS
    low = (text or "").lower()
    for topic, terms, labels in _TOPIC_RULES:
        if any(t in low for t in terms):
            return topic, labels
    return "general", _GENERAL_FALLBACK_LABELS


def _render_for(label: str, span: str, topic: str) -> tuple[str | None, str | None]:
    """Return (vault_topic, fact) for a tagged (label, span) under `topic`.

    Housing labels render via the housing map; everything else via the general
    map (whose topic may be the routed topic or a label-fixed one like stocks)."""
    if label in _HOUSING_RENDER:
        vtopic, template = _HOUSING_RENDER[label]
    elif label in _GENERAL_RENDER:
        vtopic, template = _GENERAL_RENDER[label]
        vtopic = vtopic.format(topic=topic)
    else:
        return None, None
    digits = re.sub(r"[^\d]", "", span)
    if "{n}" in template and not digits:
        return None, None  # numeric criterion with no number — drop, don't emit garbage
    fact = template.format(v=span.strip(), n=digits, topic=topic)
    return vtopic, fact


def model_id() -> str | None:
    return os.environ.get("GLINER_MODEL_ID") or None


def available() -> bool:
    return bool(model_id() and os.environ.get("PIONEER_API_KEY"))


def task_agnostic() -> bool:
    """Opt-in switch for the dynamic-label path. Default OFF keeps the proven
    housing gate so we never ship the 'everything is housing' regression on an
    unverified checkpoint. See module docstring."""
    return os.environ.get("GLINER_TASK_AGNOSTIC", "").lower() in ("1", "true", "yes")


def _conf(d: dict) -> float:
    v = d.get("confidence", d.get("score", 1.0))
    try:
        return float(v)
    except (TypeError, ValueError):
        return 1.0


def _normalize(body: dict | list, allowed: set[str]) -> list[tuple[str, str, float, object]]:
    """Coax Pioneer's /inference response into [(label, span, score, span_key)].

    `allowed` is the label set we requested (varies by topic now), so we keep
    only labels we asked for. span_key is (start, end) offsets when present (so
    identical numbers at different positions stay distinct), else the span text.
    Real shape is result.data.entities = {label: [{text, confidence, start,
    end}]}; we also tolerate list-of-entities and bare {label: [...]} map forms."""
    if isinstance(body, dict):
        for key in ("result", "data", "entities", "predictions", "output"):
            if key in body and isinstance(body[key], (dict, list)):
                return _normalize(body[key], allowed)
        # {label: [{text,confidence,start,end}]} or {label: ["span"]} map form
        out: list[tuple[str, str, float, object]] = []
        for label, spans in body.items():
            if label not in allowed:
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
            if label in allowed and span:
                key = (e.get("start"), e.get("end")) if e.get("start") is not None else str(span)
                out.append((label, str(span), _conf(e), key))
        return out
    return []


def _suppress_overlaps(
    spans: list[tuple[str, str, float, object]],
) -> list[tuple[str, str, float, object]]:
    """Greedy span non-max suppression. A lightly-trained GLiNER tags the same
    (or overlapping) text with several labels — e.g. "$5000" as max_price 0.69
    while "5000" inside it is min_sqft 0.59. Take labels highest-confidence
    first and drop any whose character span overlaps one already kept."""
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
    return kept


def _post_inference(mid: str, text: str, labels: list[str]) -> list[tuple[str, str, float, object]]:
    r = httpx.post(
        f"{BASE}/inference",
        headers={"X-API-Key": os.environ["PIONEER_API_KEY"], "Content-Type": "application/json"},
        json={"model_id": mid, "text": text, "schema": {"entities": labels}, "threshold": 0.5},
        timeout=20,
    )
    r.raise_for_status()
    return _normalize(r.json(), set(labels))


def extract(text: str) -> list[dict] | None:
    """Return distiller-shaped [{topic, fact}] from one message, or None to
    signal the caller to fall back to the LLM distiller.

    Default mode is housing-gated (proven). With GLINER_TASK_AGNOSTIC=1 we route
    the message to a topic + label set and render domain-correct facts."""
    mid = model_id()
    if not mid:
        return None

    if task_agnostic():
        topic, labels = route_topic(text)
    else:
        # Housing-only model: only fire on clearly housing-domain text, else the
        # LLM distiller handles it. Prevents mislabeling GPU/stock/zip answers as
        # housing facts (see gate note above).
        if not is_housing_text(text):
            return None
        topic, labels = "housing", HOUSING_LABELS

    try:
        spans = _post_inference(mid, text, labels)
    except Exception as e:
        print(f"[gliner] inference failed ({e}); falling back to LLM distiller")
        return None

    kept = _suppress_overlaps(spans)

    seen, items = set(), []
    for label, span, _score, _key in kept:
        vtopic, fact = _render_for(label, span, topic)
        if not fact or not vtopic:
            continue
        dedup = (vtopic, fact)
        if dedup in seen:
            continue
        seen.add(dedup)
        items.append({"topic": vtopic, "fact": fact})
    return items
