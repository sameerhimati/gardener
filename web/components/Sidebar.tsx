"use client";

import { useEffect, useRef, useState } from "react";
import type { Watch } from "@/lib/api";
import { relativeTime } from "@/lib/hooks";

interface SidebarProps {
  watches: Watch[] | null;
  selected: string; // "main" or a watch id
  onSelect: (id: string) => void;
}

function statusColor(status: string): string {
  switch (status) {
    case "active":
    case "running":
      return "bg-moss";
    case "paused":
    case "stopped":
      return "bg-dim";
    case "error":
    case "failed":
      return "bg-rust";
    default:
      return "bg-moss-deep";
  }
}

export default function Sidebar({ watches, selected, onSelect }: SidebarProps) {
  // Pulse a watch's status dot when its last_run changes between polls —
  // a cycle just ran.
  const prevRuns = useRef<Map<string, string | null>>(new Map());
  const [pulsing, setPulsing] = useState<Set<string>>(new Set());

  useEffect(() => {
    if (!watches) return;
    const changed: string[] = [];
    for (const w of watches) {
      const prev = prevRuns.current.get(w.id);
      if (prev !== undefined && prev !== w.last_run && w.last_run) {
        changed.push(w.id);
      }
      prevRuns.current.set(w.id, w.last_run);
    }
    if (changed.length > 0) {
      setPulsing((cur) => new Set([...cur, ...changed]));
      const timer = setTimeout(() => {
        setPulsing((cur) => {
          const next = new Set(cur);
          changed.forEach((id) => next.delete(id));
          return next;
        });
      }, 4500);
      return () => clearTimeout(timer);
    }
  }, [watches]);

  return (
    <aside className="flex w-60 shrink-0 flex-col border-r border-edge bg-surface">
      {/* wordmark */}
      <div className="flex items-center gap-2 px-4 pb-5 pt-5">
        <span className="h-2 w-2 rounded-full bg-moss" aria-hidden />
        <span className="text-[15px] font-semibold tracking-tight text-ink">
          Gardener
        </span>
      </div>

      {/* main chat */}
      <nav className="flex min-h-0 flex-1 flex-col gap-1 overflow-y-auto px-2 pb-4">
        <button
          onClick={() => onSelect("main")}
          className={`rounded-md px-3 py-2 text-left text-sm transition-colors ${
            selected === "main"
              ? "bg-raised text-ink"
              : "text-faint hover:bg-hover hover:text-ink"
          }`}
        >
          Main chat
        </button>

        {/* watches */}
        <div className="mt-5 px-3 pb-1.5 text-[11px] font-medium uppercase tracking-[0.14em] text-dim">
          Watches
        </div>

        {watches === null && (
          <div className="px-3 py-1 text-xs text-dim">…</div>
        )}

        {watches !== null && watches.length === 0 && (
          <p className="px-3 py-1 text-xs leading-relaxed text-dim">
            No watches yet — ask Gardener to keep an eye on something.
          </p>
        )}

        {watches?.map((w) => (
          <button
            key={w.id}
            onClick={() => onSelect(w.id)}
            className={`group rounded-md px-3 py-2 text-left transition-colors ${
              selected === w.id
                ? "bg-raised"
                : "hover:bg-hover"
            }`}
          >
            <span className="flex items-start gap-2">
              <span
                className={`mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full ${statusColor(
                  w.status,
                )} ${pulsing.has(w.id) ? "animate-cycle-pulse" : ""}`}
                title={w.status}
              />
              <span className="min-w-0">
                <span
                  className={`block truncate text-sm ${
                    selected === w.id ? "text-ink" : "text-faint group-hover:text-ink"
                  }`}
                >
                  {w.task}
                </span>
                <span className="block text-[11px] text-dim">
                  {relativeTime(w.last_run)}
                </span>
              </span>
            </span>
          </button>
        ))}
      </nav>

      <div className="border-t border-edge px-4 py-3 text-[11px] text-dim">
        memory that gardens itself
      </div>
    </aside>
  );
}
