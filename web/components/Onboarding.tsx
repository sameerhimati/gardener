"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { createWatch, onboardingTurn, type PlantedFact } from "@/lib/api";
import { Markdown } from "@/lib/markdown";
import ThinkingDots from "@/components/ThinkingDots";

export const ONBOARDED_KEY = "gardener_onboarded";
// Must match MAIN_SESSION_KEY in ChatPane — carrying the onboarding session here
// makes the main chat continue the same conversation (no "Nothing planted yet").
const MAIN_SESSION_KEY = "gardener_main_session_id";

const INTRO =
  "Your memory is a garden — everything I learn about you, growing as a vault you can read. I'm the gardener: I plant, I weed the contradictions, I keep it true.";

const QUESTIONS = [
  "Who am I gardening for? Tell me about yourself.",
  "What are you actively looking for or deciding on right now?",
  "What should I keep an eye on for you while you're away?",
  "Any hard preferences I should never forget?",
];

const WATCH_QUESTION = 2; // answer to this one can become a standing watch

/** One user↔Gardener exchange inside a step. `reply: null` = in flight. */
interface Exchange {
  user: string;
  reply: string | null;
  facts: PlantedFact[];
}

const EASE_OUT: [number, number, number, number] = [0.2, 0.7, 0.3, 1];

function FactChip({ fact, index }: { fact: PlantedFact; index: number }) {
  return (
    <motion.span
      initial={{ opacity: 0, scale: 0.85, y: 5 }}
      animate={{ opacity: 1, scale: 1, y: 0 }}
      transition={{ duration: 0.3, ease: EASE_OUT, delay: index * 0.06 }}
      className="inline-flex max-w-full items-center gap-2 rounded-full border border-moss/25 bg-moss/10 px-3 py-1.5 text-xs text-moss-deep"
    >
      <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-moss" aria-hidden />
      <span className="truncate">
        <span className="font-medium">{fact.topic}</span>
        <span className="text-moss-deep/60"> — </span>
        {fact.fact}
      </span>
    </motion.span>
  );
}

