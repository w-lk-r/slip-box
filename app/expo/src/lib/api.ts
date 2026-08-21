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

export async function ingest(payload: IngestPayload): Promise<IngestResult> {
  const apiKey = await getApiKey();
  if (!apiKey) {
    return { ok: false, error: 'No API key set — add one in Settings first.' };
  }

  try {
    const response = await fetch(`${BASE_URL}/ingest`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'x-api-key': apiKey,
      },
      body: JSON.stringify(payload),
    });

    if (!response.ok) {
      const body = await response.text();
      return { ok: false, error: `${response.status}: ${body}` };
    }

    const data = (await response.json()) as { session_id: string };
    return { ok: true, sessionId: data.session_id };
  } catch (err) {
    return { ok: false, error: err instanceof Error ? err.message : String(err) };
  }
}
