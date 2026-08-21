// Server-only — never imported from a "use client" component. Holds the
// backend API key and proxies requests to it, so the browser only ever
// talks to this app's own origin (no CORS, no key ever reaching the client).
const BACKEND_BASE_URL = process.env.BACKEND_BASE_URL;
const API_KEY = process.env.API_KEY;

export async function backendFetch(path: string, init?: RequestInit): Promise<Response> {
  if (!BACKEND_BASE_URL || !API_KEY) {
    throw new Error('BACKEND_BASE_URL and API_KEY must be set (see .env.local.sample)');
  }
  return fetch(`${BACKEND_BASE_URL}${path}`, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      'x-api-key': API_KEY,
      ...init?.headers,
    },
    cache: 'no-store',
  });
}
