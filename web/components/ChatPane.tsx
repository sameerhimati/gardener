"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  getMessages,
  runWatch,
  sendChat,
  sendWatchMessage,
  type Message,
  type Watch,
} from "@/lib/api";
import { relativeTime, usePolling } from "@/lib/hooks";
import { Markdown } from "@/lib/markdown";

const MAIN_SESSION_KEY = "gardener_main_session_id";

interface ChatPaneProps {
  selected: string; // "main" or a watch id
  watch: Watch | null; // resolved watch when selected is a watch id
}

function Bubble({ message }: { message: Message }) {
  const isUser = message.role === "user";
  if (isUser) {
    return (
      <div className="flex justify-end">
        <div className="max-w-[78%] rounded-2xl rounded-br-sm bg-moss-deep/30 px-4 py-2.5 text-sm leading-relaxed text-ink whitespace-pre-wrap">
          {message.content}
        </div>
      </div>
    );
  }
  return (
    <div className="flex justify-start">
      <div className="max-w-[78%] rounded-2xl rounded-bl-sm border border-edge bg-raised px-4 py-2.5">
        <Markdown text={message.content} />
      </div>
    </div>
  );
}

export default function ChatPane({ selected, watch }: ChatPaneProps) {
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

  useEffect(() => {
    // switching conversations: clear transient state
    setPending([]);
    setSendError(false);
    setSteering(false);
  }, [selected]);

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
  }, [messageCount, selected]);

  const send = useCallback(async () => {
    const text = input.trim();
    if (!text || sending) return;
    if (!isMain && !watch) return; // watch not resolved yet — don't strand a message
    setSending(true);
    setSendError(false);
    setInput("");
    const now = new Date().toISOString();
    setPending((cur) => [...cur, { role: "user", content: text, ts: now }]);

    try {
      if (isMain) {
        const res = await sendChat(mainSession, text);
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
  }, [input, sending, isMain, mainSession, watch, refresh]);

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
    <section className="flex min-w-0 flex-1 flex-col bg-bg">
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
          <button
            onClick={onRunNow}
            disabled={runningNow}
            className="shrink-0 rounded-md border border-edge px-3 py-1.5 text-xs text-faint transition-colors hover:border-moss-deep hover:text-moss disabled:opacity-50"
          >
            {runningNow ? "Running…" : "Run now"}
          </button>
        )}
      </header>

      {/* messages */}
      <div className="min-h-0 flex-1 overflow-y-auto">
        {messages.length === 0 ? (
          emptyState
        ) : (
          <div className="mx-auto flex max-w-3xl flex-col gap-4 px-5 py-6">
            {messages.map((m, i) => (
              <Bubble key={`${m.ts}-${i}`} message={m} />
            ))}
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
          <div className="flex items-end gap-2 rounded-xl border border-edge bg-surface px-3 py-2 focus-within:border-moss-deep">
            <textarea
              rows={1}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  send();
                }
              }}
              placeholder={
                isMain
                  ? "Ask Gardener anything…"
                  : "Steer this watch — e.g. “only 3+ bd, 1500+ sqft”"
              }
              className="max-h-40 min-h-[24px] flex-1 resize-none bg-transparent text-sm text-ink outline-none placeholder:text-dim"
            />
            <button
              onClick={send}
              disabled={sending || input.trim() === ""}
              className="shrink-0 rounded-lg bg-moss-deep px-3 py-1.5 text-xs font-medium text-ink transition-colors hover:bg-moss-deep/80 disabled:opacity-40"
            >
              {sending ? "…" : "Send"}
            </button>
          </div>
        </div>
      </footer>
    </section>
  );
}
