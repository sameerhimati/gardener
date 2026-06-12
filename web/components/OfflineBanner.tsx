"use client";

import { useBackendOnline } from "@/lib/hooks";

export default function OfflineBanner() {
  const online = useBackendOnline();
  if (online) return null;
  return (
    <div className="flex h-7 shrink-0 items-center justify-center gap-2 border-b border-amber/30 bg-amber/10 text-xs text-amber">
      <span className="h-1.5 w-1.5 rounded-full bg-amber" aria-hidden />
      backend offline — retrying
    </div>
  );
}
