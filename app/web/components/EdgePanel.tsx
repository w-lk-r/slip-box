'use client';

import { useState } from 'react';

import type { EdgeType, GraphEdge } from '@/lib/types';

const EDGE_TYPES: EdgeType[] = ['SUPPORTS', 'CONTRADICTS', 'EXTENDS', 'RELATED_TO', 'GROUNDED_IN'];

export default function EdgePanel({
  edge,
  onClose,
  onChanged,
}: {
  edge: GraphEdge;
  onClose: () => void;
  onChanged: () => void;
}) {
  const [type, setType] = useState<EdgeType>(edge.type);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const path = `/api/edges/${encodeURIComponent(edge.source)}/${encodeURIComponent(edge.edge_id)}`;

  async function handleSaveType() {
    if (type === edge.type) return;
    setBusy(true);
    setError(null);
    try {
      const res = await fetch(path, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ type }),
      });
      if (!res.ok) throw new Error(`Request failed: ${res.status}`);
      onChanged();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  async function handleDelete() {
    setBusy(true);
    setError(null);
    try {
      const res = await fetch(path, { method: 'DELETE' });
      if (!res.ok) throw new Error(`Request failed: ${res.status}`);
      onChanged();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setBusy(false);
    }
  }

  return (
    <aside className="fixed bottom-6 left-1/2 w-full max-w-sm -translate-x-1/2 rounded-xl bg-white p-4 shadow-xl dark:bg-neutral-900">
      <button onClick={onClose} className="mb-2 text-sm text-neutral-500 hover:text-neutral-800 dark:hover:text-neutral-200">
        ✕ Close
      </button>

      <p className="text-xs text-neutral-500">
        {edge.source} → {edge.target}
      </p>
      <p className="mt-1 text-xs text-neutral-500">Confidence: {edge.confidence.toFixed(2)}</p>

      <select
        value={type}
        onChange={(e) => setType(e.target.value as EdgeType)}
        disabled={busy}
        className="mt-3 w-full rounded border border-neutral-300 bg-transparent p-2 text-sm dark:border-neutral-700"
      >
        {EDGE_TYPES.map((t) => (
          <option key={t} value={t}>
            {t}
          </option>
        ))}
      </select>

      {error && <p className="mt-2 text-xs text-red-500">{error}</p>}

      <div className="mt-3 flex gap-2">
        <button
          onClick={handleSaveType}
          disabled={busy || type === edge.type}
          className="flex-1 rounded bg-blue-600 px-3 py-2 text-sm text-white disabled:opacity-40"
        >
          Save
        </button>
        <button
          onClick={handleDelete}
          disabled={busy}
          className="flex-1 rounded bg-red-600 px-3 py-2 text-sm text-white disabled:opacity-40"
        >
          Delete edge
        </button>
      </div>
    </aside>
  );
}
