"use client";

import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { createWatch } from "@/lib/api";
import {
  IDEAS_PERSONAL,
  IDEAS_GENERAL,
  ZIP_KEY,
  type Idea,
} from "@/lib/ideas";

/**
 * Ideas / watch picker — a permanent home for the onboarding chips.
 *
 * Tapping an idea spawns a standing watch via POST /watches (the same path
 * Onboarding seeds through). Location ideas thread the user's zip (remembered
 * in localStorage) so "near me" means their place. Onboarding is one-time; this
 * panel is the always-available way to add more watches later.
 */
export default function IdeasPanel() {
  const [zip, setZip] = useState("");
  const [editingZip, setEditingZip] = useState(false);
  // Per-idea status so a tap gives immediate, calm feedback.
  const [spawning, setSpawning] = useState<Set<string>>(new Set());
  const [spawned, setSpawned] = useState<Set<string>>(new Set());

  // Restore the remembered zip on mount (set during a prior session or here).
  useEffect(() => {
    try {
      const z = localStorage.getItem(ZIP_KEY);
      if (z) setZip(z);
    } catch {
      // localStorage unavailable — fine, ideas just use generic phrasing.
    }
  }, []);

  function saveZip(next: string) {
    const clean = next.replace(/[^0-9]/g, "").slice(0, 5);
    setZip(clean);
    try {
      if (clean) localStorage.setItem(ZIP_KEY, clean);
      else localStorage.removeItem(ZIP_KEY);
    } catch {
      // ignore — purely a convenience cache
    }
  }

  async function spawn(idea: Idea) {
    if (spawning.has(idea.label)) return;
    setSpawning((s) => new Set(s).add(idea.label));
    try {
      await createWatch(idea.prompt(zip.trim()));
      setSpawned((s) => new Set(s).add(idea.label));
      // Let the "added" confirmation fade after a beat so the idea is reusable.
      setTimeout(() => {
        setSpawned((s) => {
          const next = new Set(s);
          next.delete(idea.label);
          return next;
        });
      }, 2200);
    } catch {
      // fail soft — the offline banner already signals backend trouble
    } finally {
      setSpawning((s) => {
        const next = new Set(s);
        next.delete(idea.label);
        return next;
      });
    }
  }

  return (
    <div className="flex h-full min-h-0 flex-col">
      {/* header */}
      <div className="shrink-0 border-b border-edge px-4 py-2.5">
        <p className="text-[11px] uppercase tracking-wide text-dim">
          Ideas · one tap starts a standing watch
        </p>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto px-4 py-4">
        {/* zip — so "near me" ideas know where you are */}
        <div className="mb-5 flex items-center gap-2 text-xs">
          <span className="text-dim">Near me:</span>
          {editingZip ? (
            <input
              autoFocus
              value={zip}
              inputMode="numeric"
              placeholder="zip"
              onChange={(e) => saveZip(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === "Escape") setEditingZip(false);
              }}
              onBlur={() => setEditingZip(false)}
              className="w-20 rounded-md border border-edge bg-bg px-2 py-1 text-xs text-ink outline-none focus:border-moss/50"
            />
          ) : (
            <button
              onClick={() => setEditingZip(true)}
              className="rounded-md border border-edge px-2 py-1 text-xs text-faint transition-colors hover:border-moss/50 hover:text-moss"
            >
              {zip ? zip : "set zip"}
            </button>
          )}
        </div>

        <IdeaGroup
          title="For you"
          ideas={IDEAS_PERSONAL}
          zip={zip}
          spawning={spawning}
          spawned={spawned}
          onPick={spawn}
        />
        <div className="h-5" />
        <IdeaGroup
          title="More to watch"
          ideas={IDEAS_GENERAL}
          zip={zip}
          spawning={spawning}
          spawned={spawned}
          onPick={spawn}
        />

        <p className="mt-6 text-[11px] leading-relaxed text-dim">
          Tap an idea and it appears as a watch in the sidebar — open it to steer
          it mid-task. You can add the same idea more than once.
        </p>
      </div>
    </div>
  );
}

function IdeaGroup({
  title,
  ideas,
  zip,
  spawning,
  spawned,
  onPick,
}: {
  title: string;
  ideas: Idea[];
  zip: string;
  spawning: Set<string>;
  spawned: Set<string>;
  onPick: (idea: Idea) => void;
}) {
  return (
    <div>
      <p className="pb-2.5 font-mono text-[10px] uppercase tracking-wide text-dim">
        {title}
      </p>
      <div className="flex flex-wrap gap-2">
        {ideas.map((idea) => {
          const busy = spawning.has(idea.label);
          const done = spawned.has(idea.label);
          return (
            <motion.button
              key={idea.label}
              onClick={() => onPick(idea)}
              disabled={busy}
              title={idea.prompt(zip.trim())}
              whileTap={{ scale: 0.96 }}
              className={`rounded-full border px-3.5 py-1.5 text-xs font-medium transition-colors disabled:cursor-default ${
                done
                  ? "border-moss/40 bg-moss/10 text-moss-deep"
                  : "border-edge text-faint hover:border-moss/50 hover:text-moss disabled:opacity-50"
              }`}
            >
              {done ? (
                <span>
                  <span className="mr-1 text-moss" aria-hidden>
                    ✓
                  </span>
                  added
                </span>
              ) : busy ? (
                "adding…"
              ) : (
                idea.label
              )}
            </motion.button>
          );
        })}
      </div>
    </div>
  );
}
