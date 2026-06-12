"use client";

/** Unified diff rendered with red/green line coloring. */
export default function DiffView({ diff }: { diff: string }) {
  const lines = diff.replace(/\r\n/g, "\n").split("\n");
  return (
    <pre className="overflow-x-auto rounded-md border border-edge bg-bg font-mono text-xs leading-5">
      {lines.map((line, i) => {
        let cls = "text-faint";
        if (line.startsWith("+++") || line.startsWith("---")) {
          cls = "text-dim";
        } else if (line.startsWith("@@")) {
          cls = "text-moss-deep";
        } else if (line.startsWith("+")) {
          cls = "bg-moss/10 text-moss";
        } else if (line.startsWith("-")) {
          cls = "bg-rust/10 text-rust";
        }
        return (
          <div key={i} className={`px-3 ${cls}`}>
            {line === "" ? " " : line}
          </div>
        );
      })}
    </pre>
  );
}
