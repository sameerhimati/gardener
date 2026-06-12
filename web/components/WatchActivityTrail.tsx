"use client";

import { motion } from "framer-motion";
import { getWatchEvents, type WatchEvent } from "@/lib/api";
import { usePolling } from "@/lib/hooks";

function parseInput(raw: unknown): Record<string, unknown> {
  if (typeof raw === "string") {
    try {
      return JSON.parse(raw);
    } catch {
      return {};
    }
  }
  return (raw as Record<string, unknown>) ?? {};
}

function hostname(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
}

interface Step {
  icon: string;
  text: string;
  url?: string;
}

function describe(ev: WatchEvent): Step | null {
  if (ev.kind === "tool_call") {
    const name = ev.payload.name as string;
    const input = parseInput(ev.payload.input);
    if (name === "web_search")
      return { icon: "🔍", text: `searched “${input.query ?? ""}”` };
    if (name === "web_fetch") {
      const url = String(input.url ?? "");
      return { icon: "🌐", text: `fetched ${hostname(url)}`, url };
    }
    return { icon: "⚙", text: name };
  }
  if (ev.kind === "watch_cycle") {
    const s = ((ev.payload.summary as string) || "").trim();
    if (!s || s.toLowerCase() === "no change")
      return { icon: "·", text: "checked — no change" };
    return { icon: "✓", text: s };
  }
  return null; // tool_result omitted — the call + cycle summary tell the story
}

export default function WatchActivityTrail({ watchId }: { watchId: string }) {
  const { data } = usePolling<WatchEvent[]>(
    () => getWatchEvents(watchId),
    3000,
    watchId,
  );

  // endpoint is newest-first; show oldest→newest as a chronological trail
  const steps = (data ?? [])
    .map(describe)
    .filter((s): s is Step => s !== null)
    .reverse()
    .slice(-10);

  if (steps.length === 0) return null;

  return (
    <div className="shrink-0 border-b border-edge bg-surface px-5 py-3">
      <div className="mx-auto max-w-3xl">
        <p className="mb-2 text-[11px] font-medium uppercase tracking-wide text-dim">
          What this worker did on the web
        </p>
        <ol className="flex flex-col gap-1.5">
          {steps.map((s, i) => (
            <motion.li
              key={i}
              initial={{ opacity: 0, x: -4 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ duration: 0.2, delay: i * 0.02 }}
              className="flex items-start gap-2 text-xs leading-relaxed text-faint"
            >
              <span className="select-none" aria-hidden>
                {s.icon}
              </span>
              {s.url ? (
                <a
                  href={s.url}
                  target="_blank"
                  rel="noreferrer"
                  className="text-moss-deep underline decoration-moss/30 underline-offset-2 hover:decoration-moss"
                >
                  {s.text}
                </a>
              ) : (
                <span className="min-w-0 break-words">{s.text}</span>
              )}
            </motion.li>
          ))}
        </ol>
      </div>
    </div>
  );
}
