import { useState } from 'react';
import { ActivityIndicator, StyleSheet, TextInput } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import ModePicker, { MODE_OPTIONS } from '@/components/mode-picker';
import { ThemedText } from '@/components/themed-text';
import { ThemedView } from '@/components/themed-view';
import { Spacing } from '@/constants/theme';
import { useTheme } from '@/hooks/use-theme';
import { toIngestPayload } from '@/lib/shareIntent';
import { useIngestFlow, type IngestSource } from '@/lib/useIngestFlow';

export default function SubmitScreen() {
  const theme = useTheme();
  const [input, setInput] = useState('');

  // Same URL-vs-plain-text detection share.tsx's share-sheet path already
  // uses — a bare link becomes {url}, anything else becomes {text}.
  const trimmed = input.trim();
  const source: IngestSource | null = trimmed ? toIngestPayload({ text: trimmed }) : null;

  const { status, error, mode, setMode, topic, setTopic, outcome, handleSend, reset } = useIngestFlow(source);

  async function handleSendAndClear() {
    await handleSend();
  }

  function handleSendAnother() {
    setInput('');
    reset();
  }

  return (
    <ThemedView style={styles.container}>
      <SafeAreaView style={styles.safeArea} edges={['bottom']}>
        {status === 'idle' && (
          <>
            <ThemedText type="small" themeColor="textSecondary">
              Paste a link or some text
            </ThemedText>
            <TextInput
              value={input}
              onChangeText={setInput}
              placeholder="https://... or paste a passage"
              placeholderTextColor={theme.textSecondary}
              multiline
              autoCapitalize="none"
              style={[styles.input, { color: theme.text }]}
            />

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
              onPress={source ? handleSendAndClear : undefined}
              themeColor={source ? undefined : 'textSecondary'}
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
                Slip Box is processing it now — check the Notes tab shortly.
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
            <ThemedText type="link" onPress={handleSendAnother} style={styles.action}>
              Add another
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
  input: {
    minHeight: 100,
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: '#8888',
    borderRadius: Spacing.two,
    padding: Spacing.three,
    fontSize: 16,
    textAlignVertical: 'top',
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
