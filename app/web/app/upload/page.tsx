'use client';

import { useState } from 'react';
import Link from 'next/link';

import {
  getIngestStatus,
  ingestPdf,
  MAX_CONCURRENT_UPLOADS,
  MAX_PDF_SIZE_BYTES,
  presignUploads,
  runWithConcurrency,
  uploadToS3,
  type IngestMode,
  type NoteRef,
} from '@/lib/upload';

type FileStatus = 'queued' | 'uploading' | 'ingesting' | 'processing' | 'complete' | 'error';

type UploadItem = {
  id: string;
  file: File;
  status: FileStatus;
  error?: string;
  notesCreated?: NoteRef[];
  skippedReason?: string | null;
};

const MODE_OPTIONS: { value: IngestMode; label: string; hint: string }[] = [
  { value: 'auto', label: 'Auto', hint: "Agent decides — one note per PDF, or several if there's a lot in it" },
  { value: 'single', label: 'One idea', hint: 'Exactly one note per PDF — pick a topic below, or let it choose' },
  { value: 'all', label: 'All ideas', hint: 'One note per distinct idea in each PDF' },
];

const POLL_INTERVAL_MS = 3000;

function StatusLabel({ item }: { item: UploadItem }) {
  switch (item.status) {
    case 'queued':
      return <span className="text-neutral-500">Queued</span>;
    case 'uploading':
      return <span className="text-blue-500">Uploading…</span>;
    case 'ingesting':
      return <span className="text-blue-500">Sending…</span>;
    case 'processing':
      return <span className="text-blue-500">Processing…</span>;
    case 'error':
      return <span className="text-red-500">Error: {item.error}</span>;
    case 'complete':
      if (item.notesCreated && item.notesCreated.length > 0) {
        return (
          <span className="text-green-600">
            {item.notesCreated.length === 1 ? `Created "${item.notesCreated[0].title}"` : `Created ${item.notesCreated.length} notes`}
          </span>
        );
      }
      return <span className="text-neutral-500">No note — {item.skippedReason || 'nothing worth saving'}</span>;
  }
}

