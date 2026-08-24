// Tracks in-flight ingestions for the Recent list's spinner row, backed by
// real GET /ingest/{session_id} polling — see docs/future-scope.md's "Real
// ingest-completion tracking". Replaces the old client-only timeout guess.
import { getIngestStatus } from './api';

export type PendingIngestion = {
  sessionId: string;
  startedAt: number;
  // Defaults to the ingest-specific copy in index.tsx's PendingRow when
  // absent — set explicitly for a differently-worded in-flight job, e.g. an
  // on-demand summarize request, which shares this exact polling mechanism.
  label?: string;
};

const POLL_INTERVAL_MS = 3000;
// Safety fallback only — stops polling a session forever if the status
// endpoint itself is unreachable. Real completion is detected by polling,
// not by this timeout.
const MAX_PENDING_MS = 120_000;

let pending: PendingIngestion[] = [];
const listeners = new Set<() => void>();
let pollTimer: ReturnType<typeof setInterval> | null = null;

function notify() {
  for (const listener of listeners) listener();
}

// Array.filter() always returns a new reference, even when nothing gets
// removed — reassigning `pending` unconditionally would make every
// getPendingIngestionsSnapshot() call return a "changed" snapshot to
// useSyncExternalStore even when nothing actually changed, looping forever.
// Only reassign (and notify) when something actually changed. See the fix
// for the "Maximum update depth exceeded" bug this exact pattern caused.
function remove(sessionId: string) {
  const filtered = pending.filter((p) => p.sessionId !== sessionId);
  if (filtered.length !== pending.length) {
    pending = filtered;
    notify();
  }
}

async function pollOnce() {
  const now = Date.now();
  await Promise.all(
    pending.map(async (p) => {
      if (now - p.startedAt > MAX_PENDING_MS) {
        remove(p.sessionId);
        return;
      }
      const result = await getIngestStatus(p.sessionId);
      if (result.ok && result.status !== 'processing') {
        remove(p.sessionId);
      }
    })
  );
  if (pending.length === 0 && pollTimer) {
    clearInterval(pollTimer);
    pollTimer = null;
  }
}

function schedulePoll() {
  if (pollTimer || pending.length === 0) return;
  pollTimer = setInterval(pollOnce, POLL_INTERVAL_MS);
}

export function addPendingIngestion(sessionId: string, label?: string): void {
  pending = [...pending, { sessionId, startedAt: Date.now(), label }];
  notify();
  schedulePoll();
}

// Call after a fresh items fetch — clears any pending entry started before
// the newest known item, since ingestion for it has clearly already landed.
// Not exact (one share can produce many notes, or none the agent judges
// worth writing), just a way to clear the placeholder sooner than the next
// poll tick in the common case.
export function clearPendingBefore(newestItemCreatedAt: string | undefined): void {
  if (!newestItemCreatedAt) return;
  const newestMs = Date.parse(newestItemCreatedAt);
  if (Number.isNaN(newestMs)) return;
  const filtered = pending.filter((p) => p.startedAt >= newestMs);
  if (filtered.length !== pending.length) {
    pending = filtered;
    notify();
  }
}

export function getPendingIngestionsSnapshot(): PendingIngestion[] {
  return pending;
}

export function subscribePendingIngestions(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}
