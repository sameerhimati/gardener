# Agent Framework Decision Memo — Gardener
_June 12, 2026 · researched live against current docs_

---

## 1. The Field as of June 2026

| Framework | Lang | Version | Status |
|---|---|---|---|
| **Pydantic AI** | Python | v1.107.0 (Jun 10, 2026) | Active, stable, FastAPI-first |
| **LangGraph** | Python | v1.2.0 | Active, mature, graph-based |
| **Vercel AI SDK** | TypeScript | v6.0.203 | Active, UI-first, RSC/streaming native |
| **Mastra** | TypeScript | v1.42.0 | Active, opinionated full-stack |
| **Claude Agent SDK** | Python/TS | current | Beta managed-agent surface, Anthropic-hosted |
| **OpenAI Agents SDK** | Python | current | Works with Claude via LiteLLM; gotchas |
| **Raw Anthropic SDK loop** | Python/TS | current | ~80 lines, zero deps, manual hooks |
| **Composio** | cross | v0.13.1 (May 14, 2026) | First-class adapters for all major frameworks |

---

## 2. Top 3 Deep-Dive

### 2a. Pydantic AI (recommended)

**Hook story** — `Hooks` fires at every lifecycle event. ClickHouse writer is trivial:

```python
from pydantic_ai import Agent
from pydantic_ai.hooks import Hooks
import clickhouse_connect, time

ch = clickhouse_connect.get_client(...)
hooks = Hooks()

@hooks.on.wrap_model_request
async def log_turn(ctx, *, request_context, handler):
    t0 = time.time()
    response = await handler(request_context)
    ch.insert('events', [['model_turn', ctx.run_id, time.time()-t0, str(response)]])
    return response

@hooks.on.wrap_tool_execute
async def log_tool(ctx, *, call, tool_def, handler):
    t0 = time.time()
    result = await handler(call)
    ch.insert('events', [['tool_call', ctx.run_id, time.time()-t0, tool_def.name, str(call.args)]])
    return result

# Vault tool
from pydantic_ai import tool
@tool
async def write_vault(path: str, content: str) -> str:
    (vault / path).write_text(content)
    return f"wrote {path}"

# Agent
from composio_pydanticai import ComposioToolSet
composio_tools = ComposioToolSet().get_tools(actions=['GMAIL_SEND_EMAIL', 'GOOGLECALENDAR_CREATE_EVENT'])
agent = Agent('anthropic:claude-opus-4-8', tools=[write_vault, *composio_tools], capabilities=[hooks])

# FastAPI streaming — one line
from pydantic_ai.ext.fastapi import VercelAIAdapter

@app.post('/chat')
async def chat(request: Request) -> Response:
    return await VercelAIAdapter.dispatch_request(request, agent=agent)
```

**Time-to-working estimate**: 2–4 hours (chat endpoint + streaming + Composio + ClickHouse hook)

**Background lint agent**: second `Agent` instance with same `Hooks`, run via `asyncio.create_task` or APScheduler. No separate process needed.

---

### 2b. LangGraph

**Hook story** — `wrap_tool_call` and `wrap_model_call` middleware. Solid but more boilerplate:

```python
from langgraph.middleware import Middleware
from langchain_anthropic import ChatAnthropic

class CHLogger(Middleware):
    async def wrap_model_call(self, request, handler):
        t0 = time.time()
        response = await handler(request)
        ch.insert('events', [['model_turn', time.time()-t0]])
        return response

    async def wrap_tool_call(self, request, handler):
        t0 = time.time()
        result = await handler(request)
        ch.insert('events', [['tool_call', request.tool_name, time.time()-t0]])
        return result

from composio_langgraph import ComposioToolSet
tools = ComposioToolSet().get_tools(actions=['GMAIL_SEND_EMAIL'])
agent = create_react_agent(ChatAnthropic(model="claude-opus-4-8"), tools, middleware=[CHLogger()])

# Streaming to FastAPI
async def stream_chat(message: str):
    async for chunk in agent.astream({"messages": [HumanMessage(message)]}):
        yield f"data: {json.dumps(chunk)}\n\n"
```

