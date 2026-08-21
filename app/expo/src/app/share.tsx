import { router } from 'expo-router';
import { useShareIntentContext } from 'expo-share-intent';
import { useEffect, useState } from 'react';
import { ActivityIndicator, Pressable, StyleSheet, TextInput } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { ThemedText } from '@/components/themed-text';
import { ThemedView } from '@/components/themed-view';
import { Spacing } from '@/constants/theme';
import { useTheme } from '@/hooks/use-theme';
import { ingest, type IngestMode, type IngestPayload } from '@/lib/api';
import { toIngestPayload } from '@/lib/shareIntent';
import { fetchYoutubeContent, isYoutubeUrl, type YoutubeContent } from '@/lib/youtube';

type Status = 'idle' | 'sending' | 'sent' | 'error';

const MODE_OPTIONS: { value: IngestMode; label: string; hint: string }[] = [
  { value: 'auto', label: 'Auto', hint: "Agent decides — one note, or several if there's a lot here" },
  { value: 'single', label: 'One idea', hint: 'Exactly one note — pick a topic below, or let it choose' },
  { value: 'all', label: 'All ideas', hint: 'One note per distinct idea in the source' },
];

function ModePicker({ mode, onChange }: { mode: IngestMode; onChange: (m: IngestMode) => void }) {
  const theme = useTheme();
  return (
    <ThemedView style={styles.modeRow}>
      {MODE_OPTIONS.map((opt) => {
        const selected = opt.value === mode;
        return (
          <Pressable key={opt.value} onPress={() => onChange(opt.value)} style={styles.modeChipWrap}>
            <ThemedView
              type={selected ? 'backgroundSelected' : 'backgroundElement'}
              style={styles.modeChip}
            >
              <ThemedText type="small" themeColor={selected ? 'text' : 'textSecondary'}>
                {opt.label}
              </ThemedText>
            </ThemedView>
          </Pressable>
        );
      })}
    </ThemedView>
  );
}

export default function ShareScreen() {
  const theme = useTheme();
  const { shareIntent, resetShareIntent } = useShareIntentContext();
  const [status, setStatus] = useState<Status>('idle');
  const [error, setError] = useState<string | null>(null);
  const [mode, setMode] = useState<IngestMode>('auto');
  const [topic, setTopic] = useState('');
  const [youtubeContent, setYoutubeContent] = useState<YoutubeContent | null>(null);
  const [youtubeLoading, setYoutubeLoading] = useState(false);

  const basePayload = toIngestPayload(shareIntent);
  const shareUrl = basePayload && 'url' in basePayload ? basePayload.url : null;

  // A shared link that's YouTube gets its transcript fetched from the phone's
  // own network connection before send — AWS's IPs are blocked by YouTube's
  // transcript endpoint, the phone's aren't. Falls back to the raw URL (and
  // the backend's own graceful "no transcript" handling) if this fails.
  useEffect(() => {
    setYoutubeContent(null);
    if (shareUrl && isYoutubeUrl(shareUrl)) {
      setYoutubeLoading(true);
      fetchYoutubeContent(shareUrl)
        .then(setYoutubeContent)
        .finally(() => setYoutubeLoading(false));
    }
  }, [shareUrl]);

  const topicValue = mode === 'single' && topic.trim() ? topic.trim() : undefined;
  const payload: IngestPayload | null = basePayload
    ? youtubeContent
      ? { text: youtubeContent.text, source_url: youtubeContent.sourceUrl, mode, topic: topicValue }
      : { ...basePayload, mode, topic: topicValue }
    : null;

  async function handleSend() {
    if (!payload || youtubeLoading) return;
    setStatus('sending');
    const result = await ingest(payload);
    if (result.ok) {
      setStatus('sent');
    } else {
      setStatus('error');
      setError(result.error);
    }
  }

  function handleDone() {
    resetShareIntent();
    router.back();
  }

  return (
    <ThemedView style={styles.container}>
      <SafeAreaView style={styles.safeArea}>
        {!basePayload && (
          <ThemedText>Nothing shareable was detected — closing this and try again.</ThemedText>
        )}

        {basePayload && status === 'idle' && (
          <>
            <ThemedText type="smallBold">
              {youtubeContent
                ? 'YouTube transcript fetched'
                : youtubeLoading
                  ? 'Fetching YouTube transcript…'
                  : 'url' in basePayload
                    ? 'Link detected'
                    : 'Text detected'}
            </ThemedText>
            <ThemedView type="backgroundElement" style={styles.preview}>
              {youtubeLoading ? (
                <ActivityIndicator />
              ) : (
                <ThemedText numberOfLines={6}>
                  {youtubeContent
                    ? youtubeContent.text
                    : 'url' in basePayload
                      ? basePayload.url
                      : basePayload.text}
                </ThemedText>
              )}
            </ThemedView>

            <ThemedText type="small" themeColor="textSecondary">
              How many notes?
            </ThemedText>
            <ModePicker mode={mode} onChange={setMode} />
            <ThemedText type="small" themeColor="textSecondary" style={styles.modeHint}>
              {MODE_OPTIONS.find((o) => o.value === mode)?.hint}
            </ThemedText>

            {mode === 'single' && (
              <TextInput
                value={topic}
                onChangeText={setTopic}
                placeholder="Optional: which idea? (leave blank to let it choose)"
                placeholderTextColor={theme.textSecondary}
                style={[styles.topicInput, { color: theme.text }]}
              />
            )}

            <ThemedText
              type="link"
              onPress={youtubeLoading ? undefined : handleSend}
              themeColor={youtubeLoading ? 'textSecondary' : undefined}
              style={styles.action}
            >
              Send to Slip Box
            </ThemedText>
          </>
        )}

        {status === 'sending' && (
          <ThemedView style={styles.center}>
            <ActivityIndicator />
            <ThemedText type="small" style={styles.center}>
              Sending…
            </ThemedText>
          </ThemedView>
        )}

        {status === 'sent' && (
          <>
            <ThemedText type="smallBold">Sent ✓</ThemedText>
            <ThemedText type="small" style={styles.hint}>
              Slip Box is processing it now — it'll show up in your items shortly.
            </ThemedText>
            <ThemedText type="link" onPress={handleDone} style={styles.action}>
              Done
            </ThemedText>
          </>
        )}

        {status === 'error' && (
          <>
            <ThemedText type="smallBold">Couldn't send it</ThemedText>
            <ThemedText type="small" style={styles.hint}>
              {error}
            </ThemedText>
            <ThemedText type="link" onPress={handleSend} style={styles.action}>
              Try again
            </ThemedText>
          </>
        )}
      </SafeAreaView>
    </ThemedView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
  },
  safeArea: {
    flex: 1,
    padding: Spacing.four,
    gap: Spacing.two,
  },
  preview: {
    padding: Spacing.three,
    borderRadius: Spacing.two,
    marginBottom: Spacing.two,
  },
  modeRow: {
    flexDirection: 'row',
    gap: Spacing.two,
  },
  modeChipWrap: {
    flex: 1,
  },
  modeChip: {
    paddingVertical: Spacing.two,
    borderRadius: Spacing.two,
    alignItems: 'center',
  },
  modeHint: {
    opacity: 0.8,
  },
  topicInput: {
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: '#8888',
    borderRadius: Spacing.two,
    padding: Spacing.three,
    fontSize: 15,
    marginTop: Spacing.one,
  },
  action: {
    textAlign: 'center',
    marginTop: Spacing.three,
  },
  center: {
    alignItems: 'center',
    gap: Spacing.two,
  },
  hint: {
    opacity: 0.7,
  },
});
