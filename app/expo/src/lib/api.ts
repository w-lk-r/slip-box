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

export type ItemType = 'literature-note' | 'summary-card' | 'permanent-note';

export type Item = {
  note_id: string;
  type: ItemType;
  title: string;
  authored_by?: string;
  date?: string;
  tags?: string[];
  created_at?: string;
};

export type ListItemsResult =
  | { ok: true; items: Item[]; cursor?: string }
  | { ok: false; error: string };

/**
 * One page of items, unsorted (backend pagination is a raw DynamoDB Scan
 * cursor, not a chronological offset — the caller accumulates pages and
 * sorts client-side rather than assuming each page is itself in date order).
 */
export async function listItems(limit = 20, cursor?: string): Promise<ListItemsResult> {
  const query = cursor ? `?limit=${limit}&cursor=${encodeURIComponent(cursor)}` : `?limit=${limit}`;
  const result = await apiFetch<{ items: Item[]; cursor?: string }>(`/items${query}`);
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

export type ItemDetail = Item & {
  source: Source | null;
  body: string;
  connections: Record<string, string[]>;
};

export type GetItemResult =
  | { ok: true; item: ItemDetail }
  | { ok: false; error: string };

export async function getItem(noteId: string): Promise<GetItemResult> {
  const result = await apiFetch<ItemDetail>(`/items/${encodeURIComponent(noteId)}`);
  if (!result.ok) return result;
  return { ok: true, item: result.data };
}
