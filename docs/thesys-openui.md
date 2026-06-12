# Thesys C1 & OpenUI — Build-Ready Guide

*Researched against live docs, June 12 2026.*

---

## 1. What It Is

**C1** (by Thesys) is a generative-UI middleware API: you call it exactly like the OpenAI chat-completions endpoint, but instead of returning markdown it returns a streaming XML-like DSL that a thin React SDK (`@thesysai/genui-sdk`) renders as interactive components — charts, forms, cards, tables. C1 is not itself an LLM; it proxies your request to a backing model (Claude Sonnet 4 or GPT-5) and augments the output with UI spec. **OpenUI** is a separate, MIT-licensed open spec + runtime (published March 2026) that Thesys open-sourced — it ships its own compact line-oriented language (`@openuidev/react-lang`) that is 67% more token-efficient than JSON and usable without any Thesys account.

---

## 2. Setup

### Account & API Key

1. Free account at [console.thesys.dev](https://console.thesys.dev)
2. Generate an API key under **API Keys**
3. `THESYS_API_KEY=<key>` in env

### Scaffold (Next.js — fastest path)

```bash
npx create-c1-app          # requires Node ≥ 20.9
cd my-app && npm run dev   # → http://localhost:3000
```

### Manual install into an existing Next.js project

```bash
npm install @thesysai/genui-sdk @crayonai/react-core @crayonai/react-ui @crayonai/stream openai
```

Versions from the official template (June 2026): `@thesysai/genui-sdk ^0.8.3`, `@crayonai/react-core ^0.7.6`, `@crayonai/react-ui ^0.9.8`, `@crayonai/stream ^0.6.4`, `openai ^4.91.1`, `next 15.2.8`.

---

## 3. Integration Pattern

```
Browser → POST /api/chat (your Next.js route)
              ↓
         OpenAI client (baseURL = api.thesys.dev/v1/embed/)
              ↓
         C1 proxies to Claude Sonnet 4 or GPT-5
              ↓
         Streams C1 DSL (XML-like spec)
              ↓
Browser ← ReadableStream  →  <C1Component> renders live UI
```

**You never call the LLM directly when using C1** — C1 owns the LLM call and injects UI-generation instructions. Select the backing model via the model string.

### Backend: `src/app/api/chat/route.ts`

```typescript
import { NextRequest, NextResponse } from "next/server";
import OpenAI from "openai";
import { transformStream } from "@crayonai/stream";

const client = new OpenAI({
  baseURL: "https://api.thesys.dev/v1/embed/",
  apiKey: process.env.THESYS_API_KEY,
});

export async function POST(req: NextRequest) {
  const { prompt, threadId, responseId } = await req.json();
  const messageStore = getMessageStore(threadId);
  messageStore.addMessage(prompt);

  const llmStream = await client.chat.completions.create({
    model: "c1/anthropic/claude-sonnet-4/v-20251230",
    // or "c1/openai/gpt-5/v-20251130"
    messages: messageStore.getOpenAICompatibleMessageList(),
    stream: true,
  });

  const responseStream = transformStream(
    llmStream,
    (chunk) => chunk.choices?.[0]?.delta?.content ?? "",
    {
      onEnd: ({ accumulated }) => {
        messageStore.addMessage({
          role: "assistant",
          content: accumulated.filter(Boolean).join(""),
          id: responseId,
        });
      },
    }
  ) as ReadableStream<string>;

  return new NextResponse(responseStream, {
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache, no-transform",
      Connection: "keep-alive",
    },
  });
}
```

### Frontend: drop-in chat

```tsx
import { C1Chat } from "@thesysai/genui-sdk";

export default function Page() {
  return <C1Chat apiUrl="/api/chat" theme={{ mode: "dark" }} />;
}
```

### Custom component + actions round-trip

Register a custom component via Zod schema in `metadata`:

```typescript
import { z } from "zod";
import { zodToJsonSchema } from "zod-to-json-schema";

const GymProgressSchema = z.object({
  workouts: z.array(z.object({
    date: z.string(),
    lift: z.string(),
    weight: z.number(),
    reps: z.number(),
  })).describe("Array of workout entries to chart"),
});

const llmStream = await client.chat.completions.create({
  model: "c1/anthropic/claude-sonnet-4/v-20251230",
  messages: [...],
  stream: true,
  // @ts-ignore – thesys metadata extension
  metadata: {
    thesys: JSON.stringify({
      c1_custom_components: {
        GymProgressChart: zodToJsonSchema(GymProgressSchema),
      },
    }),
  },
});
```

React side with action hook:

```tsx
import { useOnAction } from "@thesysai/genui-sdk";

export const GymProgressChart = ({ workouts }) => {
  const onAction = useOnAction();
  return (
    <div>
      {/* chart */}
      <button onClick={() =>
        onAction(
          "Log new set",                              // humanFriendlyMessage
          `User wants to log a new workout entry`     // llmFriendlyMessage → fed back to your LLM
        )
      }>
        + Log Set
      </button>
    </div>
  );
};
```

```tsx
<C1Chat apiUrl="/api/chat" customComponents={{ GymProgressChart }} />
```

**Actions round-trip**: `onAction` fires → `continue_conversation` event → `llmFriendlyMessage` appended to conversation → back to your `/api/chat` route → C1 generates next UI.

---

## 4. Gotchas

**LLM lock-in**: C1 owns the LLM call. You cannot route to your own Claude client with your own system prompt — C1 injects its own prompt to produce UI spec. Models limited to what C1 exposes (`c1/anthropic/claude-sonnet-4`, `c1/openai/gpt-5`). No custom `anthropic-beta` headers, no extended thinking. **For Gardener's core agent loop this is a non-trivial constraint — display layer only.**

**Styling**: Crayon design system. `theme` prop + custom components, but you can't fully override Crayon primitives — visual seam vs Tailwind/shadcn UI without theming work.

**Free tier**: 3,000 C1 API calls/month (≈100/day), data used for training. $49/month Build tier → 25K calls. Latency is double-hop: add ~100–200ms to Claude's TTFT.

**Streaming format**: Streaming XML DSL (`<thinking>`, `<content>`, `<artifact>` tags), not plain text. Bypassing C1 to call Claude directly renders nothing — `<C1Component>` requires the C1 DSL.

**`messageStore` is in-memory by default** in the template — wire your own persistence.

---

## 5. What Changed Since Early 2025

- **Model strings changed**: `"c1-nightly"` still valid but canonical strings are provider-qualified: `"c1/anthropic/claude-sonnet-4/v-20251230"`.
- **OpenUI launched (March 2026)**: open-source spec (`@openuidev/*`) — generative UI without the managed endpoint. MIT, BYO-LLM-friendly, not production-proven yet.
- **Supported models**: Claude Sonnet 4 and GPT-5 (earlier versions only exposed GPT-4-class).
- **FastAPI template** now exists: `git clone https://github.com/thesysdev/template-c1-fastapi`.
- **Crayon packages split**: `@crayonai/react-core`, `@crayonai/react-ui`, `@crayonai/stream` — old monolithic `@crayonai/react` import no longer works.

---

## 6. Verdict

**Garnish, not load-bearing** — C1 is a fast demo win for micro-app moments, but the LLM-ownership constraint means you cannot run your own agent loop (event writing, vault diffs, lint worker) through it — you'd maintain two AI call paths with a seam at the rendering layer. OpenUI's `@openuidev/react-lang` is the lower-lock-in alternative worth evaluating as it matures. ($2,000 OpenUI prize exists — weigh against integration cost.)

---

## 7. Links (fetched June 12 2026)

- [Thesys homepage](https://www.thesys.dev/)
- [C1 docs — What is C1](https://docs.thesys.dev/guides/what-is-thesys-c1)
- [C1 docs — How C1 Works](https://docs.thesys.dev/guides/how-c1-works)
- [C1 docs — Quickstart / Setup](https://docs.thesys.dev/guides/setup)
- [C1 docs — Actions / Interactivity](https://docs.thesys.dev/guides/interactivity/actions)
- [C1 docs — Custom Components](https://docs.thesys.dev/guides/custom-components)
- [Thesys Pricing](https://www.thesys.dev/pricing)
- [OpenUI GitHub (thesysdev/openui)](https://github.com/thesysdev/openui)
- [OpenUI Lang overview](https://www.openui.com/docs/openui-lang/overview)
- [template-c1-next](https://github.com/thesysdev/template-c1-next)
- [Dev.to: Thesys React SDK walkthrough](https://dev.to/anmolbaranwal/thesys-react-sdk-turn-llm-responses-into-real-time-user-interfaces-30d5)
- [InfoWorld: Thesys launches C1 API](https://www.infoworld.com/article/3971182/thesys-introduces-generative-ui-api-for-building-ai-apps.html)
