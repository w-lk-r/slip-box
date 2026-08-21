import { fetchTranscript, YoutubeTranscriptError } from 'youtube-transcript';

// Mirrors app/MyAgent/tools/notes.py's _youtube_video_id — same URL shapes,
// same reason to run client-side: YouTube blocks the transcript endpoint
// from cloud-provider IPs (AWS included), so the backend agent can't
// reliably fetch it, but the phone's own network connection isn't blocked.
export function extractYoutubeVideoId(url: string): string | null {
  let parsed: URL;
  try {
    parsed = new URL(url);
  } catch {
    return null;
  }
  let host = parsed.hostname.toLowerCase();
  for (const prefix of ['www.', 'm.', 'music.']) {
    if (host.startsWith(prefix)) {
      host = host.slice(prefix.length);
      break;
    }
  }
  if (host === 'youtu.be') {
    return parsed.pathname.replace(/^\//, '').split('/')[0] || null;
  }
  if (host === 'youtube.com') {
    if (parsed.pathname === '/watch') {
      return parsed.searchParams.get('v');
    }
    for (const prefix of ['/shorts/', '/embed/', '/live/']) {
      if (parsed.pathname.startsWith(prefix)) {
        return parsed.pathname.slice(prefix.length).split('/')[0] || null;
      }
    }
  }
  return null;
}

export function isYoutubeUrl(url: string): boolean {
  return extractYoutubeVideoId(url) !== null;
}

export type YoutubeContent = { text: string; sourceUrl: string };

async function fetchOEmbed(url: string): Promise<{ title: string; channel: string } | null> {
  try {
    const resp = await fetch(`https://www.youtube.com/oembed?url=${encodeURIComponent(url)}&format=json`);
    if (!resp.ok) return null;
    const data = await resp.json();
    return data.title ? { title: data.title, channel: data.author_name } : null;
  } catch {
    return null;
  }
}

/**
 * Fetches a YouTube video's transcript (plus title/channel for context the
 * transcript alone doesn't carry) from the phone's own network connection.
 * Returns null only when there's nothing usable at all (private/deleted
 * video) — the caller should fall back to sending the raw URL in that case,
 * which the backend's own oEmbed-only fallback can still degrade to
 * gracefully.
 */
export async function fetchYoutubeContent(url: string): Promise<YoutubeContent | null> {
  const videoId = extractYoutubeVideoId(url);
  if (!videoId) return null;

  const meta = await fetchOEmbed(url);
  const header = meta ? `Title: ${meta.title}\nChannel: ${meta.channel}\n\n` : '';

  try {
    const segments = await fetchTranscript(videoId);
    const transcript = segments.map((s) => s.text).join(' ');
    return { text: header + transcript, sourceUrl: url };
  } catch (err) {
    if (!(err instanceof YoutubeTranscriptError) || !meta) return null;
    return {
      text: `${header}No transcript is available for this video — write the note from the title/channel alone if that's enough.`,
      sourceUrl: url,
    };
  }
}
