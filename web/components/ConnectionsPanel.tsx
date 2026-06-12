"use client";

import { useState } from "react";
import { getConnectors, type Connector } from "@/lib/api";
import { usePolling } from "@/lib/hooks";

/**
 * Connections / connector management — the integrations watches act through.
 *
 * Currently Google Calendar and Discord (via Composio). Real OAuth happens via
 * the interactive Composio CLI, so this panel does NOT perform the connect — it
 * shows live status (from GET /connectors) and the exact command to run.
 */
export default function ConnectionsPanel() {
  const { data: connectors } = usePolling<Connector[]>(
    getConnectors,
    3000,
    "connectors",
  );

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="shrink-0 border-b border-edge px-4 py-2.5">
        <p className="text-[11px] uppercase tracking-wide text-dim">
          Connections · how your watches act in the world
        </p>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto px-4 py-4">
        {connectors === null && (
          <p className="px-1 py-2 text-xs text-dim">…</p>
        )}

        <div className="flex flex-col gap-3">
          {connectors?.map((c) => (
            <ConnectorRow key={c.key} connector={c} />
          ))}
        </div>

        <p className="mt-6 text-[11px] leading-relaxed text-dim">
          Connecting is a one-time terminal step — run the command, approve the
          OAuth in your browser, and the status here turns green on the next
          poll.
        </p>
      </div>
    </div>
  );
}

function ConnectorRow({ connector }: { connector: Connector }) {
  const [copied, setCopied] = useState(false);
  // The instructions string is the CLI command — surface it as copyable code.
  const command = connector.instructions;

  return (
    <div className="rounded-lg border border-edge bg-bg px-3.5 py-3">
      <div className="flex items-center justify-between gap-2">
        <span className="flex items-center gap-2">
          <span
            className={`h-2 w-2 shrink-0 rounded-full ${
              connector.connected ? "bg-moss" : "bg-dim"
            }`}
            aria-hidden
            title={connector.connected ? "connected" : "not connected"}
          />
          <span className="text-sm font-medium text-ink">{connector.label}</span>
        </span>
        <span
          className={`rounded-full px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide ${
            connector.connected
              ? "bg-moss/10 text-moss-deep"
              : "bg-raised text-dim"
          }`}
        >
          {connector.connected ? "connected" : "not connected"}
        </span>
      </div>

      {!connector.connected && command && (
        <div className="mt-3 flex items-center gap-2">
          <code className="min-w-0 flex-1 truncate rounded-md border border-edge bg-surface px-2.5 py-1.5 font-mono text-[11px] text-faint">
            {command}
          </code>
          <button
            onClick={() => {
              navigator.clipboard?.writeText(command);
              setCopied(true);
              setTimeout(() => setCopied(false), 1500);
            }}
            className="shrink-0 rounded-md border border-edge px-2.5 py-1.5 text-[11px] text-faint transition-colors hover:border-moss/50 hover:text-moss"
          >
            {copied ? "copied" : "copy"}
          </button>
        </div>
      )}
    </div>
  );
}
