import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  title: "Gardener — an agent whose memory takes care of itself",
  description:
    "Chat with one agent that acts on the open web. Set standing watches that run as steerable subagent chats. Steering distills into a plain-markdown memory a background lint agent keeps honest — contradictions caught, fixes applied, corrections published.",
};

/* Standalone marketing route at /landing. Self-contained, presentational only.
   Reuses the app palette (moss accent, ink on near-white) and Geist type from
   the root layout. The root <body> is overflow-hidden, so this page owns its
   own scroll container. No backend calls. */

const ACCENT = "text-moss";

function Eyebrow({ children }: { children: React.ReactNode }) {
  return (
    <p className="font-mono text-[11px] uppercase tracking-[0.18em] text-dim">
      {children}
    </p>
  );
}

/* A small, hand-drawn moss sprig — the page's one piece of identity art,
   echoing the SVG garden the app opens with. Used as a quiet section marker. */
function Sprig({ className = "" }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      className={className}
      fill="none"
      aria-hidden="true"
    >
      <path
        d="M12 22 V8"
        stroke="var(--color-moss)"
        strokeWidth="1.6"
        strokeLinecap="round"
      />
      <path
        d="M12 13 C8 12 6 9 6 6 C9 6 11 8 12 11"
        stroke="var(--color-moss)"
        strokeWidth="1.6"
        strokeLinecap="round"
        fill="none"
      />
      <path
        d="M12 16 C16 15 18 12 18 9 C15 9 13 11 12 14"
        stroke="var(--color-moss)"
        strokeWidth="1.6"
        strokeLinecap="round"
        fill="none"
      />
    </svg>
  );
}

function Feature({
  index,
  kicker,
  title,
  body,
  children,
}: {
  index: string;
  kicker: string;
  title: string;
  body: string;
  children: React.ReactNode;
}) {
  return (
    <section className="grid gap-10 border-t border-edge py-16 md:grid-cols-12 md:gap-12">
      <div className="md:col-span-5">
        <div className="flex items-baseline gap-3">
          <span className="font-mono text-sm text-moss">{index}</span>
          <Eyebrow>{kicker}</Eyebrow>
        </div>
        <h3 className="mt-4 text-2xl font-semibold tracking-tight text-ink md:text-[28px] md:leading-snug">
          {title}
        </h3>
        <p className="mt-4 max-w-md text-[15px] leading-relaxed text-faint">
          {body}
        </p>
      </div>
      <div className="md:col-span-7">{children}</div>
    </section>
  );
}

/* A faux chat exchange — shows the steerable subagent feel without any JS. */
function Bubble({
  who,
  tone = "them",
  children,
}: {
  who: string;
  tone?: "you" | "them";
  children: React.ReactNode;
}) {
  return (
    <div className="flex flex-col gap-1">
      <span className="font-mono text-[10px] uppercase tracking-wide text-dim">
        {who}
      </span>
      <div
        className={
          tone === "you"
            ? "self-start rounded-lg rounded-tl-sm border border-edge bg-surface px-3.5 py-2.5 text-[13px] leading-relaxed text-ink"
            : "self-start rounded-lg rounded-tl-sm border border-moss/30 bg-moss/[0.07] px-3.5 py-2.5 text-[13px] leading-relaxed text-ink"
        }
      >
        {children}
      </div>
    </div>
  );
}

