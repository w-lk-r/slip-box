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
 * expects: exactly one of {url} or {text} (+ optional source_url).
 */
export function toIngestPayload(shareIntent: ShareIntentLike): IngestPayload | null {
  const text = shareIntent.text?.trim();

  // Real text content beats webUrl, not the other way around — some apps
  // (Kindle sharing a highlight) attach both the quote AND a link back to
  // the source in the same share. The quote is the actual content to
  // ingest; the link is a citation for it, not a substitute — same
  // source_url mechanism already used for a client-fetched YouTube
  // transcript. Previously webUrl was checked first, which silently
  // discarded the quote and ingested just the book's product-page link.
  if (text && !URL_PATTERN.test(text)) {
    return shareIntent.webUrl ? { text, source_url: shareIntent.webUrl } : { text };
  }
  if (shareIntent.webUrl) {
    return { url: shareIntent.webUrl };
  }
  if (text) {
    // text itself was a bare URL (e.g. a link shared as a Message).
    return { url: text };
  }
  return null;
}
