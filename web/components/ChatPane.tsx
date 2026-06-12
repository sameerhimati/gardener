"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { motion } from "framer-motion";
import {
  getMessages,
  runWatch,
  sendChat,
  sendWatchMessage,
  updateWatch,
  type Message,
  type Watch,
} from "@/lib/api";
import { relativeTime, usePolling } from "@/lib/hooks";
import { Markdown } from "@/lib/markdown";
import ThinkingDots from "@/components/ThinkingDots";
import WatchActivityTrail from "@/components/WatchActivityTrail";

const MAIN_SESSION_KEY = "gardener_main_session_id";

// How often a watch re-runs. Labels are friendly; values are seconds for the API.
const CADENCE_OPTIONS: { label: string; sec: number }[] = [
  { label: "every 5m", sec: 300 },
  { label: "every 15m", sec: 900 },
  { label: "every 30m", sec: 1800 },
  { label: "hourly", sec: 3600 },
  { label: "every 6h", sec: 21600 },
  { label: "every 12h", sec: 43200 },
  { label: "once a day", sec: 86400 },
];
const DEFAULT_CADENCE_SEC = 3600;

interface ChatPaneProps {
  selected: string; // "main" or a watch id
  watch: Watch | null; // resolved watch when selected is a watch id
  injectedText?: string; // text pushed in from clicking a garden fact
  onConsumeInjected?: () => void;
}

function Bubble({ message }: { message: Message }) {
  const isUser = message.role === "user";
  if (isUser) {
    return (
      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.25, ease: "easeOut" }}
        className="flex justify-end"
      >
        <div className="max-w-[78%] rounded-xl bg-moss/10 px-4 py-2.5 text-sm leading-relaxed text-ink whitespace-pre-wrap">
          {message.content}
        </div>
      </motion.div>
    );
  }
  // Assistant replies sit plain on the page, like a document.
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.25, ease: "easeOut" }}
      className="py-1 pr-6"
    >
      <Markdown text={message.content} />
    </motion.div>
  );
}

