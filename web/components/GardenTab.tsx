"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { getVault, getVaultFile, type VaultFile, type VaultFileMeta } from "@/lib/api";
import { relativeTime, usePolling } from "@/lib/hooks";
import { Markdown } from "@/lib/markdown";

// Same fallback as lib/api.ts — empty env var must still resolve to localhost.
const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

/** Persist an edited vault note. Returns the saved {path, content}. */
async function writeVaultFile(path: string, content: string): Promise<VaultFile> {
  const res = await fetch(`${API_URL}/vault/file`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ path, content }),
  });
  if (!res.ok) throw new Error(`PUT /vault/file → ${res.status}`);
  return (await res.json()) as VaultFile;
}

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

  // Rendered prose vs. the raw .md source — the vault is real files you can crack open.
  const [view, setView] = useState<"rendered" | "raw">("rendered");
  const [copied, setCopied] = useState(false);

  // Inline editing — the memory feels live when you can hand-tend it.
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  // Local override so the rendered view updates instantly after save, ahead of
  // the next poll. Cleared when a different file is selected.
  const [savedContent, setSavedContent] = useState<string | null>(null);

  // Auto-select the first file once the list arrives.
  useEffect(() => {
    if (!files || files.length === 0) return;
    if (!selectedPath || !files.some((f) => f.path === selectedPath)) {
      setSelectedPath(files[0].path);
    }
  }, [files, selectedPath]);

  const { data: file, refresh: refreshFile } = usePolling<VaultFile>(
    selectedPath ? () => getVaultFile(selectedPath) : null,
    3000,
    selectedPath ?? "no-file",
  );

  // Switching files drops any in-flight edit and local override.
  useEffect(() => {
    setEditing(false);
    setSaveError(null);
    setSavedContent(null);
  }, [selectedPath]);

  // What the reading pane shows: our just-saved content wins until the poll
  // catches up, then the live file takes over.
  const displayContent = savedContent ?? file?.content ?? "";

  async function handleSave() {
    if (!selectedPath) return;
    setSaving(true);
    setSaveError(null);
    try {
      const saved = await writeVaultFile(selectedPath, draft);
      setSavedContent(saved.content);
      setEditing(false);
      refreshFile?.();
    } catch (e) {
      setSaveError(e instanceof Error ? e.message : "save failed");
    } finally {
      setSaving(false);
    }
  }

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

      {/* reading pane toolbar — toggle rendered/raw, copy source, send to chat */}
      {selectedPath && file && (
        <div className="flex shrink-0 items-center justify-between gap-2 px-4 pt-3">
          <span className="truncate font-mono text-[11px] text-dim">
            {selectedPath}
          </span>
          <div className="flex shrink-0 items-center gap-1.5">
            {editing ? (
              <>
                <button
                  onClick={handleSave}
                  disabled={saving}
                  className="rounded-md border border-moss/50 bg-moss/10 px-2.5 py-1 text-[11px] text-moss transition-colors hover:bg-moss/20 disabled:opacity-50"
                >
                  {saving ? "saving…" : "save"}
                </button>
                <button
                  onClick={() => {
                    setEditing(false);
                    setSaveError(null);
                  }}
                  disabled={saving}
                  className="rounded-md border border-edge px-2.5 py-1 text-[11px] text-faint transition-colors hover:text-ink disabled:opacity-50"
                >
                  cancel
                </button>
              </>
            ) : (
              <>
                {/* rendered | raw segmented control */}
                <div className="flex items-center rounded-md border border-edge text-[11px]">
                  {(["rendered", "raw"] as const).map((v) => (
                    <button
                      key={v}
                      onClick={() => setView(v)}
                      className={`px-2 py-1 transition-colors first:rounded-l-md last:rounded-r-md ${
                        view === v
                          ? "bg-raised text-ink"
                          : "text-dim hover:text-faint"
                      }`}
                    >
                      {v === "raw" ? "raw .md" : "rendered"}
                    </button>
                  ))}
                </div>
                <button
                  onClick={() => {
                    setDraft(displayContent);
                    setView("raw");
                    setEditing(true);
                  }}
                  className="rounded-md border border-edge px-2.5 py-1 text-[11px] text-faint transition-colors hover:border-moss/50 hover:text-moss"
                >
                  edit
                </button>
                {view === "raw" && (
                  <button
                    onClick={() => {
                      navigator.clipboard?.writeText(displayContent);
                      setCopied(true);
                      setTimeout(() => setCopied(false), 1500);
                    }}
                    className="rounded-md border border-edge px-2 py-1 text-[11px] text-faint transition-colors hover:border-moss/50 hover:text-moss"
                  >
                    {copied ? "copied" : "copy"}
                  </button>
                )}
              </>
            )}
            {!editing && onFactClick && (
              <button
                onClick={() => onFactClick(selectedPath, firstFact(displayContent))}
                className="rounded-md border border-edge px-2.5 py-1 text-[11px] text-faint transition-colors hover:border-moss/50 hover:text-moss"
              >
                → ask in chat
              </button>
            )}
          </div>
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
              editing ? (
                <div className="flex flex-col gap-2">
                  {saveError && (
                    <p className="text-[11px] text-red-400">{saveError}</p>
                  )}
                  <textarea
                    value={draft}
                    onChange={(e) => setDraft(e.target.value)}
                    spellCheck={false}
                    autoFocus
                    className="min-h-[16rem] w-full resize-y rounded-md border border-moss/30 bg-raised/40 px-3 py-2 font-mono text-[12px] leading-relaxed text-ink outline-none focus:border-moss/60"
                  />
                </div>
              ) : view === "raw" ? (
                <pre className="whitespace-pre-wrap break-words font-mono text-[12px] leading-relaxed text-faint">
                  {displayContent}
                </pre>
              ) : (
                <Markdown text={displayContent} provenance />
              )
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
