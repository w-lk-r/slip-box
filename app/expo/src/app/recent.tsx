import { Link, useFocusEffect } from 'expo-router';
import { useCallback, useState } from 'react';
import { ActivityIndicator, Pressable, RefreshControl, SectionList, StyleSheet } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { ThemedText } from '@/components/themed-text';
import { ThemedView } from '@/components/themed-view';
import { Spacing } from '@/constants/theme';
import { listItems, type Item } from '@/lib/api';

const PAGE_SIZE = 20;

const TYPE_LABEL: Record<Item['type'], string> = {
  'literature-note': 'note',
  'summary-card': 'summary',
  'permanent-note': 'idea',
};

function dateKey(item: Item): string {
  const iso = item.created_at ?? item.date;
  return iso ? iso.slice(0, 10) : 'unknown';
}

function sectionTitle(key: string): string {
  if (key === 'unknown') return 'Undated';
  const today = new Date().toISOString().slice(0, 10);
  const yesterday = new Date(Date.now() - 86_400_000).toISOString().slice(0, 10);
  if (key === today) return 'Today';
  if (key === yesterday) return 'Yesterday';
  return new Date(`${key}T00:00:00`).toLocaleDateString(undefined, {
    month: 'long',
    day: 'numeric',
    year: 'numeric',
  });
}

// Pages are raw DynamoDB scan chunks, not chronologically ordered — always
// sort the full accumulated set before grouping, don't assume page order.
function groupByDate(items: Item[]): { title: string; data: Item[] }[] {
  const sorted = [...items].sort((a, b) => (b.created_at ?? '').localeCompare(a.created_at ?? ''));
  const groups = new Map<string, Item[]>();
  for (const item of sorted) {
    const key = dateKey(item);
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key)!.push(item);
  }
  return Array.from(groups.entries()).map(([key, data]) => ({ title: sectionTitle(key), data }));
}

function ItemRow({ item }: { item: Item }) {
  return (
    <Link href={`/note/${item.note_id}`} asChild>
      <Pressable>
        <ThemedView type="backgroundElement" style={styles.row}>
          <ThemedText numberOfLines={2}>{item.title}</ThemedText>
          <ThemedText type="small" themeColor="textSecondary">
            {TYPE_LABEL[item.type] ?? item.type}
          </ThemedText>
        </ThemedView>
      </Pressable>
    </Link>
  );
}

export default function RecentScreen() {
  const [items, setItems] = useState<Item[]>([]);
  const [cursor, setCursor] = useState<string | undefined>();
  const [refreshing, setRefreshing] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);

  const loadFirstPage = useCallback(async () => {
    const result = await listItems(PAGE_SIZE);
    if (result.ok) {
      setItems(result.items);
      setCursor(result.cursor);
      setError(null);
    } else {
      setError(result.error);
    }
    setLoaded(true);
  }, []);

  useFocusEffect(
    useCallback(() => {
      loadFirstPage();
    }, [loadFirstPage])
  );

  async function handleRefresh() {
    setRefreshing(true);
    await loadFirstPage();
    setRefreshing(false);
  }

  async function handleEndReached() {
    if (!cursor || loadingMore) return;
    setLoadingMore(true);
    const result = await listItems(PAGE_SIZE, cursor);
    if (result.ok) {
      setItems((prev) => [...prev, ...result.items]);
      setCursor(result.cursor);
    }
    setLoadingMore(false);
  }

  return (
    <ThemedView style={styles.container}>
      <SafeAreaView style={styles.safeArea} edges={['bottom']}>
        {error && (
          <ThemedText type="small" style={styles.error}>
            {error}
          </ThemedText>
        )}
        <SectionList
          sections={groupByDate(items)}
          keyExtractor={(item) => item.note_id}
          renderItem={({ item }) => <ItemRow item={item} />}
          renderSectionHeader={({ section }) => (
            <ThemedText type="smallBold" style={styles.sectionHeader}>
              {section.title}
            </ThemedText>
          )}
          ItemSeparatorComponent={() => <ThemedView style={{ height: Spacing.two }} />}
          stickySectionHeadersEnabled={false}
          contentContainerStyle={styles.list}
          refreshControl={<RefreshControl refreshing={refreshing} onRefresh={handleRefresh} />}
          onEndReached={handleEndReached}
          onEndReachedThreshold={0.4}
          ListFooterComponent={loadingMore ? <ActivityIndicator style={styles.footer} /> : null}
          ListEmptyComponent={
            loaded && !error ? <ThemedText type="small">Nothing here yet.</ThemedText> : null
          }
        />
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
    paddingHorizontal: Spacing.four,
  },
  list: {
    paddingVertical: Spacing.three,
  },
  sectionHeader: {
    marginTop: Spacing.three,
    marginBottom: Spacing.two,
  },
  row: {
    padding: Spacing.three,
    borderRadius: Spacing.two,
    gap: Spacing.one,
  },
  error: {
    marginTop: Spacing.three,
    opacity: 0.7,
  },
  footer: {
    marginVertical: Spacing.three,
  },
});
