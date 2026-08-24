import { router } from 'expo-router';
import { useState } from 'react';
import { Pressable, StyleSheet, View } from 'react-native';

import { ThemedText } from '@/components/themed-text';
import { ThemedView } from '@/components/themed-view';
import { Spacing } from '@/constants/theme';
import type { IndexEntry } from '@/lib/api';

// 1-3 entry notes per keyword by design (docs/frontend-ux-spec.md's Index
// Cards section) — an inline accordion covers that few rows, no separate
// screen needed the way review-stack.tsx's larger per-source lists needed one.
export default function IndexCardRow({ entry }: { entry: IndexEntry }) {
  const [expanded, setExpanded] = useState(false);

  if (entry.notes.length === 1) {
    const note = entry.notes[0];
    return (
      <Pressable onPress={() => router.push(`/note/${encodeURIComponent(note.note_id)}`)}>
        <ThemedView type="backgroundElement" style={styles.row}>
          <View style={styles.rowMain}>
            <ThemedText type="smallBold">{entry.keyword}</ThemedText>
            <ThemedText type="small" themeColor="textSecondary" numberOfLines={2}>
              {note.title}
            </ThemedText>
          </View>
          <ThemedText type="small" themeColor="textSecondary">
            ›
          </ThemedText>
        </ThemedView>
      </Pressable>
    );
  }

  return (
    <ThemedView type="backgroundElement" style={styles.group}>
      <Pressable onPress={() => setExpanded((e) => !e)} style={styles.row}>
        <View style={styles.rowMain}>
          <ThemedText type="smallBold">{entry.keyword}</ThemedText>
          <ThemedText type="small" themeColor="textSecondary">
            {entry.notes.length} entries
          </ThemedText>
        </View>
        <ThemedText type="small" themeColor="textSecondary">
          {expanded ? '⌄' : '›'}
        </ThemedText>
      </Pressable>
      {expanded &&
        entry.notes.map((note) => (
          <Pressable key={note.note_id} onPress={() => router.push(`/note/${encodeURIComponent(note.note_id)}`)}>
            <View style={styles.subRow}>
              <ThemedText numberOfLines={2} style={styles.subRowText}>
                {note.title}
              </ThemedText>
              <ThemedText type="small" themeColor="textSecondary">
                ›
              </ThemedText>
            </View>
          </Pressable>
        ))}
    </ThemedView>
  );
}

const styles = StyleSheet.create({
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: Spacing.two,
    padding: Spacing.three,
    borderRadius: Spacing.two,
  },
  rowMain: {
    flex: 1,
    gap: Spacing.half,
  },
  group: {
    borderRadius: Spacing.two,
    overflow: 'hidden',
  },
  subRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: Spacing.two,
    paddingVertical: Spacing.two,
    paddingHorizontal: Spacing.three,
    paddingLeft: Spacing.four,
  },
  subRowText: {
    flex: 1,
  },
});
