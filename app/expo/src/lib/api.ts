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

export type IngestPayload = { text: string } | { url: string };

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
  source_url?: string;
  date?: string;
  tags?: string[];
  created_at?: string;
};

export type ListItemsResult =
  | { ok: true; items: Item[] }
  | { ok: false; error: string };

export async function listItems(limit = 30): Promise<ListItemsResult> {
  const result = await apiFetch<{ items: Item[] }>(`/items?limit=${limit}`);
  if (!result.ok) return result;
  const items = [...result.data.items].sort((a, b) =>
    (b.created_at ?? '').localeCompare(a.created_at ?? '')
  );
  return { ok: true, items };
}