export default function UploadPage() {
  const [items, setItems] = useState<UploadItem[]>([]);
  const [mode, setMode] = useState<IngestMode>('auto');
  const [topic, setTopic] = useState('');
  const [running, setRunning] = useState(false);

  function addFiles(fileList: FileList | null) {
    if (!fileList) return;
    const pdfs = Array.from(fileList).filter((f) => f.name.toLowerCase().endsWith('.pdf'));
    setItems((prev) => [
      ...prev,
      ...pdfs.map((file) => {
        const id = `${file.name}-${crypto.randomUUID()}`;
        // Immediate feedback, no round trip — the backend re-checks this for
        // real at presign time, since a client-reported size isn't enforcement.
        if (file.size > MAX_PDF_SIZE_BYTES) {
          const limitMb = Math.round(MAX_PDF_SIZE_BYTES / (1024 * 1024));
          return { id, file, status: 'error' as FileStatus, error: `too large (max ${limitMb}MB)` };
        }
        return { id, file, status: 'queued' as FileStatus };
      }),
    ]);
  }

  function update(id: string, patch: Partial<UploadItem>) {
    setItems((prev) => prev.map((it) => (it.id === id ? { ...it, ...patch } : it)));
  }

  async function pollUntilDone(id: string, sessionId: string) {
    for (;;) {
      const status = await getIngestStatus(sessionId);
      if (status.status === 'processing') {
        await new Promise((r) => setTimeout(r, POLL_INTERVAL_MS));
        continue;
      }
      if (status.status === 'error') {
        update(id, { status: 'error', error: status.error || 'processing failed' });
      } else {
        update(id, { status: 'complete', notesCreated: status.notes_created, skippedReason: status.skipped_reason });
      }
      return;
    }
  }

  async function processItem(item: UploadItem) {
    try {
      update(item.id, { status: 'uploading' });
      const presign = await presignUploads([{ filename: item.file.name, size: item.file.size }]);
      const target = presign.files[0];
      await uploadToS3(target.upload_url, item.file);

      update(item.id, { status: 'ingesting' });
      const { session_id } = await ingestPdf(target.key, mode, mode === 'single' ? topic : undefined);

      update(item.id, { status: 'processing' });
      await pollUntilDone(item.id, session_id);
    } catch (err) {
      update(item.id, { status: 'error', error: err instanceof Error ? err.message : String(err) });
    }
  }

  async function handleUploadAll() {
    setRunning(true);
    const queued = items.filter((it) => it.status === 'queued');
    await runWithConcurrency(queued, MAX_CONCURRENT_UPLOADS, processItem);
    setRunning(false);
  }

  const queuedCount = items.filter((it) => it.status === 'queued').length;

  return (
    <main className="max-w-2xl mx-auto p-6 flex flex-col gap-4 w-full">
      <Link href="/" className="text-sm text-neutral-500 hover:underline self-start">
        ← Graph
      </Link>
      <h1 className="text-xl font-semibold">Upload PDFs</h1>
      <p className="text-sm text-neutral-500">
        Point at one or more PDFs — a whole folder works too. Each one is read by the model directly (no separate
        text-extraction step) and turned into notes.
      </p>

      <div
        onDragOver={(e) => e.preventDefault()}
        onDrop={(e) => {
          e.preventDefault();
          addFiles(e.dataTransfer.files);
        }}
        className="border-2 border-dashed border-neutral-300 dark:border-neutral-700 rounded-lg p-8 text-center flex flex-col gap-3 items-center"
      >
        <p className="text-sm text-neutral-500">Drag PDFs here, or</p>
        <div className="flex gap-2">
          <label className="cursor-pointer px-3 py-1.5 rounded-md bg-neutral-900 text-white dark:bg-neutral-100 dark:text-neutral-900 text-sm">
            Choose files
            <input type="file" multiple accept="application/pdf" className="hidden" onChange={(e) => addFiles(e.target.files)} />
          </label>
          <label className="cursor-pointer px-3 py-1.5 rounded-md border border-neutral-300 dark:border-neutral-700 text-sm">
            Choose folder
            {/* webkitdirectory is nonstandard but broadly supported (Chrome/Edge/Firefox/Safari) for folder
                selection — not in React's InputHTMLAttributes typings, hence the loosely-typed spread. */}
            <input
              type="file"
              multiple
              className="hidden"
              {...({ webkitdirectory: 'true' } as Record<string, string>)}
              onChange={(e) => addFiles(e.target.files)}
            />
          </label>
        </div>
      </div>

      <div className="flex flex-col gap-2">
        <span className="text-sm text-neutral-500">How many notes per PDF?</span>
        <div className="flex gap-2">
          {MODE_OPTIONS.map((opt) => (
            <button
              key={opt.value}
              onClick={() => setMode(opt.value)}
              className={`px-3 py-1.5 rounded-md text-sm border ${
                mode === opt.value
                  ? 'bg-neutral-900 text-white dark:bg-neutral-100 dark:text-neutral-900 border-transparent'
                  : 'border-neutral-300 dark:border-neutral-700'
              }`}
            >
              {opt.label}
            </button>
          ))}
        </div>
        <span className="text-xs text-neutral-500">{MODE_OPTIONS.find((o) => o.value === mode)?.hint}</span>
        {mode === 'single' && (
          <input
            value={topic}
            onChange={(e) => setTopic(e.target.value)}
            placeholder="Optional: which idea? (leave blank to let it choose per PDF)"
            className="border border-neutral-300 dark:border-neutral-700 rounded-md px-3 py-1.5 text-sm"
          />
        )}
      </div>

      {items.length > 0 && (
        <ul className="flex flex-col gap-2">
          {items.map((item) => (
            <li
              key={item.id}
              className="flex justify-between items-center gap-3 border border-neutral-200 dark:border-neutral-800 rounded-md px-3 py-2 text-sm"
            >
              <span className="truncate">{item.file.name}</span>
              <StatusLabel item={item} />
            </li>
          ))}
        </ul>
      )}

      {queuedCount > 0 && (
        <button
          onClick={handleUploadAll}
          disabled={running}
          className="self-start px-4 py-2 rounded-md bg-neutral-900 text-white dark:bg-neutral-100 dark:text-neutral-900 text-sm disabled:opacity-50"
        >
          {running ? 'Uploading…' : `Upload ${queuedCount} PDF${queuedCount === 1 ? '' : 's'}`}
        </button>
      )}
    </main>
  );
}
