"use client";

import {
  useCallback,
  useEffect,
  useRef,
  useState,
  useSyncExternalStore,
} from "react";
import { isOnline, subscribeHealth } from "@/lib/api";

/**
 * Dead-simple SWR-style polling. Pass `null` as fetcher to pause.
 * `key` resets state when the underlying resource changes (e.g. session id).
 * Keeps the last good data on failure — the UI never blanks out because the
 * backend blipped.
 */
export function usePolling<T>(
  fetcher: (() => Promise<T>) | null,
  intervalMs: number,
  key = "",
) {
  const [data, setData] = useState<T | null>(null);
  const [loaded, setLoaded] = useState(false);
  const fetcherRef = useRef(fetcher);
  fetcherRef.current = fetcher;
  const runRef = useRef<() => Promise<void>>(async () => {});

  const enabled = fetcher !== null;

  useEffect(() => {
    setData(null);
    setLoaded(false);
    if (!enabled) return;
    let active = true;

    const run = async () => {
      const f = fetcherRef.current;
      if (!f) return;
      try {
        const result = await f();
        if (active) {
          setData(result);
          setLoaded(true);
        }
      } catch {
        // fail soft: keep last data; the health store drives the banner
      }
    };
    runRef.current = run;

    run();
    const timer = setInterval(run, intervalMs);
    return () => {
      active = false;
      clearInterval(timer);
    };
  }, [key, intervalMs, enabled]);

  const refresh = useCallback(() => runRef.current(), []);

  return { data, loaded, refresh };
}

/** True while the backend is reachable; drives the offline banner. */
export function useBackendOnline(): boolean {
  return useSyncExternalStore(subscribeHealth, isOnline, () => true);
}

/** Format a timestamp as a short relative time ("3m ago"). */
export function relativeTime(ts: string | null | undefined): string {
  if (!ts) return "never";
  const then = new Date(ts).getTime();
  if (Number.isNaN(then)) return "—";
  const secs = Math.max(0, Math.floor((Date.now() - then) / 1000));
  if (secs < 10) return "just now";
  if (secs < 60) return `${secs}s ago`;
  const mins = Math.floor(secs / 60);
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}
