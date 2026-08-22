// Client-side helpers for the PDF upload page. presignUploads/ingestPdf/
// getIngestStatus go through this app's own same-origin Route Handlers
// (app/api/uploads/presign, app/api/ingest/*) — the BFF pattern already used
// for /api/graph, see lib/backend.ts. uploadToS3 is the deliberate exception:
// it PUTs directly from the browser to S3 using a presigned URL, bypassing
// this app's backend entirely — that's the whole point of presigning
// (uploads can be large; Route Handler compute isn't a relay for the bytes).

export type IngestMode = 'auto' | 'single' | 'all';

// Mirrors app/api/models.py's MAX_PDF_SIZE_BYTES — a pragmatic guardrail
// against an accidental whole-book upload failing deep inside an agent
// invocation instead of at the point of upload, not a verified Bedrock
// document-size limit. Checked here for immediate feedback (no round trip);
// the backend re-checks it for real, since a client-reported size can't be
// trusted as enforcement on its own.
export const MAX_PDF_SIZE_BYTES = 20 * 1024 * 1024;

// Batch uploads/ingests run this many files at a time — POST /ingest each
// starts a real AgentCore invocation, so firing an entire folder at once
// (Promise.all with no cap) would burst well past what's a reasonable
// concurrent load on Bedrock/AgentCore for a single batch.
export const MAX_CONCURRENT_UPLOADS = 3;

export type PresignedFile = { filename: string; key: string; upload_url: string };
export type PresignResponse = { upload_id: string; files: PresignedFile[] };

export type NoteRef = { note_id: string; title: string };
export type IngestStatus = {
  session_id: string;
  status: 'processing' | 'complete' | 'error';
  notes_created: NoteRef[];
  skipped_reason: string | null;
  error: string | null;
};

export async function presignUploads(files: { filename: string; size: number }[]): Promise<PresignResponse> {
  const res = await fetch('/api/uploads/presign', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ files }),
  });
  if (!res.ok) throw new Error(`presign failed: ${res.status} ${await res.text()}`);
  return res.json();
}

export async function uploadToS3(uploadUrl: string, file: File): Promise<void> {
  const res = await fetch(uploadUrl, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/pdf' },
    body: file,
  });
  if (!res.ok) throw new Error(`upload failed: ${res.status}`);
}

export async function ingestPdf(pdfKey: string, mode: IngestMode, topic?: string): Promise<{ session_id: string }> {
  const res = await fetch('/api/ingest', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ pdf_key: pdfKey, mode, topic: topic || undefined }),
  });
  if (!res.ok) throw new Error(`ingest failed: ${res.status} ${await res.text()}`);
  return res.json();
}

export async function getIngestStatus(sessionId: string): Promise<IngestStatus> {
  const res = await fetch(`/api/ingest/${encodeURIComponent(sessionId)}`);
  if (!res.ok) throw new Error(`status check failed: ${res.status}`);
  return res.json();
}

// Runs `task` over `items` with at most `limit` in flight at once, rather
// than Promise.all's unbounded concurrency — see MAX_CONCURRENT_UPLOADS.
export async function runWithConcurrency<T>(items: T[], limit: number, task: (item: T) => Promise<void>): Promise<void> {
  let next = 0;
  async function worker() {
    while (next < items.length) {
      const item = items[next++];
      await task(item);
    }
  }
  await Promise.all(Array.from({ length: Math.min(limit, items.length) }, worker));
}
