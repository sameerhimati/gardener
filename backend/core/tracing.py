"""Langfuse tracing — zero-touch global instrumentation of the Anthropic SDK.

Calling `init()` once at process startup patches `anthropic.Anthropic` globally
(via the OpenTelemetry Anthropic instrumentor), so EVERY `client.messages.create`
call in the codebase — the agent loop, core.llm, the lint worker — is traced into
Langfuse with model + token + cost metadata, WITHOUT editing any call site.

This is the LLM-call observability layer. It is separate from core.events
(our own ClickHouse/JSONL event log), which stays as-is.

Graceful degradation is the whole contract here: if the Langfuse keys are absent,
or the SDK isn't installed, or anything throws, init() silently no-ops and the app
runs on ANTHROPIC_API_KEY alone. Tracing must never crash the product.

Init is idempotent (safe to call from both the FastAPI startup and the worker
entrypoint, even in the same process). flush() drains the queue before a
short-lived process exits — without it, the cron lint worker would drop traces.
"""

from __future__ import annotations

import os

_enabled = False  # True once instrumentation is live; gates flush()
_initialized = False  # ensures init() only ever runs its body once


def configured() -> bool:
    """Both Langfuse keys present in env → tracing is intended."""
    return bool(os.environ.get("LANGFUSE_PUBLIC_KEY") and os.environ.get("LANGFUSE_SECRET_KEY"))


def init() -> bool:
    """Initialize Langfuse + globally instrument the Anthropic SDK. Idempotent.

    Returns True if tracing is live, False if it no-oped (missing keys / SDK /
    any error). Never raises.
    """
    global _enabled, _initialized
    if _initialized:
        return _enabled
    _initialized = True

    if not configured():
        print("[tracing] Langfuse keys not set — LLM tracing disabled (app runs normally)")
        return False

    # Langfuse v4 reads LANGFUSE_BASE_URL; some setups still use LANGFUSE_HOST.
    # Normalize so either env var works, defaulting to the US cloud region.
    base_url = os.environ.get("LANGFUSE_BASE_URL") or os.environ.get("LANGFUSE_HOST")
    if base_url:
        os.environ.setdefault("LANGFUSE_HOST", base_url)
        os.environ.setdefault("LANGFUSE_BASE_URL", base_url)
    else:
        os.environ.setdefault("LANGFUSE_BASE_URL", "https://us.cloud.langfuse.com")
        os.environ.setdefault("LANGFUSE_HOST", "https://us.cloud.langfuse.com")

    try:
        from langfuse import get_client
        from opentelemetry.instrumentation.anthropic import AnthropicInstrumentor

        # get_client() builds the singleton from env (keys + base url) and wires
        # the OTEL exporter that ships spans to Langfuse.
        client = get_client()
        # Patches the Anthropic SDK process-wide. Idempotent in practice, but the
        # _initialized guard already prevents a second call.
        AnthropicInstrumentor().instrument()
        _enabled = True

        # auth_check is a network round-trip; treat failure as non-fatal so a bad
        # key or offline box never blocks startup — we just won't see traces.
        try:
            if client.auth_check():
                print(f"[tracing] Langfuse tracing live ({os.environ['LANGFUSE_BASE_URL']})")
            else:
                print("[tracing] Langfuse auth_check failed — check keys; instrumentation still active")
        except Exception as e:  # noqa: BLE001
            print(f"[tracing] Langfuse auth_check skipped ({e}); instrumentation still active")
        return True
    except Exception as e:  # noqa: BLE001
        print(f"[tracing] Langfuse init failed ({e}) — LLM tracing disabled (app runs normally)")
        _enabled = False
        return False


def flush() -> None:
    """Drain the trace queue. MUST be called before a short-lived process exits
    (e.g. the cron lint worker), or buffered traces are silently dropped.
    No-ops and never raises if tracing isn't enabled."""
    if not _enabled:
        return
    try:
        from langfuse import get_client

        get_client().flush()
    except Exception as e:  # noqa: BLE001
        print(f"[tracing] flush failed ({e})")
