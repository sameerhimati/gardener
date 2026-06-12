"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { getVault, getVaultFile, type VaultFile, type VaultFileMeta } from "@/lib/api";
import { relativeTime, usePolling } from "@/lib/hooks";
import { Markdown } from "@/lib/markdown";

/** First meaningful line of a vault note — for the "ask in chat" snippet. */
function firstFact(content: string): string {
  for (const raw of content.split("\n")) {
    const line = raw.replace(/^[-*]\s*/, "").trim();
    if (!line || line === "---" || line.startsWith("#") || /^\w+:\s/.test(line))
      continue;
    return line.replace(/\s*\(src:[^)]*\)\s*$/, "").slice(0, 140);
  }
  return content.trim().slice(0, 140);
}

export default function GardenTab({
  onFactClick,
}: {
  onFactClick?: (path: string, snippet: string) => void;
}) {
  const { data: files } = usePolling<VaultFileMeta[]>(getVault, 3000, "vault");

  // Group files by their top folder so the vault reads like a real tree.
  const groups = useMemo(() => {
    const m = new Map<string, VaultFileMeta[]>();
    for (const f of files ?? []) {
      const folder = f.path.includes("/") ? f.path.split("/")[0] : "vault";
      (m.get(folder) ?? m.set(folder, []).get(folder)!).push(f);
    }
    return [...m.entries()].sort((a, b) => a[0].localeCompare(b[0]));
  }, [files]);

  const [selectedPath, setSelectedPath] = useState<string | null>(null);

  // Auto-select the first file once the list arrives.
  useEffect(() => {
    if (!files || files.length === 0) return;
    if (!selectedPath || !files.some((f) => f.path === selectedPath)) {
      setSelectedPath(files[0].path);
    }
  }, [files, selectedPath]);

  const { data: file } = usePolling<VaultFile>(
    selectedPath ? () => getVaultFile(selectedPath) : null,
    3000,
    selectedPath ?? "no-file",
  );

  // Flash a row when its `updated` changes between polls — memory visibly
  // changing is the money moment.
  const prevUpdated = useRef<Map<string, string>>(new Map());
  const [flashing, setFlashing] = useState<Set<string>>(new Set());

  useEffect(() => {
    if (!files) return;
    const changed: string[] = [];
    for (const f of files) {
      const prev = prevUpdated.current.get(f.path);
      if (prev !== undefined && prev !== f.updated) changed.push(f.path);
      prevUpdated.current.set(f.path, f.updated);
    }
    if (changed.length > 0) {
      setFlashing((cur) => new Set([...cur, ...changed]));
      const timer = setTimeout(() => {
        setFlashing((cur) => {
          const next = new Set(cur);
          changed.forEach((p) => next.delete(p));
          return next;
        });
      }, 2800);
      return () => clearTimeout(timer);
    }
  }, [files]);

  if (files !== null && files.length === 0) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-2 px-6 text-center">
        <p className="text-sm text-faint">The garden is bare.</p>
        <p className="max-w-xs text-xs leading-relaxed text-dim">
          As you chat and steer watches, Gardener plants what it learns here as
          markdown — and tends it.
        </p>
      </div>
    );
  }

  return (
    <div className="flex h-full min-h-0 flex-col">
      {/* vault header — frames it as a living, readable vault */}
      <div className="shrink-0 border-b border-edge px-4 py-2.5">
        <p className="text-[11px] uppercase tracking-wide text-dim">
          Your memory · {files?.length ?? 0} markdown{" "}
          {files?.length === 1 ? "note" : "notes"} you can read
        </p>
      </div>

      {/* file tree, grouped by folder */}
      <div className="max-h-[38%] shrink-0 overflow-y-auto border-b border-edge py-1">
        {files === null && (
          <div className="px-4 py-2 text-xs text-dim">…</div>
        )}
        {groups.map(([folder, items]) => (
          <div key={folder} className="py-1">
            <p className="px-4 pb-1 pt-1.5 font-mono text-[10px] uppercase tracking-wide text-dim">
              {folder}
            </p>
            {items.map((f) => (
              <button
                key={f.path}
                onClick={() => setSelectedPath(f.path)}
                className={`block w-full px-4 py-1.5 pl-5 text-left transition-colors ${
                  flashing.has(f.path) ? "animate-moss-sweep" : ""
                } ${selectedPath === f.path ? "bg-raised" : "hover:bg-hover"}`}
              >
                <span
                  className={`block truncate text-sm ${
                    selectedPath === f.path ? "text-ink" : "text-faint"
                  }`}
                >
                  {f.title || f.path}
                </span>
                <span className="block truncate font-mono text-[11px] text-dim">
                  {relativeTime(f.updated)}
                </span>
              </button>
            ))}
          </div>
        ))}
      </div>

      {/* reading pane toolbar — send this note to the chat */}
      {onFactClick && selectedPath && file && (
        <div className="flex shrink-0 items-center justify-between gap-2 px-4 pt-3">
          <span className="truncate font-mono text-[11px] text-dim">
            {selectedPath}
          </span>
          <button
            onClick={() =>
              onFactClick(selectedPath, firstFact(file.content))
            }
            className="shrink-0 rounded-md border border-edge px-2.5 py-1 text-[11px] text-faint transition-colors hover:border-moss/50 hover:text-moss"
          >
            → ask in chat
          </button>
        </div>
      )}

      {/* file content — crossfades when a different file is selected */}
      <div className="min-h-0 flex-1 overflow-y-auto px-4 py-4">
        <AnimatePresence mode="wait" initial={false}>
          <motion.div
            key={selectedPath ?? "none"}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.15, ease: "easeOut" }}
          >
            {file ? (
              <Markdown text={file.content} provenance />
            ) : (
              <p className="text-xs text-dim">
                {selectedPath ? "…" : "Select a file to read it."}
              </p>
            )}
          </motion.div>
        </AnimatePresence>
      </div>
    </div>
  );
}
