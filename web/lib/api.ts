// Typed fetchers against the Gardener backend (docs/architecture.md HTTP API table).
// Every call fails soft: network failures flip a shared health flag that the UI
// renders as a thin "backend offline" banner — nothing here ever crashes the app.

import { getUserId } from "./uid";

// `||` not `??`: an empty NEXT_PUBLIC_API_URL exported by dev.sh must still fall back
const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

// ---------- types ----------

export interface Watch {
  id: string;
  task: string;
  session_id: string;
  status: string;
  cadence_sec?: number;
  last_run: string | null;
  last_result?: string | null;
}

export interface Message {
  role: string;
  content: string;
  ts: string;
}

export interface VaultFileMeta {
  path: string;
  title: string;
  updated: string;
}

export interface VaultFile {
  path: string;
  content: string;
}

export type FindingStatus = "open" | "auto_applied" | "approved" | "rejected";

export interface Finding {
  id: string;
  rule: string;
  vault_path: string;
  summary: string;
  diff: string;
  confidence: number;
  severity: string;
  status: FindingStatus;
  ts: string;
}

export interface ChatResponse {
  session_id: string;
  reply: string;
}

export interface WatchEvent {
  event_id: string;
  session_id: string;
  ts: string;
  kind: "tool_call" | "tool_result" | "watch_cycle";
  payload: Record<string, unknown>;
}

// ---------- backend health (shared store for the offline banner) ----------

let online = true;
const listeners = new Set<() => void>();

function setOnline(value: boolean) {
  if (online !== value) {
    online = value;
    listeners.forEach((l) => l());
  }
}

export function subscribeHealth(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function isOnline(): boolean {
  return online;
}

// ---------- request core ----------

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  // Per-browser identity: attach X-User-Id on EVERY request so the backend
  // routes to this browser's isolated garden. Empty (SSR) → header omitted →
  // backend defaults to "sameer".
  const uid = getUserId();
  try {
    res = await fetch(`${API_URL}${path}`, {
      ...init,
      headers: {
        "Content-Type": "application/json",
        ...(uid ? { "X-User-Id": uid } : {}),
        ...(init?.headers ?? {}),
      },
    });
  } catch (err) {
    // Network-level failure: backend is unreachable.
    setOnline(false);
    throw err;
  }
  // We reached the server — it's online even if this request errored.
  setOnline(true);
  if (!res.ok) {
    throw new Error(`${init?.method ?? "GET"} ${path} → ${res.status}`);
  }
  return (await res.json()) as T;
}

function post<T>(path: string, body?: unknown): Promise<T> {
  return request<T>(path, {
    method: "POST",
    body: body === undefined ? undefined : JSON.stringify(body),
  });
}

function patch<T>(path: string, body?: unknown): Promise<T> {
  return request<T>(path, {
    method: "PATCH",
    body: body === undefined ? undefined : JSON.stringify(body),
  });
}

function del<T>(path: string): Promise<T> {
  return request<T>(path, { method: "DELETE" });
}

// ---------- fetchers (one per endpoint) ----------

export function sendChat(
  sessionId: string | null,
  message: string,
  image?: string | null,
): Promise<ChatResponse> {
  return post<ChatResponse>("/chat", {
    ...(sessionId ? { session_id: sessionId } : {}),
    message,
    ...(image ? { image } : {}),
  });
}

export function getWatchEvents(watchId: string): Promise<WatchEvent[]> {
  return request<WatchEvent[]>(
    `/watches/${encodeURIComponent(watchId)}/events`,
  );
}

export function getMessages(sessionId: string): Promise<Message[]> {
  return request<Message[]>(
    `/sessions/${encodeURIComponent(sessionId)}/messages`,
  );
}

export function getWatches(): Promise<Watch[]> {
  return request<Watch[]>("/watches");
}

export function runWatch(watchId: string): Promise<unknown> {
  return post<unknown>(`/watches/${encodeURIComponent(watchId)}/run`);
}

export function sendWatchMessage(
  watchId: string,
  message: string,
): Promise<{ reply: string }> {
  return post<{ reply: string }>(
    `/watches/${encodeURIComponent(watchId)}/message`,
    { message },
  );
}

export function getVault(): Promise<VaultFileMeta[]> {
  return request<VaultFileMeta[]>("/vault");
}

export function getVaultFile(path: string): Promise<VaultFile> {
  return request<VaultFile>(`/vault/file?path=${encodeURIComponent(path)}`);
}

export function getFindings(): Promise<Finding[]> {
  return request<Finding[]>("/findings");
}

export function applyFinding(id: string): Promise<Finding> {
  return post<Finding>(`/findings/${encodeURIComponent(id)}/apply`);
}

export function rejectFinding(id: string): Promise<Finding> {
  return post<Finding>(`/findings/${encodeURIComponent(id)}/reject`);
}

export function runLint(): Promise<Finding[]> {
  return post<Finding[]>("/lint/run");
}

// ---------- onboarding ----------

export interface PlantedFact {
  topic: string;
  fact: string;
}

export function distill(
  text: string,
  source = "onboarding",
): Promise<{ written: PlantedFact[] }> {
  return post<{ written: PlantedFact[] }>("/distill", { text, source });
}

/** Deterministically plant name + zip into the vault. Unlike the fuzzy
 *  `/distill` extractor (which has no name concept), this endpoint lands both
 *  reliably. POST /onboarding/basics {name?, zip?} → {planted:[{topic,fact}]}. */
export function onboardingBasics(
  name: string,
  zip: string,
): Promise<{ planted: PlantedFact[] }> {
  return post<{ planted: PlantedFact[] }>("/onboarding/basics", {
    ...(name ? { name } : {}),
    ...(zip ? { zip } : {}),
  });
}

export interface OnboardingTurn {
  session_id: string;
  reply: string;
  written: PlantedFact[];
}

/** One conversational onboarding exchange — the real agent answers back. */
export function onboardingTurn(
  sessionId: string | null,
  message: string,
  question: string,
): Promise<OnboardingTurn> {
  return post<OnboardingTurn>("/onboarding/turn", {
    ...(sessionId ? { session_id: sessionId } : {}),
    message,
    question,
  });
}

export function createWatch(task: string): Promise<Watch> {
  return post<Watch>("/watches", { task });
}

export function pauseWatch(watchId: string): Promise<Watch> {
  return post<Watch>(`/watches/${encodeURIComponent(watchId)}/pause`);
}

export function resumeWatch(watchId: string): Promise<Watch> {
  return post<Watch>(`/watches/${encodeURIComponent(watchId)}/resume`);
}

export function editWatch(
  watchId: string,
  fields: { task?: string; cadence_sec?: number },
): Promise<Watch> {
  return patch<Watch>(`/watches/${encodeURIComponent(watchId)}`, fields);
}

/** Update a watch's fields (e.g. cadence). PATCH /watches/{id} → updated watch.
 *  Shares the X-User-Id-attaching request path. */
export function updateWatch(
  watchId: string,
  fields: { task?: string; cadence_sec?: number },
): Promise<Watch> {
  return patch<Watch>(`/watches/${encodeURIComponent(watchId)}`, fields);
}

export function deleteWatch(watchId: string): Promise<{ ok: boolean }> {
  return del<{ ok: boolean }>(`/watches/${encodeURIComponent(watchId)}`);
}

// ---------- connectors (integration status) ----------

export interface Connector {
  key: string;
  label: string;
  connected: boolean;
  instructions: string;
}

export function getConnectors(): Promise<Connector[]> {
  return request<Connector[]>("/connectors");
}
