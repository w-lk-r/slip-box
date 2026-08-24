import { router, useLocalSearchParams } from 'expo-router';
import { useEffect, useState } from 'react';
import { Pressable, StyleSheet, TextInput } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { ThemedText } from '@/components/themed-text';
import { ThemedView } from '@/components/themed-view';
import { Spacing } from '@/constants/theme';
import { useTheme } from '@/hooks/use-theme';
import { addIndexKeyword, getIndex, type IndexEntry } from '@/lib/api';

// Curation surface for docs/frontend-ux-spec.md's Index Cards: a keyword
// pointing at 1-3 entry notes, distinct from tags (automatic, exhaustive) by
// being sparse and hand-picked. Existing keywords are offered as tappable
// suggestions to encourage reuse over near-duplicate fragmentation
// ("Sleep" vs "sleep quality") — the whole point is a small, stable set.
export default function IndexKeywordScreen() {
  const theme = useTheme();
  const { noteId } = useLocalSearchParams<{ noteId: string }>();
  const [existing, setExisting] = useState<IndexEntry[]>([]);
  const [input, setInput] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getIndex().then((result) => {
      if (result.ok) setExisting(result.entries);
    });
  }, []);

  async function save(keyword: string) {
    const trimmed = keyword.trim();
    if (!trimmed || !noteId || saving) return;
    setSaving(true);
    const result = await addIndexKeyword(noteId, trimmed);
    setSaving(false);
    if (result.ok) {
      router.back();
    } else {
      setError(result.error);
    }
  }

  return (
    <ThemedView style={styles.container}>
      <SafeAreaView style={styles.safeArea}>
        <ThemedText type="subtitle">Add to index</ThemedText>
        <ThemedText type="small" style={styles.hint}>
          Keep it sparse — a keyword should point at only a couple of entry notes.
        </ThemedText>

        <TextInput
          value={input}
          onChangeText={setInput}
          placeholder="New keyword"
          placeholderTextColor={theme.textSecondary}
          autoCapitalize="none"
          autoCorrect={false}
          onSubmitEditing={() => save(input)}
          style={[styles.input, { color: theme.text }]}
        />
        <ThemedText
          type="link"
          onPress={input.trim() ? () => save(input) : undefined}
          themeColor={input.trim() ? undefined : 'textSecondary'}
          style={styles.saveButton}
        >
          {saving ? 'Saving…' : 'Add'}
        </ThemedText>

        {error && (
          <ThemedText type="small" style={styles.error}>
            {error}
          </ThemedText>
        )}

        {existing.length > 0 && (
          <>
            <ThemedText type="small" themeColor="textSecondary" style={styles.suggestionsLabel}>
              Or add to an existing keyword
            </ThemedText>
            {existing.map((entry) => (
              <Pressable key={entry.keyword} onPress={() => save(entry.keyword)}>
                <ThemedView type="backgroundElement" style={styles.suggestionRow}>
                  <ThemedText>{entry.keyword}</ThemedText>
                  <ThemedText type="small" themeColor="textSecondary">
                    {entry.notes.length} {entry.notes.length === 1 ? 'entry' : 'entries'}
                  </ThemedText>
                </ThemedView>
              </Pressable>
            ))}
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
  hint: {
    opacity: 0.7,
  },
  input: {
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: '#8888',
    borderRadius: Spacing.two,
    padding: Spacing.three,
    fontSize: 16,
    marginTop: Spacing.two,
  },
  saveButton: {
    textAlign: 'center',
    marginTop: Spacing.one,
  },
  error: {
    opacity: 0.8,
  },
  suggestionsLabel: {
    marginTop: Spacing.three,
  },
  suggestionRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: Spacing.three,
    borderRadius: Spacing.two,
    marginBottom: Spacing.two,
  },
});