**Time-to-working estimate**: 4–7 hours (middleware wiring, SSE plumbing from scratch)

---

### 2c. Vercel AI SDK

**Hook story** — `prepareStep` + `onStepFinish` per step; tool interception requires wrapping each `execute` function — indirect, not a middleware that catches everything:

```ts
import { anthropic } from '@ai-sdk/anthropic';
import { VercelProvider } from '@composio/vercel';
import { streamText } from 'ai';

const composio = new Composio({ provider: new VercelProvider() });
const tools = await session.tools(); // Vercel-native format

const result = streamText({
  model: anthropic('claude-opus-4-8'),
  tools,
  onStepFinish: async ({ usage, finishReason, toolCalls }) => {
    await ch.insert({ table: 'events', values: [{ type: 'step', tool_calls: toolCalls }] });
  },
  // no single hook for tool execute — must wrap each tool.execute individually
  messages,
});
```

**Time-to-working estimate**: 3–5 hours for Next.js; if FastAPI backend is required, adds complexity (separate TS server or Next.js Route Handler).

---

## 3. Recommendation

**Pydantic AI (Python)**

**Reason 1 — Hookability is first-class, not bolted on.** `wrap_model_request` and `wrap_tool_execute` fire on every event in the loop. The ClickHouse writer is 10 lines of decorator code. LangGraph's middleware is comparable but requires subclassing; Vercel AI SDK requires wrapping each tool's `execute` individually, which breaks if Composio tools are auto-generated.

**Reason 2 — Fastest path to a working chat endpoint.** `VercelAIAdapter.dispatch_request` gives streaming to any web UI in one line. `composio-pydanticai` is a first-class adapter (not MCP-bridged). FastAPI is the explicit design reference for the framework. Background lint agent is a second `Agent` instance — no new infra.

**What we give up:** LangGraph's durable execution / checkpointing (irrelevant here — no long-running graph state needed). Mastra's built-in memory/thread management (can add manually with a SQLite table). Vercel AI SDK's native Next.js RSC streaming (not blocking — `VercelAIAdapter` implements the same Data Stream Protocol).

---

## 4. Fallback

If Pydantic AI fights us for >2 hours (e.g., Composio adapter breakage, hooks not firing on streamed responses):

**Raw Anthropic SDK loop (~80 lines, zero deps)**

```python
async def agent_loop(messages, tools):
    while True:
        response = await client.messages.create(model="claude-opus-4-8", tools=tools, messages=messages, stream=True)
        # yield stream chunks to UI
        ch.insert('events', [['model_turn', response.usage]])  # hook here
        if response.stop_reason == 'tool_use':
            for block in response.content:
                if block.type == 'tool_use':
                    ch.insert('events', [['tool_call', block.name, str(block.input)]])  # hook here
                    result = await dispatch_tool(block.name, block.input)
                    messages.append({"role": "tool", "content": result})
        else:
            break
```

Composio tools work with raw SDK (pass tool schemas directly from `ComposioToolSet().get_tools()`). No middleware needed — every hook point is explicit. Downside: streaming SSE plumbing is manual (~30 more lines).

---

## 5. Links

All URLs fetched June 12, 2026:

- Pydantic AI Hooks: https://ai.pydantic.dev/hooks/
- Pydantic AI FastAPI integration: https://ai.pydantic.dev/api/ext/fastapi/
- Pydantic AI Anthropic: https://ai.pydantic.dev/models/anthropic/
- Composio Python adapters: https://docs.composio.dev/tools/frameworks/pydantic-ai
- Composio changelog v0.13.1: https://github.com/composiohq/composio/releases/tag/v0.13.1
- LangGraph middleware: https://langchain-ai.github.io/langgraph/concepts/middleware/
- Vercel AI SDK `onStepFinish`: https://sdk.vercel.ai/docs/reference/ai-sdk-core/stream-text
- Mastra Processors: https://mastra.ai/en/docs/agents/processors
- Anthropic SDK streaming: https://docs.anthropic.com/en/api/streaming
