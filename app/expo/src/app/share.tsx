import { router } from 'expo-router';
import { useShareIntentContext } from 'expo-share-intent';
import { useEffect, useState } from 'react';
import { ActivityIndicator, StyleSheet, TextInput } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import ModePicker, { MODE_OPTIONS } from '@/components/mode-picker';
import { ThemedText } from '@/components/themed-text';
import { ThemedView } from '@/components/themed-view';
import { Spacing } from '@/constants/theme';
import { useTheme } from '@/hooks/use-theme';
import { useIngestFlow, type IngestSource } from '@/lib/useIngestFlow';
import { toIngestPayload } from '@/lib/shareIntent';
import { fetchYoutubeContent, isYoutubeUrl, type YoutubeContent } from '@/lib/youtube';

export default function ShareScreen() {
  const theme = useTheme();
  const { shareIntent, resetShareIntent } = useShareIntentContext();
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

  const source: IngestSource | null = basePayload
    ? youtubeContent
      ? { text: youtubeContent.text, source_url: youtubeContent.sourceUrl }
      : basePayload
    : null;

  const { status, error, mode, setMode, topic, setTopic, outcome, handleSend } = useIngestFlow(source, youtubeLoading);

  // dismissTo, not back(): this screen is a modal pushed on top of the tabs
  // by ShareIntentListener (app/_layout.tsx), often as the very first thing
  // rendered on a fresh cold-start-from-share-sheet launch — there may be no
  // prior screen for back() to resolve to at all, which is exactly how a
  // user ended up stranded here with no way out. dismissTo closes the modal
  // and lands on a specific screen underneath regardless of stack history.
  function handleClose(destination: '/' | '/review') {
    resetShareIntent();
    router.dismissTo(destination);
  }

  return (
    <ThemedView style={styles.container}>
      <SafeAreaView style={styles.safeArea}>
        {!basePayload && (
          <>
            <ThemedText>Nothing shareable was detected here.</ThemedText>
            <ThemedText type="link" onPress={() => handleClose('/')} style={styles.action}>
              Close
            </ThemedText>
          </>
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
            {!outcome && (
              <ThemedText type="small" style={styles.hint}>
                Slip Box is processing it now — it'll show up in your items shortly.
              </ThemedText>
            )}
            {outcome && 'error' in outcome && (
              <ThemedText type="small" style={styles.hint}>
                Something went wrong while processing: {outcome.error}
              </ThemedText>
            )}
            {outcome && 'notesCreated' in outcome && outcome.notesCreated.length > 0 && (
              <ThemedText type="small" style={styles.hint}>
                {outcome.notesCreated.length === 1
                  ? `Created "${outcome.notesCreated[0].title}".`
                  : `Created ${outcome.notesCreated.length} notes.`}
              </ThemedText>
            )}
            {outcome && 'notesCreated' in outcome && outcome.notesCreated.length === 0 && (
              <ThemedText type="small" style={styles.hint}>
                No note created — {outcome.skippedReason || "the agent didn't find anything worth saving here."}
              </ThemedText>
            )}
            <ThemedText type="link" onPress={() => handleClose('/review')} style={styles.action}>
              Done — go to Review
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
            <ThemedText type="link" themeColor="textSecondary" onPress={() => handleClose('/')} style={styles.action}>
              Close
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
