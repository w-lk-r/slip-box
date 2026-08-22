import { useLocalSearchParams } from 'expo-router';
import { useEffect, useState } from 'react';
import { ActivityIndicator, Linking, Pressable, ScrollView, StyleSheet } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { ThemedText } from '@/components/themed-text';
import { ThemedView } from '@/components/themed-view';
import { Spacing } from '@/constants/theme';
import { getItem, type ItemDetail } from '@/lib/api';

const CONNECTION_LABEL: Record<string, string> = {
  supports: 'Supports',
  contradicts: 'Contradicts',
  extends: 'Extends',
  related_to: 'Related to',
  grounded_in: 'Grounded in',
};

// Frontmatter link entries are stored as "[[note_id|Title]]" — pull out just the title.
function linkTitle(entry: string): string {
  const match = entry.match(/^\[\[[^|]*\|(.+)\]\]$/);
  return match ? match[1] : entry;
}

export default function NoteDetailScreen() {
  const { noteId } = useLocalSearchParams<{ noteId: string }>();
  const [item, setItem] = useState<ItemDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!noteId) return;
    getItem(noteId).then((result) => {
      if (result.ok) setItem(result.item);
      else setError(result.error);
    });
  }, [noteId]);

  if (error) {
    return (
      <ThemedView style={styles.container}>
        <SafeAreaView style={styles.safeArea}>
          <ThemedText type="small">{error}</ThemedText>
        </SafeAreaView>
      </ThemedView>
    );
  }

  if (!item) {
    return (
      <ThemedView style={[styles.container, styles.center]}>
        <ActivityIndicator />
      </ThemedView>
    );
  }

  const connectionEntries = Object.entries(item.connections ?? {}).filter(
    ([, links]) => links.length > 0
  );

  return (
    <ThemedView style={styles.container}>
      <SafeAreaView style={styles.safeArea} edges={['bottom']}>
        <ScrollView contentContainerStyle={styles.scroll}>
          <ThemedText type="subtitle">{item.title}</ThemedText>

          <ThemedView style={styles.meta}>
            <ThemedText type="small" themeColor="textSecondary">
              {item.type}
            </ThemedText>
            {!!item.date && (
              <ThemedText type="small" themeColor="textSecondary">
                {item.date}
              </ThemedText>
            )}
          </ThemedView>

          {!!item.tags?.length && (
            <ThemedText type="small" themeColor="textSecondary">
              {item.tags.join(' · ')}
            </ThemedText>
          )}

          <ThemedText style={styles.body}>{item.body}</ThemedText>

          {!!item.source && (
            <Pressable
              disabled={!item.source.url}
              onPress={() => item.source!.url && Linking.openURL(item.source!.url)}
            >
              <ThemedText
                type="small"
                themeColor="textSecondary"
                numberOfLines={1}
                style={item.source.url ? styles.sourceLink : undefined}
              >
                Source: {item.source.title}
                {item.source.author ? ` — ${item.source.author}` : ''}
              </ThemedText>
            </Pressable>
          )}

          {connectionEntries.length > 0 && (
            <ThemedView style={styles.connections}>
              <ThemedText type="smallBold">Connections</ThemedText>
              {connectionEntries.map(([type, links]) => (
                <ThemedView key={type} style={styles.connectionGroup}>
                  <ThemedText type="small" themeColor="textSecondary">
                    {CONNECTION_LABEL[type] ?? type}
                  </ThemedText>
                  {links.map((link) => (
                    <ThemedText key={link} type="small" style={styles.connectionItem}>
                      {linkTitle(link)}
                    </ThemedText>
                  ))}
                </ThemedView>
              ))}
            </ThemedView>
          )}
        </ScrollView>
      </SafeAreaView>
    </ThemedView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
  },
  center: {
    alignItems: 'center',
    justifyContent: 'center',
  },
  safeArea: {
    flex: 1,
    paddingHorizontal: Spacing.four,
  },
  scroll: {
    paddingVertical: Spacing.three,
    gap: Spacing.three,
  },
  meta: {
    flexDirection: 'row',
    gap: Spacing.three,
  },
  body: {
    lineHeight: 24,
  },
  sourceLink: {
    textDecorationLine: 'underline',
  },
  connections: {
    gap: Spacing.two,
    marginTop: Spacing.two,
  },
  connectionGroup: {
    gap: Spacing.half,
  },
  connectionItem: {
    opacity: 0.85,
  },
});
