import { router } from 'expo-router';
import { useShareIntentContext } from 'expo-share-intent';
import { useState } from 'react';
import { ActivityIndicator, StyleSheet } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { ThemedText } from '@/components/themed-text';
import { ThemedView } from '@/components/themed-view';
import { Spacing } from '@/constants/theme';
import { ingest, type IngestPayload } from '@/lib/api';
import { toIngestPayload } from '@/lib/shareIntent';

type Status = 'idle' | 'sending' | 'sent' | 'error';

export default function ShareScreen() {
  const { shareIntent, resetShareIntent } = useShareIntentContext();
  const [status, setStatus] = useState<Status>('idle');
  const [error, setError] = useState<string | null>(null);

  const payload: IngestPayload | null = toIngestPayload(shareIntent);

  async function handleSend() {
    if (!payload) return;
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
        {!payload && (
          <ThemedText>Nothing shareable was detected — closing this and try again.</ThemedText>
        )}

        {payload && status === 'idle' && (
          <>
            <ThemedText type="smallBold">
              {'url' in payload ? 'Link detected' : 'Text detected'}
            </ThemedText>
            <ThemedView type="backgroundElement" style={styles.preview}>
              <ThemedText numberOfLines={6}>
                {'url' in payload ? payload.url : payload.text}
              </ThemedText>
            </ThemedView>
            <ThemedText type="link" onPress={handleSend} style={styles.action}>
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
    gap: Spacing.three,
  },
  preview: {
    padding: Spacing.three,
    borderRadius: Spacing.two,
  },
  action: {
    textAlign: 'center',
    marginTop: Spacing.two,
  },
  center: {
    alignItems: 'center',
    gap: Spacing.two,
  },
  hint: {
    opacity: 0.7,
  },
});