export default function LandingPage() {
  return (
    <main className="h-dvh overflow-y-auto bg-bg font-sans text-ink">
      {/* top hairline / wordmark */}
      <div className="mx-auto flex max-w-5xl items-center justify-between px-6 pt-7">
        <div className="flex items-center gap-2.5">
          <Sprig className="h-5 w-5" />
          <span className="text-sm font-semibold tracking-tight">Gardener</span>
        </div>
        <Link
          href="/"
          className="font-mono text-[12px] text-faint transition-colors hover:text-moss"
        >
          open app →
        </Link>
      </div>

      {/* ───────────────────────── hero ───────────────────────── */}
      <section className="mx-auto max-w-5xl px-6 pb-20 pt-20 md:pt-28">
        <Eyebrow>self-maintaining memory</Eyebrow>
        <h1 className="mt-5 max-w-3xl text-balance text-4xl font-semibold leading-[1.07] tracking-tight md:text-[58px] md:leading-[1.04]">
          An agent whose memory{" "}
          <span className={ACCENT}>gardens itself.</span>
        </h1>
        <p className="mt-7 max-w-xl text-pretty text-lg leading-relaxed text-faint">
          Most agents forget, or quietly rot — old preferences linger,
          contradictions pile up, no one prunes. Gardener treats memory as a
          living thing. You chat, you steer, and a background gardener keeps the
          record clean, current, and honest enough to cite.
        </p>

        <div className="mt-9 flex flex-wrap items-center gap-4">
          <Link
            href="/"
            className="rounded-md bg-moss px-5 py-2.5 text-sm font-medium text-white shadow-sm transition-colors hover:bg-moss-deep"
          >
            Enter the garden
          </Link>
          <Link
            href="#how"
            className="rounded-md border border-edge px-5 py-2.5 text-sm font-medium text-faint transition-colors hover:border-moss/50 hover:text-moss"
          >
            See how it works
          </Link>
        </div>

        <p className="mt-6 font-mono text-[12px] text-dim">
          one agent · standing watches · a markdown vault that tends itself
        </p>
      </section>

      {/* ─────────────────────── features ─────────────────────── */}
      <div className="mx-auto max-w-5xl px-6">
        <Feature
          index="01"
          kicker="the main agent"
          title="One agent you chat with — and it actually acts on the web."
          body="Not a search box that hands you links. Gardener searches, fetches pages, and takes real actions on the open web — the same conversation that answers you is the one that does the work."
        >
          <div className="flex flex-col gap-3 rounded-xl border border-edge bg-surface p-5">
            <Bubble who="you" tone="you">
              Find the cheapest GPU under $500 with 16GB+ and watch for restocks.
            </Bubble>
            <Bubble who="gardener">
              Searching three retailers now. I'll stand up a watch for restocks
              and drop a calendar hold the moment one lands.
            </Bubble>
            <div className="flex items-center gap-2 pl-1 pt-1">
              <span className="inline-block h-1.5 w-1.5 rounded-full bg-moss animate-cycle-pulse" />
              <span className="font-mono text-[11px] text-dim">
                acting · live on the open web
              </span>
            </div>
          </div>
        </Feature>

        <Feature
          index="02"
          kicker="standing watches"
          title="Watches run as their own chats — open one and steer it mid-task."
          body="Ask Gardener to “watch Zillow for houses in my neighborhood” and that watch becomes a live subagent conversation. Pop it open, narrow it (“only 3+ bedrooms”), and it adjusts on the next cycle. On a real match, it acts — a calendar event, a Discord post — not just a notification."
        >
          <div className="overflow-hidden rounded-xl border border-edge bg-surface">
            <div className="flex items-center justify-between border-b border-edge px-4 py-2.5">
              <div className="flex items-center gap-2">
                <span className="inline-block h-1.5 w-1.5 rounded-full bg-moss animate-cycle-pulse" />
                <span className="text-[13px] font-medium text-ink">
                  watch · zillow / 77005
                </span>
              </div>
              <span className="font-mono text-[10px] uppercase tracking-wide text-dim">
                cycle 14
              </span>
            </div>
            <div className="flex flex-col gap-3 p-4">
              <Bubble who="you" tone="you">
                Only 3+ bedrooms, 1500+ sqft.
              </Bubble>
              <Bubble who="watch">
                Tightened the filter. Re-scanning 12 active listings — 2 still
                qualify.
              </Bubble>
              <Bubble who="watch">
                Match: 4bd / 1,820 sqft, $612k. Added a tour hold to your
                calendar and posted it to #house-hunt.
              </Bubble>
            </div>
          </div>
        </Feature>

        <Feature
          index="03"
          kicker="self-linting memory"
          title="Your steering becomes plain markdown — that a lint agent keeps honest."
          body="Every preference you express lands in a vault you can read and edit by hand. A background lint agent watches that vault against the event log: it catches contradictions and staleness, proposes diffs with receipts, auto-applies the high-confidence ones, and publishes its corrections publicly to cited.md — a changelog other agents and AI search can quote."
        >
          <div className="overflow-hidden rounded-xl border border-edge bg-surface font-mono text-[12px] leading-relaxed">
            <div className="border-b border-edge px-4 py-2 text-[10px] uppercase tracking-wide text-dim">
              vault/preferences.md · lint diff
            </div>
            <div className="px-4 py-3">
              <p className="text-faint">budget ceiling:</p>
              <p className="text-rust line-through opacity-70">
                - under $500
              </p>
              <p className="text-moss">+ under $650</p>
              <p className="mt-3 text-[11px] text-dim">
                receipt: you approved a $612k match on Jun 8 (event #1043).
                contradiction caught · auto-applied · logged to cited.md
              </p>
            </div>
          </div>
        </Feature>
      </div>

      {/* ─────────────────────── the loop ─────────────────────── */}
      <section id="how" className="border-t border-edge">
        <div className="mx-auto max-w-5xl px-6 py-20">
          <div className="flex items-center gap-3">
            <Sprig className="h-5 w-5" />
            <Eyebrow>the loop that keeps it alive</Eyebrow>
          </div>
          <h2 className="mt-4 max-w-2xl text-3xl font-semibold tracking-tight text-ink md:text-[34px]">
            Memory that grows is easy. Memory that stays{" "}
            <span className={ACCENT}>true</span> is the hard part.
          </h2>

          <ol className="mt-12 grid gap-px overflow-hidden rounded-xl border border-edge bg-edge md:grid-cols-5">
            {[
              {
                n: "1",
                t: "You chat",
                d: "Tell Gardener what you want. It acts and stands up watches.",
              },
              {
                n: "2",
                t: "A watch acts",
                d: "On a real match it books, posts, or pings — then logs the event.",
              },
              {
                n: "3",
                t: "Memory grows",
                d: "Your steering distills into markdown you can read and edit.",
              },
              {
                n: "4",
                t: "Lint catches it",
                d: "The gardener spots a contradiction against the event log.",
              },
              {
                n: "5",
                t: "It publishes",
                d: "Applies the fix with receipts and posts the correction to cited.md.",
              },
            ].map((s) => (
              <li
                key={s.n}
                className="flex flex-col gap-2 bg-bg p-5"
              >
                <span className="flex h-7 w-7 items-center justify-center rounded-full bg-moss/10 font-mono text-[12px] text-moss">
                  {s.n}
                </span>
                <span className="text-[15px] font-semibold tracking-tight text-ink">
                  {s.t}
                </span>
                <span className="text-[13px] leading-relaxed text-faint">
                  {s.d}
                </span>
              </li>
            ))}
          </ol>

          <p className="mt-8 max-w-2xl text-[15px] leading-relaxed text-faint">
            The loop closes on itself. That's the whole thesis:{" "}
            <span className="text-ink">
              self-maintaining memory is what makes an agent durable
            </span>{" "}
            over months, not minutes — and a memory clean enough to publish is a
            memory you can trust.
          </p>
        </div>
      </section>

      {/* ─────────────── public gate / citeable ─────────────── */}
      <section className="border-t border-edge bg-surface">
        <div className="mx-auto max-w-5xl px-6 py-20">
          <div className="grid gap-10 md:grid-cols-12 md:gap-12">
            <div className="md:col-span-5">
              <Eyebrow>a public gate</Eyebrow>
              <h2 className="mt-4 text-3xl font-semibold tracking-tight text-ink md:text-[32px]">
                Your garden is citeable.
              </h2>
            </div>
            <div className="md:col-span-7">
              <p className="text-[15px] leading-relaxed text-faint">
                The correction changelog isn't private bookkeeping — it's
                published. Every contradiction the gardener resolves, with its
                receipt, lives at a public{" "}
                <span className="font-mono text-ink">cited.md</span> that other
                agents and AI search can read and quote. A memory that shows its
                work is a memory the rest of the web can rely on.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* ─────────────────────── final CTA ─────────────────────── */}
      <section className="border-t border-edge">
        <div className="mx-auto max-w-5xl px-6 py-24 text-center">
          <Sprig className="mx-auto h-7 w-7" />
          <h2 className="mx-auto mt-6 max-w-2xl text-balance text-4xl font-semibold leading-tight tracking-tight md:text-[44px]">
            Plant one thing. Watch it tend itself.
          </h2>
          <p className="mx-auto mt-5 max-w-md text-[15px] leading-relaxed text-faint">
            Start a conversation, set a watch, and let the gardener keep the
            record honest while you get on with your life.
          </p>
          <Link
            href="/"
            className="mt-9 inline-block rounded-md bg-moss px-6 py-3 text-sm font-medium text-white shadow-sm transition-colors hover:bg-moss-deep"
          >
            Enter the garden
          </Link>
        </div>
      </section>

      {/* footer */}
      <footer className="border-t border-edge">
        <div className="mx-auto flex max-w-5xl flex-col items-center justify-between gap-3 px-6 py-8 text-center md:flex-row md:text-left">
          <div className="flex items-center gap-2">
            <Sprig className="h-4 w-4" />
            <span className="text-[13px] font-medium text-faint">Gardener</span>
          </div>
          <span className="font-mono text-[11px] text-dim">
            an agent whose memory takes care of itself
          </span>
        </div>
      </footer>
    </main>
  );
}
