'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';

import type { SourceListItem } from '@/lib/types';

const TYPE_LABEL: Record<SourceListItem['type'], string> = {
  web: 'Web',
  youtube: 'YouTube',
  pdf: 'PDF',
};

export default function SourcesPage() {
  const [sources, setSources] = useState<SourceListItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch('/api/sources')
      .then((res) => {
        if (!res.ok) throw new Error(`Request failed: ${res.status}`);
        return res.json();
      })
      .then((data) => setSources(data.sources))
      .catch((err) => setError(err instanceof Error ? err.message : String(err)));
  }, []);

  return (
    <main className="max-w-2xl mx-auto p-6 flex flex-col gap-4 w-full">
      <Link href="/" className="text-sm text-neutral-500 hover:underline self-start">
        ← Graph
      </Link>
      <h1 className="text-xl font-semibold">Sources</h1>
      <p className="text-sm text-neutral-500">Everything that's been ingested, grouped by where it came from.</p>

      {error && <p className="text-sm text-red-500">{error}</p>}
      {!sources && !error && <p className="text-sm text-neutral-500">Loading…</p>}
      {sources && sources.length === 0 && <p className="text-sm text-neutral-500">No sources yet.</p>}

      {sources && sources.length > 0 && (
        <ul className="flex flex-col gap-2">
          {sources.map((source) => (
            <li key={source.source_id}>
              <Link
                href={`/sources/${encodeURIComponent(source.source_id)}`}
                className="flex items-center justify-between gap-3 rounded-md border border-neutral-200 px-3 py-2 text-sm hover:bg-neutral-50 dark:border-neutral-800 dark:hover:bg-neutral-900"
              >
                <span className="truncate">{source.title}</span>
                <span className="shrink-0 text-xs text-neutral-500">{TYPE_LABEL[source.type]}</span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </main>
  );
}
