"use client";

import { useState } from "react";
import { getFindings, type Finding } from "@/lib/api";
import { usePolling } from "@/lib/hooks";
import GardenTab from "@/components/GardenTab";
import LintTab from "@/components/LintTab";

type Tab = "garden" | "lint";

export default function RightRail({
  onFactClick,
}: {
  onFactClick?: (path: string, snippet: string) => void;
}) {
  const [tab, setTab] = useState<Tab>("garden");

  // Findings are polled here so the Lint tab badge stays live even while the
  // Garden tab is showing.
  const { data: findings, refresh } = usePolling<Finding[]>(
    getFindings,
    3000,
    "findings",
  );
  const openCount = findings?.filter((f) => f.status === "open").length ?? 0;

  return (
    <aside className="flex w-[380px] shrink-0 flex-col border-l border-edge bg-surface">
      {/* tabs */}
      <div className="flex h-14 shrink-0 items-end gap-1 border-b border-edge px-3">
        {(["garden", "lint"] as const).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`relative rounded-t-md px-3 pb-2.5 pt-2 text-sm transition-colors ${
              tab === t
                ? "text-ink"
                : "text-dim hover:text-faint"
            }`}
          >
            {t === "garden" ? "Garden" : "Lint"}
            {t === "lint" && openCount > 0 && (
              <span className="ml-1.5 inline-flex h-4 min-w-4 items-center justify-center rounded-full bg-amber/20 px-1 font-mono text-[10px] text-amber">
                {openCount}
              </span>
            )}
            {tab === t && (
              <span className="absolute inset-x-2 -bottom-px h-px bg-moss" />
            )}
          </button>
        ))}
      </div>

      <div className="min-h-0 flex-1">
        {tab === "garden" ? (
          <GardenTab onFactClick={onFactClick} />
        ) : (
          <LintTab findings={findings} refresh={refresh} />
        )}
      </div>
    </aside>
  );
}
