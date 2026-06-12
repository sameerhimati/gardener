"""Plain sync LLM completions — used by the lint worker and the distiller.

Routes to Pioneer (OpenAI-compatible) when PIONEER_API_KEY is set, else the
Anthropic API. The agent loop does NOT use this — it talks to Anthropic
directly because it needs tool use.
"""

import os

DEFAULT_ANTHROPIC_MODEL = "claude-sonnet-4-6"
DEFAULT_PIONEER_MODEL = "Qwen/Qwen3-8B"
DEFAULT_PIONEER_BASE_URL = "https://api.pioneer.ai/v1"


def complete(prompt: str, system: str = "", model: str | None = None) -> str:
    if os.environ.get("PIONEER_API_KEY"):
        return _complete_pioneer(prompt, system, model)
    return _complete_anthropic(prompt, system, model)


def _complete_pioneer(prompt: str, system: str, model: str | None) -> str:
    from openai import OpenAI

    api_key = os.environ["PIONEER_API_KEY"]
    client = OpenAI(
        api_key=api_key,
        base_url=os.environ.get("PIONEER_BASE_URL", DEFAULT_PIONEER_BASE_URL),
        default_headers={"X-API-Key": api_key},  # Pioneer's documented auth header
    )
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    response = client.chat.completions.create(
        model=model or os.environ.get("PIONEER_MODEL", DEFAULT_PIONEER_MODEL),
        messages=messages,
    )
    return response.choices[0].message.content or ""


def _complete_anthropic(prompt: str, system: str, model: str | None) -> str:
    import anthropic

    client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from env
    kwargs = {"system": system} if system else {}
    response = client.messages.create(
        model=model or os.environ.get("MODEL", DEFAULT_ANTHROPIC_MODEL),
        max_tokens=2048,
        messages=[{"role": "user", "content": prompt}],
        **kwargs,
    )
    return "".join(block.text for block in response.content if block.type == "text")
