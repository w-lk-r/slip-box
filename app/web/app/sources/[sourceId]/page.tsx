'use client';

import { use, useEffect, useState } from 'react';
import Link from 'next/link';

import NodePanel from '@/components/NodePanel';
import type { ItemSummary } from '@/lib/types';

export default function SourceItemsPage({ params }: { params: Promise<{ sourceId: string }> }) {
  const { sourceId } = use(params);
  const [items, setItems] = useState<ItemSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selectedNoteId, setSelectedNoteId] = useState<string | null>(null);

  useEffect(() => {
    fetch(`/api/items?source_id=${encodeURIComponent(sourceId)}`)
      .then((res) => {
        if (!res.ok) throw new Error(`Request failed: ${res.status}`);
        return res.json();
      })
      .then((data) => setItems(data.items))
      .catch((err) => setError(err instanceof Error ? err.message : String(err)));
  }, [sourceId]);

  return (
    <main className="max-w-2xl mx-auto p-6 flex flex-col gap-4 w-full">
      <Link href="/sources" className="text-sm text-neutral-500 hover:underline self-start">
        ← Sources
      </Link>
      <h1 className="text-xl font-semibold">Notes from this source</h1>

      {error && <p className="text-sm text-red-500">{error}</p>}
      {!items && !error && <p className="text-sm text-neutral-500">Loading…</p>}
      {items && items.length === 0 && <p className="text-sm text-neutral-500">No notes found for this source.</p>}

      {items && items.length > 0 && (
        <ul className="flex flex-col gap-2">
          {items.map((item) => (
            <li key={item.note_id}>
              <button
                onClick={() => setSelectedNoteId(item.note_id)}
                className="flex w-full items-center justify-between gap-3 rounded-md border border-neutral-200 px-3 py-2 text-left text-sm hover:bg-neutral-50 dark:border-neutral-800 dark:hover:bg-neutral-900"
              >
                <span className="truncate">{item.title}</span>
                <span className="shrink-0 text-xs text-neutral-500">{item.type}</span>
              </button>
            </li>
          ))}
        </ul>
      )}

      {selectedNoteId && <NodePanel noteId={selectedNoteId} onClose={() => setSelectedNoteId(null)} />}
    </main>
  );
}
