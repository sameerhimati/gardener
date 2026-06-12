"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { distill, onboardingTurn, type PlantedFact } from "@/lib/api";
import { Markdown } from "@/lib/markdown";
import ThinkingDots from "@/components/ThinkingDots";
import GardenEntrance from "@/components/GardenEntrance";

export const ONBOARDED_KEY = "gardener_onboarded";
// Must match MAIN_SESSION_KEY in ChatPane — carrying the onboarding session here
// makes the main chat continue the same conversation (no "Nothing planted yet").
const MAIN_SESSION_KEY = "gardener_main_session_id";

// One light touch of the garden metaphor for brand — the rest is plain.
const TAGLINE = "An agent whose memory takes care of itself.";

/* ── interest starting points ──────────────────────────────────────────────
   Each chip is a real starting intent. Selecting one seeds a standing watch
   (the agent spawns it from the text). The first group is the demo persona's
   world; the second is general so it never looks hardcoded to one user.

   `prompt` is a function of the entered zip so location-dependent chips
   (homes, apartments, weather, anything "near me") inject the real zip the
   user typed in basics — "near me" actually means their place, not the seed
   persona's. When no zip was entered, fall back to the generic phrasing. */
interface Interest {
  label: string; // short chip text
  prompt: (zip: string) => string; // actual intent sent to the agent; zip is "" if none
}

// "houses near me" → "houses near 77005" when a zip is known, else generic.
const nearZip = (zip: string, withZip: string, generic: string) =>
  zip ? withZip.replace("{zip}", zip) : generic;

const INTERESTS_PERSONAL: Interest[] = [
  {
    label: "Houses near me",
    prompt: (zip) =>
      nearZip(
        zip,
        "Watch Zillow for houses near {zip}",
        "Watch Zillow for houses in my neighborhood",
      ),
  },
  {
    label: "Weather near me",
    prompt: (zip) =>
      nearZip(
        zip,
        "Watch the weather in {zip} and warn me about anything notable",
        "Watch my local weather and warn me about anything notable",
      ),
  },
  { label: "GPU deals", prompt: () => "Track GPU prices and tell me about deals under $500" },
  { label: "What I'm reading", prompt: () => "Keep notes on what I'm reading" },
  { label: "AI agent research", prompt: () => "Follow new research on AI agents" },
];

const INTERESTS_GENERAL: Interest[] = [
  { label: "Flight status", prompt: () => "Track a flight's status and tell me about delays or gate changes" },
  { label: "Flight deals", prompt: () => "Find flight deals to a place I want to go" },
  { label: "Package tracking", prompt: () => "Track a package and tell me when it's out for delivery" },
  { label: "Concert tickets", prompt: () => "Alert me when concert tickets I care about drop" },
  { label: "Price drop", prompt: () => "Watch a product and tell me when the price drops" },
  { label: "Back in stock", prompt: () => "Watch a product until it's back in stock" },
  { label: "News on a topic", prompt: () => "Summarize news on a topic I care about" },
  { label: "A stock or crypto", prompt: () => "Track a stock or crypto for me" },
  {
    label: "Apartments near me",
    prompt: (zip) =>
      nearZip(
        zip,
        "Find apartments near {zip} within a budget",
        "Find apartments under a budget",
      ),
  },
];

/** One user↔Gardener exchange inside a step. `reply: null` = in flight. */
interface Exchange {
  user: string;
  reply: string | null;
  facts: PlantedFact[];
}

const EASE_OUT: [number, number, number, number] = [0.2, 0.7, 0.3, 1];

// Step indices — named so the conditional flow stays readable.
const STEP_CONCEPT = 0;
const STEP_BASICS = 1;
const STEP_INTERESTS = 2;
const STEP_ACTIVE = 3;
const STEP_FINAL = 4;
const STEP_COUNT = STEP_FINAL; // dots cover concept..active (final has none)

