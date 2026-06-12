// Per-browser identity for Gardener's multi-tenant gardens.
//
// Each browser mints one opaque uuid the first time it loads, stores it in
// localStorage under `gardener_uid`, and sends it as the `X-User-Id` header on
// every backend request (wired in lib/api.ts). The backend resolves this header
// to a per-user garden (vault/watches/sessions/events), DEFAULTING to "sameer"
// when absent — so Sameer's rehearsed seeded demo (no token needed) is unchanged,
// while every judge's browser gets its own isolated garden.

const KEY = "gardener_uid";

/** Stable per-browser user id. Generates + persists one on first call.
 *  SSR-safe: returns "" when there's no window (no header sent → backend
 *  defaults to "sameer"), so server rendering never throws. */
export function getUserId(): string {
  if (typeof window === "undefined") return "";
  try {
    // Demo override: ?u=<id> pins this browser to a specific garden and
    // persists it. Load the app with ?u=sameer to see the seeded demo
    // persona (housing/gpu/etc.) instead of a fresh empty garden.
    const pinned = new URLSearchParams(window.location.search).get("u");
    if (pinned) {
      window.localStorage.setItem(KEY, pinned);
      return pinned;
    }
    let uid = window.localStorage.getItem(KEY);
    if (!uid) {
      uid = newUid();
      window.localStorage.setItem(KEY, uid);
    }
    return uid;
  } catch {
    // localStorage blocked (private mode / disabled) — fall back to an
    // in-memory id for this page so the session still works in isolation.
    return memoryUid();
  }
}

function newUid(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  // Fallback for environments without crypto.randomUUID.
  return "u-" + Math.random().toString(36).slice(2) + Date.now().toString(36);
}

let _memoryUid: string | null = null;
function memoryUid(): string {
  if (!_memoryUid) _memoryUid = newUid();
  return _memoryUid;
}
