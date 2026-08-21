// Client-only, best-effort "is my share still processing?" tracker. There's
// no backend session-status endpoint (POST /ingest just returns 202 and
// forgets), so this is a guess: a placeholder shows for up to PENDING_TTL_MS,
// clearing sooner if evidence of completion shows up (a newer item exists),
// or on its own after the timeout regardless. See docs/future-scope.md for
// the real fix (a backend status endpoint) if this stops being good enough.
export type PendingIngestion = { sessionId: string; startedAt: number };

const PENDING_TTL_MS = 90_000;

let pending: PendingIngestion[] = [];
const listeners = new Set<() => void>();
let sweepTimer: ReturnType<typeof setInterval> | null = null;

function notify() {
  for (const listener of listeners) listener();
}

function prune() {
  // Array.filter() always returns a new reference, even when nothing gets
  // removed — reassigning `pending` unconditionally would make every
  // getPendingIngestionsSnapshot() call return a "changed" snapshot to
  // useSyncExternalStore even when nothing actually changed, looping
  // forever. Only reassign (and notify) when something was actually pruned.
  const now = Date.now();
  const filtered = pending.filter((p) => now - p.startedAt < PENDING_TTL_MS);
  if (filtered.length !== pending.length) {
    pending = filtered;
    notify();
  }
}

function scheduleSweep() {
  if (sweepTimer || pending.length === 0) return;
  sweepTimer = setInterval(() => {
    prune();
    if (pending.length === 0 && sweepTimer) {
      clearInterval(sweepTimer);
      sweepTimer = null;
    }
  }, 5000);
}

export function addPendingIngestion(sessionId: string): void {
  pending = [...pending, { sessionId, startedAt: Date.now() }];
  notify();
  scheduleSweep();
}

// Call after a fresh items fetch — clears any pending entry started before
// the newest known item, since ingestion for it has clearly already landed.
// Not exact (one share can produce many notes, or none the agent judges
// worth writing), just a way to clear the placeholder sooner than the
// timeout in the common case.
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
  prune();
  return pending;
}

export function subscribePendingIngestions(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}
