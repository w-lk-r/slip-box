'use client';

import { useEffect, useState } from 'react';

import type { ItemDetail } from '@/lib/types';

const CONNECTION_LABEL: Record<string, string> = {
  supports: 'Supports',
  contradicts: 'Contradicts',
  extends: 'Extends',
  related_to: 'Related to',
  grounded_in: 'Grounded in',
};

// Frontmatter link entries are stored as "[[note_id|Title]]" — pull out just the title.
function linkTitle(entry: string): string {
  const match = entry.match(/^\[\[[^|]*\|(.+)\]\]$/);
  return match ? match[1] : entry;
}

export default function NodePanel({ noteId, onClose }: { noteId: string; onClose: () => void }) {
  const [item, setItem] = useState<ItemDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setItem(null);
    setError(null);
    fetch(`/api/items/${encodeURIComponent(noteId)}`)
      .then((res) => {
        if (!res.ok) throw new Error(`Request failed: ${res.status}`);
        return res.json();
      })
      .then(setItem)
      .catch((err) => setError(err instanceof Error ? err.message : String(err)));
  }, [noteId]);

  const connectionEntries = Object.entries(item?.connections ?? {}).filter(([, links]) => links.length > 0);

  return (
    <aside className="fixed top-0 right-0 h-full w-full max-w-sm overflow-y-auto bg-white p-5 shadow-xl dark:bg-neutral-900">
      <button onClick={onClose} className="mb-3 text-sm text-neutral-500 hover:text-neutral-800 dark:hover:text-neutral-200">
        ✕ Close
      </button>

      {error && <p className="text-sm text-red-500">{error}</p>}
      {!item && !error && <p className="text-sm text-neutral-500">Loading…</p>}

      {item && (
        <>
          <h2 className="text-lg font-semibold">{item.title}</h2>
          <div className="mt-1 flex gap-3 text-xs text-neutral-500">
            <span>{item.type}</span>
            {item.date && <span>{item.date}</span>}
          </div>
          {!!item.tags?.length && (
            <p className="mt-2 text-xs text-neutral-500">{item.tags.join(' · ')}</p>
          )}
          <p className="mt-4 whitespace-pre-wrap text-sm leading-relaxed">{item.body}</p>
          {item.source_url && (
            <p className="mt-4 truncate text-xs text-neutral-500">
              Source:{' '}
              <a href={item.source_url} target="_blank" rel="noreferrer" className="underline">
                {item.source_url}
              </a>
            </p>
          )}

          {connectionEntries.length > 0 && (
            <div className="mt-5 space-y-2 border-t border-neutral-200 pt-3 dark:border-neutral-700">
              <p className="text-xs font-semibold">Connections</p>
              {connectionEntries.map(([type, links]) => (
                <div key={type} className="text-xs">
                  <span className="text-neutral-500">{CONNECTION_LABEL[type] ?? type}:</span>{' '}
                  {links.map(linkTitle).join(', ')}
                </div>
              ))}
            </div>
          )}
        </>
      )}
    </aside>
  );
}
