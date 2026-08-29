'use client';

import { useState } from 'react';
import Link from 'next/link';

import type { IngestStatus } from '@/lib/upload';
import type { PermanentNoteCreateResponse } from '@/lib/types';

const POLL_INTERVAL_MS = 3000;

type ConnectionsState = 'idle' | 'searching' | 'done' | 'error';

export default function WritePage() {
  const [title, setTitle] = useState('');
  const [body, setBody] = useState('');
  const [tags, setTags] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [created, setCreated] = useState<PermanentNoteCreateResponse | null>(null);
  const [connectionsState, setConnectionsState] = useState<ConnectionsState>('idle');
  const [connectionsResult, setConnectionsResult] = useState<string | null>(null);

  async function handleSave() {
    setSaving(true);
    setError(null);
    try {
      const res = await fetch('/api/items/permanent', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          title,
          body,
          tags: tags
            .split(',')
            .map((t) => t.trim())
            .filter(Boolean),
        }),
      });
      if (!res.ok) throw new Error(`${res.status} ${await res.text()}`);
      setCreated(await res.json());
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSaving(false);
    }
  }

  async function handleFindConnections() {
    if (!created) return;
    setConnectionsState('searching');
    try {
      const startRes = await fetch(`/api/items/${encodeURIComponent(created.note_id)}/find-connections`, {
        method: 'POST',
      });
      if (!startRes.ok) throw new Error(`${startRes.status} ${await startRes.text()}`);
      const { session_id } = await startRes.json();

      for (;;) {
        const statusRes = await fetch(`/api/ingest/${encodeURIComponent(session_id)}`);
        const status: IngestStatus = await statusRes.json();
        if (status.status === 'processing') {
          await new Promise((r) => setTimeout(r, POLL_INTERVAL_MS));
          continue;
        }
        if (status.status === 'error') {
          setConnectionsState('error');
          setConnectionsResult(status.error || 'search failed');
        } else {
          setConnectionsState('done');
          setConnectionsResult(status.skipped_reason || 'No new connections found.');
        }
        return;
      }
    } catch (err) {
      setConnectionsState('error');
      setConnectionsResult(err instanceof Error ? err.message : String(err));
    }
  }

  function handleWriteAnother() {
    setTitle('');
    setBody('');
    setTags('');
    setCreated(null);
    setConnectionsState('idle');
    setConnectionsResult(null);
  }

  return (
    <main className="max-w-2xl mx-auto p-6 flex flex-col gap-4 w-full">
      <Link href="/" className="text-sm text-neutral-500 hover:underline self-start">
        ← Graph
      </Link>
      <h1 className="text-xl font-semibold">Write a permanent note</h1>
      <p className="text-sm text-neutral-500">
        A note in your own words — never auto-written. Cite existing notes later with &quot;Find connections&quot;
        below, or link them by hand from the graph.
      </p>

      {created ? (
        <div className="flex flex-col gap-4 border border-neutral-200 dark:border-neutral-800 rounded-lg p-4">
          <p className="text-sm">
            Saved <span className="font-medium">&quot;{created.title}&quot;</span>.
          </p>

          {connectionsState === 'idle' && (
            <button
              onClick={handleFindConnections}
              className="self-start px-4 py-2 rounded-md bg-neutral-900 text-white dark:bg-neutral-100 dark:text-neutral-900 text-sm"
            >
              Find connections
            </button>
          )}
          {connectionsState === 'searching' && <span className="text-sm text-blue-500">Searching…</span>}
          {connectionsState === 'done' && <p className="text-sm text-green-600">{connectionsResult}</p>}
          {connectionsState === 'error' && <p className="text-sm text-red-500">Error: {connectionsResult}</p>}

          <div className="flex gap-4 text-sm">
            <button onClick={handleWriteAnother} className="text-neutral-500 hover:underline">
              Write another
            </button>
            <Link href="/" className="text-neutral-500 hover:underline">
              View in graph
            </Link>
          </div>
        </div>
      ) : (
        <div className="flex flex-col gap-3">
          <input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="Title"
            className="border border-neutral-300 dark:border-neutral-700 rounded-md px-3 py-1.5 text-sm"
          />
          <textarea
            value={body}
            onChange={(e) => setBody(e.target.value)}
            placeholder="Write the idea in your own words…"
            rows={10}
            className="border border-neutral-300 dark:border-neutral-700 rounded-md px-3 py-2 text-sm"
          />
          <input
            value={tags}
            onChange={(e) => setTags(e.target.value)}
            placeholder="Tags (comma-separated)"
            className="border border-neutral-300 dark:border-neutral-700 rounded-md px-3 py-1.5 text-sm"
          />
          {error && <p className="text-sm text-red-500">Error: {error}</p>}
          <button
            onClick={handleSave}
            disabled={saving || !title.trim() || !body.trim()}
            className="self-start px-4 py-2 rounded-md bg-neutral-900 text-white dark:bg-neutral-100 dark:text-neutral-900 text-sm disabled:opacity-50"
          >
            {saving ? 'Saving…' : 'Save'}
          </button>
        </div>
      )}
    </main>
  );
}