/** A planted fact, rendered as a pill. Tap to correct the extracted text
 *  inline before it's the version that sticks — confirming re-plants the
 *  corrected fact into the vault (`onCommit`). If no `onCommit` is given the
 *  pill is read-only (e.g. the final summary just mirrors what was planted). */
function FactChip({
  fact,
  index,
  onCommit,
}: {
  fact: PlantedFact;
  index: number;
  onCommit?: (corrected: string) => void;
}) {
  const editable = Boolean(onCommit);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(fact.fact);
  const inputRef = useRef<HTMLInputElement>(null);

  const startEdit = () => {
    if (!editable) return;
    setDraft(fact.fact);
    setEditing(true);
  };

  const commit = () => {
    const next = draft.trim();
    setEditing(false);
    if (next && next !== fact.fact) onCommit?.(next);
  };

  useEffect(() => {
    if (editing) {
      inputRef.current?.focus();
      inputRef.current?.select();
    }
  }, [editing]);

  return (
    <motion.span
      initial={{ opacity: 0, scale: 0.85, y: 5 }}
      animate={{ opacity: 1, scale: 1, y: 0 }}
      transition={{ duration: 0.3, ease: EASE_OUT, delay: index * 0.06 }}
      className={`inline-flex max-w-full items-center gap-2 rounded-full border border-moss/25 bg-moss/10 px-3 py-1.5 text-xs text-moss-deep ${
        editable && !editing ? "cursor-text hover:border-moss/45" : ""
      }`}
    >
      <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-moss" aria-hidden />
      {editing ? (
        <span className="inline-flex items-center gap-1.5">
          <span className="font-medium">{fact.topic}</span>
          <span className="text-moss-deep/60">—</span>
          <input
            ref={inputRef}
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                commit();
              } else if (e.key === "Escape") {
                e.preventDefault();
                setEditing(false);
              }
            }}
            onBlur={commit}
            className="min-w-[8ch] max-w-[40ch] rounded-md border border-moss/40 bg-bg px-1.5 py-0.5 text-xs text-ink outline-none focus:border-moss"
            style={{ width: `${Math.max(draft.length, 8) + 2}ch` }}
          />
        </span>
      ) : (
        <button
          type="button"
          onClick={startEdit}
          disabled={!editable}
          title={editable ? "Tap to correct" : undefined}
          className="truncate text-left disabled:cursor-default"
        >
          <span className="font-medium">{fact.topic}</span>
          <span className="text-moss-deep/60"> — </span>
          {fact.fact}
        </button>
      )}
    </motion.span>
  );
}

function ExchangeView({
  exchange,
  onEditFact,
}: {
  exchange: Exchange;
  onEditFact: (factIndex: number, corrected: string) => void;
}) {
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
                <FactChip
                  key={i}
                  fact={f}
                  index={i}
                  onCommit={(corrected) => onEditFact(i, corrected)}
                />
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}

