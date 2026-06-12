"use client";

import React from "react";

/**
 * Tiny markdown renderer — enough for Gardener's vault files and chat replies.
 * Supports: headings, bullet/ordered lists, code fences, inline code, bold,
 * italic, links, hr, YAML frontmatter (rendered as a muted meta block), and —
 * when `provenance` is on — "(src: ...)" suffixes dimmed for the Garden tab.
 */

interface MarkdownProps {
  text: string;
  provenance?: boolean;
  className?: string;
}

const INLINE_PATTERN =
  /(`[^`]+`)|(\[[^\]]+\]\([^)\s]+\))|(\*\*[^*]+\*\*)|(\*[^*\s][^*]*\*)|(\(src:[^)]*\))/g;

function renderInline(text: string, provenance: boolean): React.ReactNode[] {
  const out: React.ReactNode[] = [];
  let last = 0;
  let key = 0;
  for (const match of text.matchAll(INLINE_PATTERN)) {
    const idx = match.index ?? 0;
    if (idx > last) out.push(text.slice(last, idx));
    const token = match[0];
    if (match[1]) {
      out.push(
        <code
          key={key++}
          className="rounded bg-raised/60 px-1 py-px font-mono text-[0.85em] text-moss-deep"
        >
          {token.slice(1, -1)}
        </code>,
      );
    } else if (match[2]) {
      const label = token.slice(1, token.indexOf("]"));
      const href = token.slice(token.indexOf("](") + 2, -1);
      out.push(
        <a
          key={key++}
          href={href}
          target="_blank"
          rel="noopener noreferrer"
          className="text-moss underline decoration-moss/40 underline-offset-2 hover:decoration-moss"
        >
          {label}
        </a>,
      );
    } else if (match[3]) {
      out.push(
        <strong key={key++} className="font-semibold text-ink">
          {renderInline(token.slice(2, -2), provenance)}
        </strong>,
      );
    } else if (match[4]) {
      out.push(
        <em key={key++} className="italic">
          {token.slice(1, -1)}
        </em>,
      );
    } else if (match[5]) {
      if (provenance) {
        out.push(
          <span key={key++} className="font-mono text-[0.78em] text-dim">
            {token}
          </span>,
        );
      } else {
        out.push(token);
      }
    }
    last = idx + token.length;
  }
  if (last < text.length) out.push(text.slice(last));
  return out;
}

interface Block {
  kind: "heading" | "ul" | "ol" | "code" | "hr" | "p" | "frontmatter";
  level?: number;
  lines: string[];
}

function parseBlocks(text: string): Block[] {
  const lines = text.replace(/\r\n/g, "\n").split("\n");
  const blocks: Block[] = [];
  let i = 0;

  // YAML frontmatter at the very top
  if (lines[0]?.trim() === "---") {
    const end = lines.findIndex((l, idx) => idx > 0 && l.trim() === "---");
    if (end > 0) {
      blocks.push({ kind: "frontmatter", lines: lines.slice(1, end) });
      i = end + 1;
    }
  }

  while (i < lines.length) {
    const line = lines[i];
    const trimmed = line.trim();

    if (trimmed === "") {
      i++;
      continue;
    }
    if (trimmed.startsWith("```")) {
      const buf: string[] = [];
      i++;
      while (i < lines.length && !lines[i].trim().startsWith("```")) {
        buf.push(lines[i]);
        i++;
      }
      i++; // closing fence
      blocks.push({ kind: "code", lines: buf });
      continue;
    }
    const heading = /^(#{1,6})\s+(.*)$/.exec(trimmed);
    if (heading) {
      blocks.push({
        kind: "heading",
        level: heading[1].length,
        lines: [heading[2]],
      });
      i++;
      continue;
    }
    if (/^(-{3,}|\*{3,})$/.test(trimmed)) {
      blocks.push({ kind: "hr", lines: [] });
      i++;
      continue;
    }
    if (/^[-*]\s+/.test(trimmed)) {
      const buf: string[] = [];
      while (i < lines.length && /^[-*]\s+/.test(lines[i].trim())) {
        buf.push(lines[i].trim().replace(/^[-*]\s+/, ""));
        i++;
      }
      blocks.push({ kind: "ul", lines: buf });
      continue;
    }
    if (/^\d+\.\s+/.test(trimmed)) {
      const buf: string[] = [];
      while (i < lines.length && /^\d+\.\s+/.test(lines[i].trim())) {
        buf.push(lines[i].trim().replace(/^\d+\.\s+/, ""));
        i++;
      }
      blocks.push({ kind: "ol", lines: buf });
      continue;
    }
    // paragraph: consume until blank line or structural line
    const buf: string[] = [];
    while (i < lines.length) {
      const t = lines[i].trim();
      if (
        t === "" ||
        t.startsWith("```") ||
        /^#{1,6}\s/.test(t) ||
        /^[-*]\s+/.test(t) ||
        /^\d+\.\s+/.test(t)
      ) {
        break;
      }
      buf.push(t);
      i++;
    }
    blocks.push({ kind: "p", lines: buf });
  }
  return blocks;
}

const HEADING_STYLES: Record<number, string> = {
  1: "text-base font-semibold tracking-tight text-ink",
  2: "text-[0.95rem] font-semibold tracking-tight text-ink",
  3: "text-sm font-semibold text-ink",
};

export function Markdown({ text, provenance = false, className }: MarkdownProps) {
  const blocks = parseBlocks(text);
  return (
    <div className={`space-y-2.5 text-sm leading-relaxed ${className ?? ""}`}>
      {blocks.map((block, i) => {
        switch (block.kind) {
          case "frontmatter":
            return (
              <div
                key={i}
                className="rounded-md border border-edge bg-surface px-3 py-2 font-mono text-xs text-dim"
              >
                {block.lines.map((l, j) => (
                  <div key={j}>{l}</div>
                ))}
              </div>
            );
          case "heading": {
            const level = Math.min(block.level ?? 1, 6);
            const cls = HEADING_STYLES[level] ?? "text-sm font-medium text-ink";
            const Tag = `h${level}` as keyof React.JSX.IntrinsicElements;
            return (
              <Tag key={i} className={cls}>
                {renderInline(block.lines[0], provenance)}
              </Tag>
            );
          }
          case "code":
            return (
              <pre
                key={i}
                className="overflow-x-auto rounded-md border border-edge bg-surface px-3 py-2 font-mono text-xs text-ink/90"
              >
                {block.lines.join("\n")}
              </pre>
            );
          case "hr":
            return <hr key={i} className="border-edge" />;
          case "ul":
            return (
              <ul key={i} className="space-y-1 pl-1">
                {block.lines.map((l, j) => (
                  <li key={j} className="flex gap-2">
                    <span className="mt-[0.45em] h-1 w-1 shrink-0 rounded-full bg-moss-deep" />
                    <span>{renderInline(l, provenance)}</span>
                  </li>
                ))}
              </ul>
            );
          case "ol":
            return (
              <ol key={i} className="space-y-1 pl-1">
                {block.lines.map((l, j) => (
                  <li key={j} className="flex gap-2">
                    <span className="shrink-0 font-mono text-xs leading-relaxed text-dim">
                      {j + 1}.
                    </span>
                    <span>{renderInline(l, provenance)}</span>
                  </li>
                ))}
              </ol>
            );
          case "p":
          default:
            return (
              <p key={i}>{renderInline(block.lines.join(" "), provenance)}</p>
            );
        }
      })}
    </div>
  );
}
