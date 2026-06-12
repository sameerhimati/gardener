"use client";

import { useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import type { Watch } from "@/lib/api";
import { relativeTime } from "@/lib/hooks";
import { ONBOARDED_KEY } from "@/components/Onboarding";

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
      }, 1700);
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

        <AnimatePresence initial={false}>
        {watches?.map((w) => (
          <motion.button
            key={w.id}
            initial={{ opacity: 0, x: -10 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: -10 }}
            transition={{ duration: 0.25, ease: "easeOut" }}
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
          </motion.button>
        ))}
        </AnimatePresence>
      </nav>

      <div className="border-t border-edge px-2 py-2">
        {/* demo affordance: clear the onboarded flag and replay the interview */}
        <button
          onClick={() => {
            localStorage.removeItem(ONBOARDED_KEY);
            window.location.reload();
          }}
          className="group/replant flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-xs text-dim transition-colors hover:bg-hover hover:text-faint"
        >
          <span aria-hidden className="text-[13px] leading-none">
            ↺
          </span>
          Replant
          <span className="ml-auto text-[10px] opacity-0 transition-opacity group-hover/replant:opacity-100">
            replay onboarding
          </span>
        </button>
        <p className="px-2 pb-1 pt-1.5 text-[11px] text-dim">
          memory that gardens itself
        </p>
      </div>
    </aside>
  );
}
