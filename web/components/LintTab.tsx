"use client";

import { useCallback, useState } from "react";
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
  open: "border-amber/50 text-amber",
  auto_applied: "border-moss-deep text-moss",
  approved: "border-moss-deep text-moss",
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
  onResolved,
}: {
  finding: Finding;
  onResolved: () => void;
}) {
  const [diffOpen, setDiffOpen] = useState(false);
  const [busy, setBusy] = useState<"apply" | "reject" | null>(null);

  const act = useCallback(
    async (action: "apply" | "reject") => {
      if (busy) return;
      setBusy(action);
      try {
        if (action === "apply") await applyFinding(finding.id);
        else await rejectFinding(finding.id);
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
    <article className="rounded-lg border border-edge bg-surface p-3">
      <div className="flex flex-wrap items-center gap-1.5">
        <span className="rounded border border-moss-deep/60 bg-moss-deep/15 px-1.5 py-0.5 font-mono text-[10px] uppercase tracking-wide text-moss">
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
          {diffOpen && (
            <div className="mt-1.5">
              <DiffView diff={finding.diff} />
            </div>
          )}
        </div>
      )}

      {finding.status === "open" && (
        <div className="mt-3 flex gap-2">
          <button
            onClick={() => act("apply")}
            disabled={busy !== null}
            className="rounded-md bg-moss-deep px-3 py-1 text-xs font-medium text-ink transition-colors hover:bg-moss-deep/80 disabled:opacity-50"
          >
            {busy === "apply" ? "Applying…" : "Apply"}
          </button>
          <button
            onClick={() => act("reject")}
            disabled={busy !== null}
            className="rounded-md border border-edge px-3 py-1 text-xs text-faint transition-colors hover:border-rust/60 hover:text-rust disabled:opacity-50"
          >
            {busy === "reject" ? "Rejecting…" : "Reject"}
          </button>
        </div>
      )}
    </article>
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
          className="rounded-md border border-edge px-2.5 py-1 text-xs text-faint transition-colors hover:border-moss-deep hover:text-moss disabled:opacity-50"
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
        {sorted?.map((f) => (
          <FindingCard key={f.id} finding={f} onResolved={refresh} />
        ))}
      </div>
    </div>
  );
}