export default function ChatPane({
  selected,
  watch,
  injectedText,
  onConsumeInjected,
}: ChatPaneProps) {
  const isMain = selected === "main";

  // Main chat session id lives in localStorage from the first /chat response.
  const [mainSession, setMainSession] = useState<string | null>(null);
  useEffect(() => {
    setMainSession(localStorage.getItem(MAIN_SESSION_KEY));
  }, []);

  const sessionId = isMain ? mainSession : (watch?.session_id ?? null);

  const { data: serverMessages, refresh } = usePolling<Message[]>(
    sessionId ? () => getMessages(sessionId) : null,
    2000,
    sessionId ?? "no-session",
  );

  // Optimistic messages, reconciled away once the server echoes them back.
  const [pending, setPending] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [sendError, setSendError] = useState(false);
  const [steering, setSteering] = useState(false);
  const [runningNow, setRunningNow] = useState(false);
  const [image, setImage] = useState<string | null>(null); // data: URI for a dropped/pasted image
  const [dragOver, setDragOver] = useState(false); // dragging an image over the whole pane

  // Per-watch cadence, seeded from the watch and updated optimistically; the
  // 3s watch poll upstream reconciles it back to the server value.
  const [cadenceSec, setCadenceSec] = useState<number>(
    watch?.cadence_sec ?? DEFAULT_CADENCE_SEC,
  );
  const [savingCadence, setSavingCadence] = useState(false);
  useEffect(() => {
    setCadenceSec(watch?.cadence_sec ?? DEFAULT_CADENCE_SEC);
  }, [watch?.id, watch?.cadence_sec]);

  useEffect(() => {
    // switching conversations: clear transient state
    setPending([]);
    setSendError(false);
    setSteering(false);
    setImage(null);
    setDragOver(false);
  }, [selected]);

  // A garden fact was clicked: drop its text into the composer.
  useEffect(() => {
    if (!injectedText) return;
    setInput((cur) => (cur ? `${cur}\n${injectedText}` : injectedText));
    onConsumeInjected?.();
  }, [injectedText, onConsumeInjected]);

  const readImageFile = useCallback((file: File) => {
    if (!file.type.startsWith("image/")) return;
    const reader = new FileReader();
    reader.onload = () => setImage(reader.result as string);
    reader.readAsDataURL(file);
  }, []);

  useEffect(() => {
    if (!serverMessages || pending.length === 0) return;
    setPending((cur) =>
      cur.filter(
        (p) =>
          !serverMessages.some(
            (m) => m.role === p.role && m.content === p.content,
          ),
      ),
    );
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [serverMessages]);

  const messages = [...(serverMessages ?? []), ...pending];

  // Auto-scroll to the newest message.
  const bottomRef = useRef<HTMLDivElement>(null);
  const messageCount = messages.length;
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messageCount, selected, sending]);

  const send = useCallback(async () => {
    const text = input.trim();
    if ((!text && !image) || sending) return;
    if (!isMain && !watch) return; // watch not resolved yet — don't strand a message
    const sentImage = image;
    setSending(true);
    setSendError(false);
    setInput("");
    setImage(null);
    const now = new Date().toISOString();
    const shown = sentImage ? `${text}\n🖼️ image attached`.trim() : text;
    setPending((cur) => [...cur, { role: "user", content: shown, ts: now }]);

    try {
      if (isMain) {
        const res = await sendChat(mainSession, text || "(see image)", sentImage);
        if (!mainSession && res.session_id) {
          localStorage.setItem(MAIN_SESSION_KEY, res.session_id);
          setMainSession(res.session_id);
        }
        setPending((cur) => [
          ...cur,
          { role: "assistant", content: res.reply, ts: new Date().toISOString() },
        ]);
      } else if (watch) {
        setSteering(true);
        const res = await sendWatchMessage(watch.id, text);
        setPending((cur) => [
          ...cur,
          { role: "assistant", content: res.reply, ts: new Date().toISOString() },
        ]);
        setTimeout(() => setSteering(false), 4000);
      }
      refresh();
    } catch {
      setSteering(false);
      setSendError(true);
      // restore the message so nothing typed is lost
      setPending((cur) => cur.filter((p) => p.content !== text));
      setInput(text);
    } finally {
      setSending(false);
    }
  }, [input, image, sending, isMain, mainSession, watch, refresh]);

  const onRunNow = useCallback(async () => {
    if (!watch || runningNow) return;
    setRunningNow(true);
    try {
      await runWatch(watch.id);
      refresh();
    } catch {
      // fail soft — banner handles it
    } finally {
      setRunningNow(false);
    }
  }, [watch, runningNow, refresh]);

  const onChangeCadence = useCallback(
    async (sec: number) => {
      if (!watch || savingCadence) return;
      const prev = cadenceSec;
      setCadenceSec(sec); // optimistic — header reflects it instantly
      setSavingCadence(true);
      try {
        await updateWatch(watch.id, { cadence_sec: sec });
      } catch {
        setCadenceSec(prev); // fail soft — roll back
      } finally {
        setSavingCadence(false);
      }
    },
    [watch, savingCadence, cadenceSec],
  );

  const emptyState = isMain ? (
    <div className="flex h-full flex-col items-center justify-center gap-2 px-8 text-center">
      <p className="text-sm text-faint">Nothing planted yet.</p>
      <p className="max-w-sm text-xs leading-relaxed text-dim">
        Say hello, or ask Gardener to keep an eye on something — watches grow
        into their own chats in the sidebar.
      </p>
    </div>
  ) : (
    <div className="flex h-full flex-col items-center justify-center gap-2 px-8 text-center">
      <p className="text-sm text-faint">This watch hasn&apos;t spoken yet.</p>
      <p className="max-w-sm text-xs leading-relaxed text-dim">
        Run a cycle, or steer it — your steering is distilled into the memory
        vault.
      </p>
    </div>
  );

  return (
    <section
      // Whole pane is a drop target — drop a screenshot anywhere to attach it.
      // Both onDragOver AND onDrop must preventDefault, or the browser navigates
      // to the dropped image instead of attaching it.
      onDragOver={(e) => {
        if (e.dataTransfer?.types?.includes("Files")) {
          e.preventDefault();
          setDragOver(true);
        }
      }}
      onDragLeave={(e) => {
        // Only clear when the cursor actually leaves the pane, not on child enter.
        if (e.currentTarget === e.target) setDragOver(false);
      }}
      onDrop={(e) => {
        e.preventDefault();
        setDragOver(false);
        const file = e.dataTransfer.files?.[0];
        if (file) readImageFile(file);
      }}
      className="relative flex min-w-0 flex-1 flex-col bg-bg"
    >
      {/* calm affordance while a file is dragged over the pane */}
      {dragOver && (
        <div className="pointer-events-none absolute inset-3 z-20 flex items-center justify-center rounded-2xl border-2 border-dashed border-moss/60 bg-moss/5 backdrop-blur-[1px]">
          <span className="rounded-full bg-bg/90 px-4 py-2 text-sm font-medium text-moss-deep shadow-sm">
            Drop image to attach
          </span>
        </div>
      )}
      {/* header */}
      <header className="flex h-14 shrink-0 items-center justify-between gap-4 border-b border-edge px-5">
        <div className="min-w-0">
          <h1 className="truncate text-sm font-medium text-ink">
            {isMain ? "Main chat" : (watch?.task ?? "Watch")}
          </h1>
          {!isMain && watch && (
            <p className="text-[11px] text-dim">
              {watch.status} · last run {relativeTime(watch.last_run)}
            </p>
          )}
        </div>
        {!isMain && watch && (
          <div className="flex shrink-0 items-center gap-2">
            {/* how often this watch re-runs */}
            <label className="flex items-center gap-1.5 text-[11px] text-dim">
              <span className="hidden sm:inline">Runs</span>
              <select
                value={cadenceSec}
                onChange={(e) => onChangeCadence(Number(e.target.value))}
                disabled={savingCadence}
                aria-label="How often this watch runs"
                className="rounded-md border border-edge bg-bg px-2 py-1.5 text-xs text-faint outline-none transition-colors hover:border-moss/50 focus:border-moss/50 disabled:opacity-50"
              >
                {/* If the server has a non-standard cadence, keep it selectable. */}
                {!CADENCE_OPTIONS.some((o) => o.sec === cadenceSec) && (
                  <option value={cadenceSec}>{`every ${cadenceSec}s`}</option>
                )}
                {CADENCE_OPTIONS.map((o) => (
                  <option key={o.sec} value={o.sec}>
                    {o.label}
                  </option>
                ))}
              </select>
            </label>
            <button
              onClick={onRunNow}
              disabled={runningNow}
              className="rounded-md border border-edge px-3 py-1.5 text-xs text-faint transition-colors hover:border-moss/50 hover:text-moss disabled:opacity-50"
            >
              {runningNow ? "Running…" : "Run now"}
            </button>
          </div>
        )}
      </header>

      {/* what the worker actually did on the web */}
      {!isMain && watch && <WatchActivityTrail watchId={watch.id} />}

      {/* messages */}
      <div className="min-h-0 flex-1 overflow-y-auto">
        {messages.length === 0 ? (
          emptyState
        ) : (
          <div className="mx-auto flex max-w-3xl flex-col gap-4 px-5 py-6">
            {messages.map((m, i) => (
              <Bubble key={`${m.ts}-${i}`} message={m} />
            ))}
            {sending && (
              <motion.div
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ duration: 0.25, delay: 0.2 }}
                className="py-1"
              >
                <ThinkingDots />
              </motion.div>
            )}
            <div ref={bottomRef} />
          </div>
        )}
      </div>

      {/* composer */}
      <footer className="shrink-0 border-t border-edge px-5 pb-5 pt-3">
        <div className="mx-auto max-w-3xl">
          <div className="h-5 px-1 text-[11px]">
            {steering && (
              <span className="text-moss">
                steering — distilling into memory…
              </span>
            )}
            {sendError && !steering && (
              <span className="text-amber">
                couldn&apos;t reach Gardener — message not sent
              </span>
            )}
          </div>
          <div className="rounded-xl border border-edge bg-bg px-3 py-2 shadow-sm transition-colors focus-within:border-moss/50">
            {image && (
              <div className="mb-2 flex items-center gap-2">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src={image}
                  alt="attached"
                  className="h-12 w-12 rounded-md border border-edge object-cover"
                />
                <button
                  onClick={() => setImage(null)}
                  className="text-[11px] text-dim underline hover:text-faint"
                >
                  remove
                </button>
              </div>
            )}
            <div className="flex items-end gap-2">
              <textarea
                rows={1}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onPaste={(e) => {
                  const file = e.clipboardData.files?.[0];
                  if (file && file.type.startsWith("image/")) readImageFile(file);
                }}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    send();
                  }
                }}
                placeholder={
                  isMain
                    ? "Ask Gardener anything — or drop in an image…"
                    : "Steer this watch — e.g. “only 3+ bd, 1500+ sqft”"
                }
                className="max-h-40 min-h-[24px] flex-1 resize-none bg-transparent text-sm text-ink outline-none placeholder:text-dim"
              />
              <button
                onClick={send}
                disabled={sending || (input.trim() === "" && !image)}
                className="shrink-0 rounded-lg bg-moss px-3 py-1.5 text-xs font-medium text-white transition-colors hover:bg-moss-deep disabled:opacity-40"
              >
                {sending ? "…" : "Send"}
              </button>
            </div>
          </div>
        </div>
      </footer>
    </section>
  );
}
