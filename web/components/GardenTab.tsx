"use client";

import { useEffect, useRef, useState } from "react";
import { getVault, getVaultFile, type VaultFile, type VaultFileMeta } from "@/lib/api";
import { relativeTime, usePolling } from "@/lib/hooks";
import { Markdown } from "@/lib/markdown";

export default function GardenTab() {
  const { data: files } = usePolling<VaultFileMeta[]>(getVault, 3000, "vault");

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
      {/* file list */}
      <div className="max-h-[38%] shrink-0 overflow-y-auto border-b border-edge py-1">
        {files === null && (
          <div className="px-4 py-2 text-xs text-dim">…</div>
        )}
        {files?.map((f) => (
          <button
            key={f.path}
            onClick={() => setSelectedPath(f.path)}
            className={`block w-full px-4 py-2 text-left transition-colors ${
              flashing.has(f.path) ? "animate-row-flash" : ""
            } ${
              selectedPath === f.path ? "bg-raised" : "hover:bg-hover"
            }`}
          >
            <span
              className={`block truncate text-sm ${
                selectedPath === f.path ? "text-ink" : "text-faint"
              }`}
            >
              {f.title || f.path}
            </span>
            <span className="block truncate font-mono text-[11px] text-dim">
              {f.path} · {relativeTime(f.updated)}
            </span>
          </button>
        ))}
      </div>

      {/* file content */}
      <div className="min-h-0 flex-1 overflow-y-auto px-4 py-4">
        {file ? (
          <Markdown text={file.content} provenance />
        ) : (
          <p className="text-xs text-dim">
            {selectedPath ? "…" : "Select a file to read it."}
          </p>
        )}
      </div>
    </div>
  );
}
