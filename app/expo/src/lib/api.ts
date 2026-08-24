import * as SecureStore from 'expo-secure-store';

// API Gateway endpoint for the Slip Box FastAPI backend (agentcore/cdk/lib/api-stack.ts).
// Single deployment target for now — hardcode rather than add env-var plumbing for one value.
const BASE_URL = 'https://q8gysyecd0.execute-api.ap-southeast-2.amazonaws.com/prod';

const API_KEY_STORE_KEY = 'slipbox_api_key';

export async function getApiKey(): Promise<string | null> {
  return SecureStore.getItemAsync(API_KEY_STORE_KEY);
}

export async function setApiKey(key: string): Promise<void> {
  await SecureStore.setItemAsync(API_KEY_STORE_KEY, key);
}

export async function clearApiKey(): Promise<void> {
  await SecureStore.deleteItemAsync(API_KEY_STORE_KEY);
}

export type IngestMode = 'auto' | 'single' | 'all';

export type IngestOptions = {
  mode?: IngestMode;
  topic?: string;
};

// source_url is only meaningful alongside text — for content the client
// already fetched itself (e.g. a YouTube transcript pulled client-side, see
// lib/youtube.ts) and wants attributed to its real source in the note.
export type IngestPayload = ({ text: string; source_url?: string } | { url: string }) & IngestOptions;

export type IngestResult =
  | { ok: true; sessionId: string }
  | { ok: false; error: string };

type ApiResult<T> = { ok: true; data: T } | { ok: false; error: string };

async function apiFetch<T>(path: string, init?: RequestInit): Promise<ApiResult<T>> {
  const apiKey = await getApiKey();
  if (!apiKey) {
    return { ok: false, error: 'No API key set — add one in Settings first.' };
  }

  try {
    const response = await fetch(`${BASE_URL}${path}`, {
      ...init,
      headers: {
        'Content-Type': 'application/json',
        'x-api-key': apiKey,
        ...init?.headers,
      },
    });

    if (!response.ok) {
      const body = await response.text();
      return { ok: false, error: `${response.status}: ${body}` };
    }

    return { ok: true, data: (await response.json()) as T };
  } catch (err) {
    return { ok: false, error: err instanceof Error ? err.message : String(err) };
  }
}

