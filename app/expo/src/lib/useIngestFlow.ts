import { useEffect, useState } from 'react';

import { getIngestStatus, ingest, type IngestMode, type NoteRef } from '@/lib/api';
import { addPendingIngestion } from '@/lib/pendingIngestions';

export type IngestFlowStatus = 'idle' | 'sending' | 'sent' | 'error';

export type IngestOutcome = { notesCreated: NoteRef[]; skippedReason: string | null } | { error: string };

// The "what" being sent, without mode/topic — this hook owns those, since
// they're driven by its own ModePicker/topic state, not by the caller.
export type IngestSource = { text: string; source_url?: string } | { url: string };

// Shared between share.tsx (source comes from the OS share sheet) and
// submit.tsx (source comes from typed input) — everything past "here's what
// to send" (mode picker state, send, poll for the real outcome) is
// identical, so it lives once here rather than twice.
export function useIngestFlow(source: IngestSource | null, extraSendGuard = false) {
  const [status, setStatus] = useState<IngestFlowStatus>('idle');
  const [error, setError] = useState<string | null>(null);
  const [mode, setMode] = useState<IngestMode>('auto');
  const [topic, setTopic] = useState('');
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [outcome, setOutcome] = useState<IngestOutcome | null>(null);

  // Poll the real outcome (which notes got created, or why none did) rather
  // than leaving "Slip Box is processing it now" as the final word — see
  // docs/future-scope.md's "Real ingest-completion tracking".
  useEffect(() => {
    if (!sessionId) return;
    let cancelled = false;
    const interval = setInterval(async () => {
      const result = await getIngestStatus(sessionId);
      if (cancelled || !result.ok || result.status === 'processing') return;
      if (result.status === 'error') {
        setOutcome({ error: result.error ?? 'Something went wrong.' });
      } else {
        setOutcome({ notesCreated: result.notesCreated, skippedReason: result.skippedReason });
      }
      clearInterval(interval);
    }, 3000);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, [sessionId]);

  async function handleSend() {
    if (!source || extraSendGuard) return;
    setStatus('sending');
    const result = await ingest({ ...source, mode, topic: mode === 'single' && topic.trim() ? topic.trim() : undefined });
    if (result.ok) {
      addPendingIngestion(result.sessionId);
      setSessionId(result.sessionId);
      setOutcome(null);
      setStatus('sent');
    } else {
      setStatus('error');
      setError(result.error);
    }
  }

  function reset() {
    setStatus('idle');
    setError(null);
    setSessionId(null);
    setOutcome(null);
  }

  return { status, error, mode, setMode, topic, setTopic, outcome, handleSend, reset };
}
