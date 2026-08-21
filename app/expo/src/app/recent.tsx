import { useFocusEffect } from 'expo-router';
import { useCallback, useState } from 'react';
import { FlatList, RefreshControl, StyleSheet } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { ThemedText } from '@/components/themed-text';
import { ThemedView } from '@/components/themed-view';
import { Spacing } from '@/constants/theme';
import { listItems, type Item } from '@/lib/api';

const TYPE_LABEL: Record<Item['type'], string> = {
  'literature-note': 'note',
  'summary-card': 'summary',
  'permanent-note': 'idea',
};

function formatDate(iso?: string) {
  if (!iso) return '';
  const d = new Date(iso);
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
}

function ItemRow({ item }: { item: Item }) {
  return (
    <ThemedView type="backgroundElement" style={styles.row}>
      <ThemedText numberOfLines={2}>{item.title}</ThemedText>
      <ThemedView style={styles.meta}>
        <ThemedText type="small" themeColor="textSecondary">
          {TYPE_LABEL[item.type] ?? item.type}
        </ThemedText>
        <ThemedText type="small" themeColor="textSecondary">
          {formatDate(item.created_at ?? item.date)}
        </ThemedText>
      </ThemedView>
    </ThemedView>
  );
}

export default function RecentScreen() {
  const [items, setItems] = useState<Item[]>([]);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);

  const load = useCallback(async () => {
    const result = await listItems(30);
    if (result.ok) {
      setItems(result.items);
      setError(null);
    } else {
      setError(result.error);
    }
    setLoaded(true);
  }, []);

  useFocusEffect(
    useCallback(() => {
      load();
    }, [load])
  );

  async function handleRefresh() {
    setRefreshing(true);
    await load();
    setRefreshing(false);
  }

  return (
    <ThemedView style={styles.container}>
      <SafeAreaView style={styles.safeArea} edges={['bottom']}>
        {error && (
          <ThemedText type="small" style={styles.error}>
            {error}
          </ThemedText>
        )}
        <FlatList
          data={items}
          keyExtractor={(item) => item.note_id}
          renderItem={({ item }) => <ItemRow item={item} />}
          ItemSeparatorComponent={() => <ThemedView style={{ height: Spacing.two }} />}
          contentContainerStyle={styles.list}
          refreshControl={<RefreshControl refreshing={refreshing} onRefresh={handleRefresh} />}
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
  row: {
    padding: Spacing.three,
    borderRadius: Spacing.two,
    gap: Spacing.one,
  },
  meta: {
    flexDirection: 'row',
    gap: Spacing.three,
  },
  error: {
    marginTop: Spacing.three,
    opacity: 0.7,
  },
});
