"use client";

import { useCallback, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import {
  applyFinding,
  rejectFinding,
  runLint,
  type Finding,
  type FindingStatus,
} from "@/lib/api";
import { relativeTime } from "@/lib/hooks";
import DiffView from "@/components/DiffView";

const STATUS_STYLES: Record<FindingStatus, string> = {
  open: "border-amber/40 text-amber",
  auto_applied: "border-moss/30 text-moss",
  approved: "border-moss/30 text-moss",
  rejected: "border-edge text-dim",
};

const STATUS_LABELS: Record<FindingStatus, string> = {
  open: "open",
  auto_applied: "auto-applied",
  approved: "approved",
  rejected: "rejected",
};

function FindingCard({
  finding,
  index,
  onResolved,
}: {
  finding: Finding;
  index: number;
  onResolved: () => void;
}) {
  const [diffOpen, setDiffOpen] = useState(false);
  const [busy, setBusy] = useState<"apply" | "reject" | null>(null);
  // Set after a successful Apply — washes the card moss before it settles
  // into its applied state.
  const [justApplied, setJustApplied] = useState(false);

  const act = useCallback(
    async (action: "apply" | "reject") => {
      if (busy) return;
      setBusy(action);
      try {
        if (action === "apply") await applyFinding(finding.id);
        else await rejectFinding(finding.id);
        if (action === "apply") setJustApplied(true);
        onResolved();
      } catch {
        // fail soft — banner handles it
      } finally {
        setBusy(null);
      }
    },
    [busy, finding.id, onResolved],
  );

  const statusCls =
    STATUS_STYLES[finding.status] ?? "border-edge text-faint";
  const statusLabel = STATUS_LABELS[finding.status] ?? finding.status;

  return (
    <motion.article
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{
        duration: 0.3,
        ease: "easeOut",
        delay: Math.min(index, 6) * 0.05,
      }}
      className={`rounded-lg border border-edge bg-bg p-3 ${
        justApplied ? "animate-moss-wash" : ""
      }`}
    >
      <div className="flex flex-wrap items-center gap-1.5">
        <span className="rounded border border-moss/25 bg-moss/10 px-1.5 py-0.5 font-mono text-[10px] uppercase tracking-wide text-moss">
          {finding.rule}
        </span>
        <span
          className={`rounded border px-1.5 py-0.5 text-[10px] ${statusCls}`}
        >
          {statusLabel}
        </span>
        <span className="ml-auto font-mono text-[10px] text-dim">
          {Math.round(finding.confidence * 100)}% · {relativeTime(finding.ts)}
        </span>
      </div>

      <p className="mt-2 text-sm leading-relaxed text-ink">{finding.summary}</p>
      <p className="mt-1 truncate font-mono text-[11px] text-dim">
        {finding.vault_path}
      </p>

      {finding.diff && (
        <div className="mt-2">
          <button
            onClick={() => setDiffOpen((v) => !v)}
            className="text-[11px] text-faint transition-colors hover:text-moss"
          >
            {diffOpen ? "▾ hide diff" : "▸ show diff"}
          </button>
          <AnimatePresence initial={false}>
            {diffOpen && (
              <motion.div
                initial={{ height: 0, opacity: 0 }}
                animate={{ height: "auto", opacity: 1 }}
                exit={{ height: 0, opacity: 0 }}
                transition={{ duration: 0.25, ease: "easeOut" }}
                className="overflow-hidden"
              >
                <div className="mt-1.5">
                  <DiffView diff={finding.diff} />
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      )}

      {finding.status === "open" && (
        <div className="mt-3 flex gap-2">
          <button
            onClick={() => act("apply")}
            disabled={busy !== null}
            className="rounded-md bg-moss px-3 py-1 text-xs font-medium text-white transition-colors hover:bg-moss-deep disabled:opacity-50"
          >
            {busy === "apply" ? "Applying…" : "Apply"}
          </button>
          <button
            onClick={() => act("reject")}
            disabled={busy !== null}
            className="rounded-md border border-edge px-3 py-1 text-xs text-faint transition-colors hover:border-rust/40 hover:text-rust disabled:opacity-50"
          >
            {busy === "reject" ? "Rejecting…" : "Reject"}
          </button>
        </div>
      )}
    </motion.article>
  );
}

export default function LintTab({
  findings,
  refresh,
}: {
  findings: Finding[] | null;
  refresh: () => void;
}) {
  const [linting, setLinting] = useState(false);

  const onRunLint = useCallback(async () => {
    if (linting) return;
    setLinting(true);
    try {
      await runLint();
      refresh();
    } catch {
      // fail soft
    } finally {
      setLinting(false);
    }
  }, [linting, refresh]);

  const sorted = findings
    ? [...findings].sort(
        (a, b) => new Date(b.ts).getTime() - new Date(a.ts).getTime(),
      )
    : null;

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex shrink-0 items-center justify-between border-b border-edge px-4 py-2.5">
        <span className="text-xs text-dim">
          the agent auditing its own memory
        </span>
        <button
          onClick={onRunLint}
          disabled={linting}
          className="rounded-md border border-edge px-2.5 py-1 text-xs text-faint transition-colors hover:border-moss/50 hover:text-moss disabled:opacity-50"
        >
          {linting ? "Linting…" : "Run lint now"}
        </button>
      </div>

      <div className="min-h-0 flex-1 space-y-2.5 overflow-y-auto px-4 py-3">
        {sorted === null && <p className="text-xs text-dim">…</p>}
        {sorted !== null && sorted.length === 0 && (
          <div className="flex flex-col items-center gap-2 px-4 pt-16 text-center">
            <p className="text-sm text-faint">No findings — the garden is tidy.</p>
            <p className="max-w-xs text-xs leading-relaxed text-dim">
              When memory contradicts what Gardener has learned, corrections
              show up here as diffs.
            </p>
          </div>
        )}
        {sorted?.map((f, i) => (
          <FindingCard key={f.id} finding={f} index={i} onResolved={refresh} />
        ))}
      </div>
    </div>
  );
}
