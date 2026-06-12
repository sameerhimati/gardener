"use client";

/**
 * "Gardener is thinking" — three soft moss dots pulsing in sequence.
 * Shared by the chat pane and onboarding while a reply is in flight.
 */
export default function ThinkingDots({ label }: { label?: string }) {
  return (
    <span className="inline-flex items-center gap-2">
      <span className="inline-flex items-center gap-1" aria-hidden>
        {[0, 1, 2].map((i) => (
          <span
            key={i}
            className="animate-thinking-dot h-1.5 w-1.5 rounded-full bg-moss/70"
            style={{ animationDelay: `${i * 180}ms` }}
          />
        ))}
      </span>
      <span className="text-xs text-dim">{label ?? "Gardener is thinking"}</span>
    </span>
  );
}