export async function ingest(payload: IngestPayload): Promise<IngestResult> {
  const result = await apiFetch<{ session_id: string }>('/ingest', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
  if (!result.ok) return result;
  return { ok: true, sessionId: result.data.session_id };
}

export type NoteRef = { note_id: string; title: string };

export type IngestStatusResult =
  | {
      ok: true;
      status: 'processing' | 'complete' | 'error';
      notesCreated: NoteRef[];
      skippedReason: string | null;
      error: string | null;
    }
  | { ok: false; error: string };

// Real completion status, replacing a client-only timeout guess — see
// docs/future-scope.md's "Real ingest-completion tracking". Written by the
// Worker (initial "processing") and the agent's own hook (final outcome).
export async function getIngestStatus(sessionId: string): Promise<IngestStatusResult> {
  const result = await apiFetch<{
    status: 'processing' | 'complete' | 'error';
    notes_created: NoteRef[];
    skipped_reason: string | null;
    error: string | null;
  }>(`/ingest/${encodeURIComponent(sessionId)}`);
  if (!result.ok) return result;
  return {
    ok: true,
    status: result.data.status,
    notesCreated: result.data.notes_created,
    skippedReason: result.data.skipped_reason,
    error: result.data.error,
  };
}

export type ItemType = 'literature-note' | 'summary-card' | 'permanent-note';

export type Item = {
  note_id: string;
  type: ItemType;
  title: string;
  authored_by?: string;
  date?: string;
  tags?: string[];
  created_at?: string;
  source_id?: string;
};

export type ListItemsResult =
  | { ok: true; items: Item[]; cursor?: string }
  | { ok: false; error: string };

/**
 * One page of items, unsorted (backend pagination is a raw DynamoDB Scan
 * cursor, not a chronological offset — the caller accumulates pages and
 * sorts client-side rather than assuming each page is itself in date order).
 */
export async function listItems(limit = 20, cursor?: string, type?: ItemType): Promise<ListItemsResult> {
  const params = new URLSearchParams({ limit: String(limit) });
  if (cursor) params.set('cursor', cursor);
  if (type) params.set('type', type);
  const result = await apiFetch<{ items: Item[]; cursor?: string }>(`/items?${params}`);
  if (!result.ok) return result;
  return { ok: true, items: result.data.items, cursor: result.data.cursor };
}

export type Source = {
  source_id: string;
  title: string;
  url: string | null;
  type: 'web' | 'youtube' | 'pdf';
  author: string | null;
};

export type ListSourcesResult = { ok: true; sources: Source[] } | { ok: false; error: string };

export async function listSources(): Promise<ListSourcesResult> {
  const result = await apiFetch<{ sources: Source[] }>('/sources');
  if (!result.ok) return result;
  return { ok: true, sources: result.data.sources };
}

export type EdgeType = 'SUPPORTS' | 'CONTRADICTS' | 'EXTENDS' | 'RELATED_TO' | 'GROUNDED_IN';

export type OutgoingEdge = {
  edge_id: string;
  to_id: string;
  to_title: string;
  // Non-empty when the neighbor is itself a curated index entry — the "sub
  // index card" signal (docs/frontend-ux-spec.md's Index Cards section):
  // discovered by walking edges from an entry note, not a separate screen.
  to_index_keywords: string[];
  type: EdgeType;
  confidence: number;
};

export type IncomingEdge = {
  edge_id: string;
  from_id: string;
  from_title: string;
  from_index_keywords: string[];
  type: EdgeType;
  confidence: number;
};

export type ItemDetail = Item & {
  source: Source | null;
  body: string;
  connections: Record<string, string[]>;
  outgoing_edges: OutgoingEdge[];
  incoming_edges: IncomingEdge[];
  // Absent (not []) when this note isn't a curated entry point for anything —
  // sparse, matching the backend's own DynamoDB convention.
  index_keywords?: string[];
};

export type GetItemResult =
  | { ok: true; item: ItemDetail }
  | { ok: false; error: string };

export async function getItem(noteId: string): Promise<GetItemResult> {
  const result = await apiFetch<ItemDetail>(`/items/${encodeURIComponent(noteId)}`);
  if (!result.ok) return result;
  return { ok: true, item: result.data };
}

export type ReviewQueueItem = Item & {
  outgoing_edges: OutgoingEdge[];
  incoming_edges: IncomingEdge[];
};

export type GetReviewQueueResult =
  | { ok: true; items: ReviewQueueItem[] }
  | { ok: false; error: string };

export async function getReviewQueue(): Promise<GetReviewQueueResult> {
  const result = await apiFetch<{ items: ReviewQueueItem[] }>('/items/review-queue');
  if (!result.ok) return result;
  return { ok: true, items: result.data.items };
}

export type MarkReviewedResult = { ok: true } | { ok: false; error: string };

export async function markReviewed(noteId: string): Promise<MarkReviewedResult> {
  const result = await apiFetch(`/items/${encodeURIComponent(noteId)}/review`, { method: 'POST' });
  if (!result.ok) return result;
  return { ok: true };
}

export type DeleteItemResult = { ok: true } | { ok: false; error: string };

// Only removes the S3 object(s) server-side — the actual DynamoDB cascade
// (edges, summary-card membership) happens asynchronously via the
// reconciler once it sees the S3 delete event, so this note may briefly
// still resolve via getItem right after this resolves. Callers should
// remove it from local state optimistically rather than waiting to poll.
export async function deleteItem(noteId: string): Promise<DeleteItemResult> {
  const result = await apiFetch(`/items/${encodeURIComponent(noteId)}`, { method: 'DELETE' });
  if (!result.ok) return result;
  return { ok: true };
}

// A keyword pointing at its 1-3 curated entry notes — Luhmann's second,
// deliberately sparse index alongside the numbered slips. Distinct from tags
// (automatic, exhaustive) by design. See docs/frontend-ux-spec.md's Index
// Cards section.
export type IndexEntry = {
  keyword: string;
  notes: Pick<Item, 'note_id' | 'title' | 'type'>[];
};

export type GetIndexResult = { ok: true; entries: IndexEntry[] } | { ok: false; error: string };

// Backend returns entries pre-sorted alphabetically by keyword — the index
// is a filed, curated structure, not a chronological feed like the Recent
// box (see (tabs)/index.tsx's own comment on why "newest" doesn't apply here).
export async function getIndex(): Promise<GetIndexResult> {
  const result = await apiFetch<{ entries: IndexEntry[] }>('/index');
  if (!result.ok) return result;
  return { ok: true, entries: result.data.entries };
}

export type IndexKeywordResult =
  | { ok: true; indexKeywords: string[] }
  | { ok: false; error: string };

export async function addIndexKeyword(noteId: string, keyword: string): Promise<IndexKeywordResult> {
  const result = await apiFetch<{ index_keywords?: string[] }>(`/items/${encodeURIComponent(noteId)}/index-keywords`, {
    method: 'POST',
    body: JSON.stringify({ keyword }),
  });
  if (!result.ok) return result;
  return { ok: true, indexKeywords: result.data.index_keywords ?? [] };
}

// Multi-select trigger for an on-demand summary card, grounded in exactly
// the user-picked note_ids (docs — the selection-first pattern CLAUDE.md
// already describes for PermanentNote writing, applied here to synthesis).
// Reuses the exact same async-invoke-and-poll shape as ingest(): a
// session_id to feed into addPendingIngestion/getIngestStatus, nothing new
// on the polling side.
export async function summarize(noteIds: string[]): Promise<IngestResult> {
  const result = await apiFetch<{ session_id: string }>('/summarize', {
    method: 'POST',
    body: JSON.stringify({ note_ids: noteIds }),
  });
  if (!result.ok) return result;
  return { ok: true, sessionId: result.data.session_id };
}

export async function removeIndexKeyword(noteId: string, keyword: string): Promise<IndexKeywordResult> {
  const result = await apiFetch<{ index_keywords?: string[] }>(
    `/items/${encodeURIComponent(noteId)}/index-keywords/${encodeURIComponent(keyword)}`,
    { method: 'DELETE' }
  );
  if (!result.ok) return result;
  return { ok: true, indexKeywords: result.data.index_keywords ?? [] };
}