function ExchangeView({ exchange }: { exchange: Exchange }) {
  return (
    <div>
      {/* the user's words, settled on the page */}
      <motion.p
        initial={{ opacity: 0, y: 6 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.25, ease: EASE_OUT }}
        className="whitespace-pre-wrap rounded-xl bg-moss/10 px-4 py-3 text-sm leading-relaxed text-ink"
      >
        {exchange.user}
      </motion.p>

      {exchange.reply === null ? (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: 0.25, delay: 0.15 }}
          className="mt-4 pl-1"
        >
          <ThinkingDots />
        </motion.div>
      ) : (
        <>
          {/* Gardener speaks back — plain document text, like the chat pane */}
          <motion.div
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.3, ease: EASE_OUT }}
            className="mt-4 pr-4"
          >
            <Markdown text={exchange.reply} />
          </motion.div>

          {exchange.facts.length > 0 && (
            <div className="mt-4 flex flex-wrap gap-2">
              {exchange.facts.map((f, i) => (
                <FactChip key={i} fact={f} index={i} />
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}

export default function Onboarding({ onDone }: { onDone: () => void }) {
  const [step, setStep] = useState(0); // 0..3 questions, 4 = final screen
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [exchanges, setExchanges] = useState<Exchange[][]>(() =>
    QUESTIONS.map(() => []),
  );
  const [input, setInput] = useState("");
  const [thinking, setThinking] = useState(false);
  const [sendError, setSendError] = useState(false);
  const [watchState, setWatchState] = useState<"idle" | "starting" | "started">(
    "idle",
  );
  const [leaving, setLeaving] = useState(false);

  const finish = useCallback(() => {
    // Carry the onboarding session into the main chat so the conversation +
    // planted facts are already there (only if they actually talked).
    if (sessionId) localStorage.setItem(MAIN_SESSION_KEY, sessionId);
    localStorage.setItem(ONBOARDED_KEY, "1");
    setLeaving(true);
    setTimeout(onDone, 380);
  }, [onDone, sessionId]);

  const submit = useCallback(async () => {
    const text = input.trim();
    if (!text || thinking) return;
    setInput("");
    setSendError(false);
    setThinking(true);
    setExchanges((prev) =>
      prev.map((list, i) =>
        i === step ? [...list, { user: text, reply: null, facts: [] }] : list,
      ),
    );
    try {
      const res = await onboardingTurn(sessionId, text, QUESTIONS[step]);
      if (!sessionId && res.session_id) setSessionId(res.session_id);
      setExchanges((prev) =>
        prev.map((list, i) =>
          i === step
            ? list.map((e, j) =>
                j === list.length - 1
                  ? { ...e, reply: res.reply, facts: res.written ?? [] }
                  : e,
              )
            : list,
        ),
      );
    } catch {
      // fail soft — drop the in-flight exchange and restore the words typed
      setExchanges((prev) =>
        prev.map((list, i) => (i === step ? list.slice(0, -1) : list)),
      );
      setInput(text);
      setSendError(true);
    } finally {
      setThinking(false);
    }
  }, [input, thinking, sessionId, step]);

  const next = useCallback(() => {
    setSendError(false);
    setInput("");
    setStep((s) => s + 1);
  }, []);

  const startWatch = useCallback(async () => {
    const task = exchanges[WATCH_QUESTION]?.[0]?.user;
    if (!task || watchState === "starting" || watchState === "started") return;
    setWatchState("starting");
    try {
      await createWatch(task);
      setWatchState("started");
    } catch {
      setWatchState("idle"); // fail soft — button stays available
    }
  }, [exchanges, watchState]);

  const onFinal = step >= QUESTIONS.length;
  const stepExchanges = onFinal ? [] : exchanges[step];
  const hasExchange = stepExchanges.some((e) => e.reply !== null);
  const allFacts = exchanges.flat().flatMap((e) => e.facts);

  // Keep the newest exchange in view as the conversation grows.
  const bottomRef = useRef<HTMLDivElement>(null);
  const exchangeCount = stepExchanges.length;
  useEffect(() => {
    if (exchangeCount > 0) {
      bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }
  }, [exchangeCount, thinking]);

  return (
    <div
      className={`fixed inset-0 z-50 flex flex-col items-center justify-center bg-bg px-6 ${
        leaving ? "animate-fade-out" : "animate-fade-in"
      }`}
    >
      {/* wordmark */}
      <div className="absolute top-8 flex items-center gap-2">
        <span className="h-2 w-2 rounded-full bg-moss" aria-hidden />
        <span className="text-sm font-semibold tracking-tight text-ink">
          Gardener
        </span>
      </div>

      <div className="w-full max-w-xl">
        <AnimatePresence mode="wait" initial={false}>
          {!onFinal ? (
            <motion.div
              key={step}
              initial={{ opacity: 0, y: 16 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -16 }}
              transition={{ duration: 0.3, ease: EASE_OUT }}
            >
              {/* progress dots */}
              <div className="mb-10 flex items-center gap-2">
                {QUESTIONS.map((_, i) => (
                  <motion.span
                    key={i}
                    animate={{
                      width: i === step ? 20 : 6,
                      backgroundColor:
                        i === step
                          ? "#587a4e"
                          : i < step
                            ? "rgba(88, 122, 78, 0.4)"
                            : "#e9e8e3",
                    }}
                    transition={{ duration: 0.3, ease: EASE_OUT }}
                    className="h-1.5 rounded-full"
                    style={{ width: 6 }}
                    aria-hidden
                  />
                ))}
              </div>

              {/* the hook — only on the first step */}
              {step === 0 && (
                <div className="mb-7">
                  <p className="text-[1.7rem] font-semibold leading-tight tracking-tight text-ink">
                    Welcome to Gardener — the agent harness made for you.
                  </p>
                  <p className="mt-3 text-sm leading-relaxed text-faint">{INTRO}</p>
                </div>
              )}

              {/* Gardener asking */}
              <p className="text-[1.45rem] font-medium leading-snug tracking-tight text-ink">
                {QUESTIONS[step]}
              </p>

              {/* the conversation so far on this question */}
              {stepExchanges.length > 0 && (
                <div className="mt-8 flex max-h-[44vh] flex-col gap-6 overflow-y-auto pr-1">
                  {stepExchanges.map((e, i) => (
                    <ExchangeView key={i} exchange={e} />
                  ))}
                  <div ref={bottomRef} />
                </div>
              )}

              {/* composer — always available, so each step can be a real exchange */}
              <div className="mt-8">
                {sendError && (
                  <p className="mb-2 px-1 text-[11px] text-amber">
                    couldn&apos;t reach Gardener — your words are back in the
                    box, try again
                  </p>
                )}
                <div className="rounded-xl border border-edge bg-bg shadow-sm transition-colors focus-within:border-moss/50">
                  <textarea
                    key={step}
                    autoFocus
                    rows={hasExchange ? 2 : 3}
                    value={input}
                    onChange={(e) => setInput(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" && !e.shiftKey) {
                        e.preventDefault();
                        submit();
                      }
                    }}
                    placeholder={
                      hasExchange
                        ? "Say more, or ask Gardener something…"
                        : "Write a little — Gardener listens, answers, and plants the durable parts."
                    }
                    className="block w-full resize-none bg-transparent px-4 py-3.5 text-[15px] leading-relaxed text-ink outline-none placeholder:text-dim"
                  />
                  <div className="flex items-center justify-between px-4 pb-3">
                    <span className="text-[11px] text-dim">
                      Enter to send · Shift+Enter for a new line
                    </span>
                    <button
                      onClick={submit}
                      disabled={input.trim() === "" || thinking}
                      className="rounded-lg bg-moss px-4 py-1.5 text-xs font-medium text-white transition-colors hover:bg-moss-deep disabled:opacity-40"
                    >
                      Send
                    </button>
                  </div>
                </div>

                {/* once Gardener has spoken, the path forward opens */}
                <AnimatePresence>
                  {hasExchange && (
                    <motion.div
                      initial={{ opacity: 0, y: 6 }}
                      animate={{ opacity: 1, y: 0 }}
                      exit={{ opacity: 0 }}
                      transition={{ duration: 0.25, ease: EASE_OUT }}
                      className="mt-5 flex items-center gap-3"
                    >
                      <button
                        onClick={next}
                        disabled={thinking}
                        className="rounded-lg bg-moss px-4 py-2 text-xs font-medium text-white transition-colors hover:bg-moss-deep disabled:opacity-50"
                      >
                        Continue
                      </button>
                      {step === WATCH_QUESTION &&
                        (watchState === "started" ? (
                          <span className="flex items-center gap-1.5 text-xs text-moss">
                            <span
                              className="h-1.5 w-1.5 rounded-full bg-moss"
                              aria-hidden
                            />
                            Watch started — it&apos;s growing in your sidebar
                          </span>
                        ) : (
                          <button
                            onClick={startWatch}
                            disabled={watchState === "starting"}
                            className="rounded-lg border border-moss/40 px-4 py-2 text-xs font-medium text-moss transition-colors hover:bg-moss/10 disabled:opacity-50"
                          >
                            {watchState === "starting"
                              ? "Starting…"
                              : "Start this watch"}
                          </button>
                        ))}
                    </motion.div>
                  )}
                </AnimatePresence>
              </div>
            </motion.div>
          ) : (
            <motion.div
              key="final"
              initial={{ opacity: 0, y: 16 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.3, ease: EASE_OUT }}
            >
              <p className="text-2xl font-medium tracking-tight text-ink">
                Your garden is planted.
              </p>
              <p className="mt-2 text-sm text-faint">
                {allFacts.length > 0
                  ? `Gardener wrote ${allFacts.length} ${
                      allFacts.length === 1 ? "fact" : "facts"
                    } to your vault${
                      watchState === "started" ? " and started a watch" : ""
                    }. It tends them from here.`
                  : "Nothing written yet — Gardener will plant as you talk."}
              </p>

              {allFacts.length > 0 && (
                <div className="mt-7 flex max-h-[40vh] flex-wrap gap-2 overflow-y-auto">
                  {allFacts.map((f, i) => (
                    <FactChip key={i} fact={f} index={i * 0.7} />
                  ))}
                </div>
              )}

              <motion.button
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ duration: 0.3, delay: 0.25 }}
                autoFocus
                onClick={finish}
                className="mt-9 rounded-lg bg-moss px-5 py-2.5 text-sm font-medium text-white transition-colors hover:bg-moss-deep"
              >
                Enter the garden
              </motion.button>
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      {/* skip, always available */}
      {!onFinal && (
        <button
          onClick={finish}
          className="absolute bottom-8 text-xs text-dim transition-colors hover:text-faint"
        >
          Skip — start bare
        </button>
      )}
    </div>
  );
}