export default function Onboarding({ onDone }: { onDone: () => void }) {
  const [step, setStep] = useState(STEP_CONCEPT);
  const [sessionId, setSessionId] = useState<string | null>(null);

  // basics
  const [name, setName] = useState("");
  const [zip, setZip] = useState("");

  // interest + active-question conversations (real agent exchanges)
  const [interestExchanges, setInterestExchanges] = useState<Exchange[]>([]);
  const [activeExchanges, setActiveExchanges] = useState<Exchange[]>([]);
  const [chosen, setChosen] = useState<Set<string>>(new Set()); // chip prompts already seeded

  const [input, setInput] = useState("");
  const [thinking, setThinking] = useState(false);
  const [sendError, setSendError] = useState(false);
  const [savingBasics, setSavingBasics] = useState(false);
  const [leaving, setLeaving] = useState(false);
  const [entering, setEntering] = useState(false); // garden-entrance flourish playing

  // Persist state, then bail straight out (used by the "Skip setup" escape hatch).
  const skipOut = useCallback(() => {
    // Carry the onboarding session into the main chat so the conversation +
    // planted facts are already there (only if they actually talked).
    if (sessionId) localStorage.setItem(MAIN_SESSION_KEY, sessionId);
    localStorage.setItem(ONBOARDED_KEY, "1");
    setLeaving(true);
    setTimeout(onDone, 380);
  }, [onDone, sessionId]);

  // The celebratory way in: persist, then play the garden-entrance animation,
  // which calls onDone when it finishes lifting away.
  const finish = useCallback(() => {
    if (sessionId) localStorage.setItem(MAIN_SESSION_KEY, sessionId);
    localStorage.setItem(ONBOARDED_KEY, "1");
    setEntering(true);
  }, [sessionId]);

  /** Run one real agent exchange for the current step (interests or active). */
  const runTurn = useCallback(
    async (text: string, question: string, isInterests: boolean) => {
      const setList = isInterests ? setInterestExchanges : setActiveExchanges;
      setSendError(false);
      setThinking(true);
      setList((prev) => [...prev, { user: text, reply: null, facts: [] }]);
      try {
        const res = await onboardingTurn(sessionId, text, question);
        if (!sessionId && res.session_id) setSessionId(res.session_id);
        setList((prev) =>
          prev.map((e, j) =>
            j === prev.length - 1
              ? { ...e, reply: res.reply, facts: res.written ?? [] }
              : e,
          ),
        );
      } catch {
        // fail soft — drop the in-flight exchange, restore the typed words
        setList((prev) => prev.slice(0, -1));
        if (!isInterests || input === "") setInput(text);
        setSendError(true);
      } finally {
        setThinking(false);
      }
    },
    [sessionId, input],
  );

  // Correct a planted fact: update the pill text in place, then re-plant the
  // corrected wording into the vault so the saved version matches what's shown.
  // `step` tells us which conversation the edited exchange belongs to.
  const editFact = useCallback(
    (isInterests: boolean, exchangeIndex: number, factIndex: number, corrected: string) => {
      const setList = isInterests ? setInterestExchanges : setActiveExchanges;
      let topic = "";
      setList((prev) =>
        prev.map((e, ei) => {
          if (ei !== exchangeIndex) return e;
          return {
            ...e,
            facts: e.facts.map((f, fi) => {
              if (fi !== factIndex) return f;
              topic = f.topic;
              return { ...f, fact: corrected };
            }),
          };
        }),
      );
      // re-plant the corrected wording (fail soft — UI already reflects the fix)
      const phrasing = topic ? `${topic}: ${corrected}` : corrected;
      void distill(phrasing, "onboarding").catch(() => {});
    },
    [],
  );

  // composer submit, routed to whichever conversational step we're on
  const submit = useCallback(() => {
    const text = input.trim();
    if (!text || thinking) return;
    setInput("");
    const isInterests = step === STEP_INTERESTS;
    const question = isInterests
      ? "What would you like Gardener to keep an eye on?"
      : "What are you actively looking for or deciding on right now?";
    void runTurn(text, question, isInterests);
  }, [input, thinking, step, runTurn]);

  // tapping an interest chip seeds a real intent through the agent.
  // The prompt is built from the entered zip, so "near me" chips (homes,
  // apartments, weather) carry the user's real location, not the seed persona's.
  const pickInterest = useCallback(
    (intent: Interest) => {
      if (thinking || chosen.has(intent.label)) return;
      setChosen((prev) => new Set(prev).add(intent.label));
      void runTurn(
        intent.prompt(zip.trim()),
        "What would you like Gardener to keep an eye on?",
        true,
      );
    },
    [thinking, chosen, runTurn, zip],
  );

  // save name + zip into the vault, then advance
  const saveBasicsAndNext = useCallback(async () => {
    const trimmedName = name.trim();
    const trimmedZip = zip.trim();
    if (savingBasics) return;
    const parts: string[] = [];
    if (trimmedName) parts.push(`My name is ${trimmedName}.`);
    if (trimmedZip) parts.push(`My zip code is ${trimmedZip}.`);
    if (parts.length > 0) {
      setSavingBasics(true);
      try {
        await distill(parts.join(" "), "onboarding");
      } catch {
        // fail soft — the basics aren't load-bearing, keep moving
      } finally {
        setSavingBasics(false);
      }
    }
    setSendError(false);
    setStep(STEP_INTERESTS);
  }, [name, zip, savingBasics]);

  const next = useCallback(() => {
    setSendError(false);
    setInput("");
    setStep((s) => s + 1);
  }, []);

  // ── conditional progression ──────────────────────────────────────────────
  // If the interests step already produced rich exchanges, the "active" step is
  // redundant — skip straight to the finish. Otherwise ask the one open question.
  const interestsAnswered = interestExchanges.some((e) => e.reply !== null);
  const afterInterests = useCallback(() => {
    setInput("");
    setSendError(false);
    setStep(interestsAnswered ? STEP_FINAL : STEP_ACTIVE);
  }, [interestsAnswered]);

  // facts gathered across the whole flow, for the final summary
  const allFacts = useMemo(
    () =>
      [...interestExchanges, ...activeExchanges].flatMap((e) => e.facts),
    [interestExchanges, activeExchanges],
  );

  const onFinal = step === STEP_FINAL;
  const stepExchanges =
    step === STEP_INTERESTS
      ? interestExchanges
      : step === STEP_ACTIVE
        ? activeExchanges
        : [];
  const hasExchange = stepExchanges.some((e) => e.reply !== null);

  // Keep the newest exchange in view as the conversation grows.
  const bottomRef = useRef<HTMLDivElement>(null);
  const exchangeCount = stepExchanges.length;
  useEffect(() => {
    if (exchangeCount > 0) {
      bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }
  }, [exchangeCount, thinking]);

  // Walking-into-the-garden flourish takes over the screen on the way out.
  if (entering) return <GardenEntrance onDone={onDone} />;

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
              {/* progress dots — concept · basics · interests · active */}
              <div className="mb-10 flex items-center gap-2">
                {Array.from({ length: STEP_COUNT }).map((_, i) => (
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

              {/* ── step 0: what a Harness actually is ───────────────────── */}
              {step === STEP_CONCEPT && (
                <div>
                  <p className="text-[1.7rem] font-semibold leading-tight tracking-tight text-ink">
                    Your harness, built around you.
                  </p>
                  <div className="mt-4 space-y-3 text-[15px] leading-relaxed text-faint">
                    <p>
                      You might think &ldquo;harness&rdquo; means a coding
                      assistant. Here it means something different: an agent
                      shaped around{" "}
                      <span className="text-ink">your</span>
                      {" life — what you're looking for, what you want watched, what you want remembered."}
                    </p>
                    <p>
                      No two harnesses are alike, because no two people are. The
                      next minute is about teaching yours who you are. {TAGLINE}
                    </p>
                  </div>

                  <button
                    onClick={next}
                    autoFocus
                    className="group mt-8 inline-flex items-center gap-2 rounded-lg bg-moss px-5 py-2.5 text-sm font-medium text-white transition-colors hover:bg-moss-deep"
                  >
                    Get started
                    <span
                      className="transition-transform group-hover:translate-x-0.5"
                      aria-hidden
                    >
                      →
                    </span>
                  </button>
                </div>
              )}

              {/* ── step 1: the basics ───────────────────────────────────── */}
              {step === STEP_BASICS && (
                <div>
                  <p className="text-[1.45rem] font-medium leading-snug tracking-tight text-ink">
                    First, the basics.
                  </p>
                  <p className="mt-2 text-sm leading-relaxed text-faint">
                    Just enough to make the agent yours. Skip anything you&apos;d
                    rather not share.
                  </p>

                  <div className="mt-7 space-y-5">
                    <div>
                      <label className="mb-1.5 block text-xs font-medium text-faint">
                        What should I call you?
                      </label>
                      <input
                        autoFocus
                        value={name}
                        onChange={(e) => setName(e.target.value)}
                        onKeyDown={(e) => {
                          if (e.key === "Enter") saveBasicsAndNext();
                        }}
                        placeholder="Your name"
                        className="w-full rounded-xl border border-edge bg-bg px-4 py-3 text-[15px] text-ink outline-none transition-colors focus:border-moss/50 placeholder:text-dim"
                      />
                    </div>

                    <div>
                      <label className="mb-1.5 block text-xs font-medium text-faint">
                        Zip code{" "}
                        <span className="font-normal text-dim">
                          — so local watches (homes, events, weather) know where
                          &ldquo;near me&rdquo; is
                        </span>
                      </label>
                      <input
                        value={zip}
                        onChange={(e) =>
                          setZip(e.target.value.replace(/[^0-9]/g, "").slice(0, 5))
                        }
                        onKeyDown={(e) => {
                          if (e.key === "Enter") saveBasicsAndNext();
                        }}
                        inputMode="numeric"
                        placeholder="Optional — e.g. 77005"
                        className="w-full rounded-xl border border-edge bg-bg px-4 py-3 text-[15px] text-ink outline-none transition-colors focus:border-moss/50 placeholder:text-dim"
                      />
                    </div>
                  </div>

                  <button
                    onClick={saveBasicsAndNext}
                    disabled={savingBasics}
                    className="mt-7 inline-flex items-center gap-2 rounded-lg bg-moss px-5 py-2.5 text-sm font-medium text-white transition-colors hover:bg-moss-deep disabled:opacity-50"
                  >
                    {savingBasics ? "Saving…" : "Continue"}
                  </button>
                </div>
              )}

              {/* ── step 2: interests (chips + freeform) ──────────────────── */}
              {step === STEP_INTERESTS && (
                <div>
                  <p className="text-[1.45rem] font-medium leading-snug tracking-tight text-ink">
                    {name ? `Nice to meet you, ${name}. ` : ""}What should I keep
                    an eye on?
                  </p>
                  <p className="mt-2 text-sm leading-relaxed text-faint">
                    Tap any that fit — I&apos;ll set them up live. Or type your
                    own; these are just starting points.
                  </p>

                  {/* selectable starting points */}
                  <div className="mt-6 flex flex-wrap gap-2">
                    {[...INTERESTS_PERSONAL, ...INTERESTS_GENERAL].map((it) => {
                      const picked = chosen.has(it.label);
                      return (
                        <button
                          key={it.label}
                          onClick={() => pickInterest(it)}
                          disabled={thinking || picked}
                          title={it.prompt(zip.trim())}
                          className={`rounded-full border px-3.5 py-1.5 text-xs font-medium transition-colors disabled:cursor-default ${
                            picked
                              ? "border-moss/40 bg-moss/10 text-moss-deep"
                              : "border-edge text-faint hover:border-moss/50 hover:text-moss disabled:opacity-50"
                          }`}
                        >
                          {picked && (
                            <span className="mr-1.5 text-moss" aria-hidden>
                              ✓
                            </span>
                          )}
                          {it.label}
                        </button>
                      );
                    })}
                  </div>

                  {/* the conversation as the agent sets things up */}
                  {stepExchanges.length > 0 && (
                    <div className="mt-7 flex max-h-[34vh] flex-col gap-6 overflow-y-auto pr-1">
                      {stepExchanges.map((e, i) => (
                        <ExchangeView
                          key={i}
                          exchange={e}
                          onEditFact={(factIndex, corrected) =>
                            editFact(true, i, factIndex, corrected)
                          }
                        />
                      ))}
                      <div ref={bottomRef} />
                    </div>
                  )}

                  {/* freeform composer */}
                  <div className="mt-7">
                    {sendError && (
                      <p className="mb-2 px-1 text-[11px] text-amber">
                        couldn&apos;t reach Gardener — try that again
                      </p>
                    )}
                    <div className="rounded-xl border border-edge bg-bg shadow-sm transition-colors focus-within:border-moss/50">
                      <textarea
                        rows={2}
                        value={input}
                        onChange={(e) => setInput(e.target.value)}
                        onKeyDown={(e) => {
                          if (e.key === "Enter" && !e.shiftKey) {
                            e.preventDefault();
                            submit();
                          }
                        }}
                        placeholder="Or describe something in your own words…"
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

                    {/* advance once at least one thing is set up */}
                    <div className="mt-5 flex items-center gap-3">
                      <button
                        onClick={afterInterests}
                        disabled={thinking}
                        className="rounded-lg bg-moss px-4 py-2 text-xs font-medium text-white transition-colors hover:bg-moss-deep disabled:opacity-50"
                      >
                        {hasExchange ? "Continue" : "Skip this for now"}
                      </button>
                      {thinking && (
                        <span className="text-[11px] text-dim">
                          setting that up…
                        </span>
                      )}
                    </div>
                  </div>
                </div>
              )}

              {/* ── step 3: one open question (conditionally reached) ─────── */}
              {step === STEP_ACTIVE && (
                <div>
                  <p className="text-[1.45rem] font-medium leading-snug tracking-tight text-ink">
                    Anything you&apos;re actively deciding on right now?
                  </p>
                  <p className="mt-2 text-sm leading-relaxed text-faint">
                    A purchase, a move, a trip — whatever&apos;s on your mind.
                    I&apos;ll remember it. Optional.
                  </p>

                  {stepExchanges.length > 0 && (
                    <div className="mt-7 flex max-h-[40vh] flex-col gap-6 overflow-y-auto pr-1">
                      {stepExchanges.map((e, i) => (
                        <ExchangeView
                          key={i}
                          exchange={e}
                          onEditFact={(factIndex, corrected) =>
                            editFact(false, i, factIndex, corrected)
                          }
                        />
                      ))}
                      <div ref={bottomRef} />
                    </div>
                  )}

                  <div className="mt-7">
                    {sendError && (
                      <p className="mb-2 px-1 text-[11px] text-amber">
                        couldn&apos;t reach Gardener — try that again
                      </p>
                    )}
                    <div className="rounded-xl border border-edge bg-bg shadow-sm transition-colors focus-within:border-moss/50">
                      <textarea
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
                        placeholder="e.g. deciding between two apartments by end of month…"
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

                    <div className="mt-5">
                      <button
                        onClick={() => setStep(STEP_FINAL)}
                        disabled={thinking}
                        className="rounded-lg bg-moss px-4 py-2 text-xs font-medium text-white transition-colors hover:bg-moss-deep disabled:opacity-50"
                      >
                        {hasExchange ? "Done" : "Skip — I'm set"}
                      </button>
                    </div>
                  </div>
                </div>
              )}
            </motion.div>
          ) : (
            <motion.div
              key="final"
              initial={{ opacity: 0, y: 16 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.3, ease: EASE_OUT }}
            >
              <p className="text-2xl font-medium tracking-tight text-ink">
                You&apos;re all set{name ? `, ${name}` : ""}.
              </p>
              <p className="mt-2 text-sm text-faint">
                {allFacts.length > 0
                  ? `I saved ${allFacts.length} ${
                      allFacts.length === 1 ? "thing" : "things"
                    } about you. You can read and correct any of it anytime — it lives in your vault.`
                  : "Nothing saved yet — I'll remember things as we talk."}
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
                Open Gardener
              </motion.button>
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      {/* skip, always available */}
      {!onFinal && (
        <button
          onClick={skipOut}
          className="absolute bottom-8 text-xs text-dim transition-colors hover:text-faint"
        >
          Skip setup
        </button>
      )}
    </div>
  );
}
