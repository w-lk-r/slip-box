import type { IngestPayload } from '@/lib/api';

// A bare URL check — some apps (e.g. sharing a link as a message) put the URL
// straight into `text` rather than the dedicated `webUrl` field, so `text`
// needs its own check rather than assuming only `webUrl` ever carries a link.
const URL_PATTERN = /^https?:\/\/\S+$/i;

export type ShareIntentLike = {
  text?: string | null;
  webUrl?: string | null;
};

/**
 * Maps expo-share-intent's { text, webUrl, ... } shape to what POST /ingest
 * expects: exactly one of {url} or {text}.
 */
export function toIngestPayload(shareIntent: ShareIntentLike): IngestPayload | null {
  if (shareIntent.webUrl) {
    return { url: shareIntent.webUrl };
  }
  const text = shareIntent.text?.trim();
  if (!text) {
    return null;
  }
  if (URL_PATTERN.test(text)) {
    return { url: text };
  }
  return { text };
}
