import { router, useFocusEffect } from 'expo-router';
import { useCallback, useState, useSyncExternalStore } from 'react';
import { ActivityIndicator, Pressable, RefreshControl, ScrollView, StyleSheet } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import PendingRow from '@/components/pending-row';
import { ThemedText } from '@/components/themed-text';
import { ThemedView } from '@/components/themed-view';
import { BottomTabInset, Spacing } from '@/constants/theme';
import { getReviewQueue, listSources, type ReviewQueueItem, type Source } from '@/lib/api';
import { getPendingIngestionsSnapshot, subscribePendingIngestions } from '@/lib/pendingIngestions';
import { setActiveReviewStack } from '@/lib/reviewStack';

// Same "worth a second look" cutoff the web app's graph view uses (dashed
// edges) and the flip-through view's swipe hint reasons about — kept in
// sync by eye across the three, since each file already owns its own
// rendering constant rather than importing a cross-platform one.
const REVIEW_CONFIDENCE_CUTOFF = 0.85;

type Stack = { key: string; title: string; items: ReviewQueueItem[] };

const URL_PATTERN = /^https?:\/\//i;

// A source's title is sometimes just its raw URL — fetch_url couldn't find a
// real <title> on the page, so _resolve_source fell back to the URL itself
// (app/MyAgent/tools/notes.py). A full URL is unreadable as a stack label;
// showing just the host is a lot more scannable, and if that still doesn't
// give enough to recognize the batch by, the group's own items already have
// real, agent-written titles worth falling back to instead.
function displayTitle(rawTitle: string, groupItems: ReviewQueueItem[]): string {
  if (!URL_PATTERN.test(rawTitle)) return rawTitle;
  if (groupItems[0]?.title) return groupItems[0].title;
  try {
    return new URL(rawTitle).hostname.replace(/^www\./, '');
  } catch {
    return rawTitle;
  }
}

// Newest item in a stack, for sorting stacks themselves — matches the
// Slip Box tab's Recent box convention (newest first) rather than item
// count, so a single fresh note doesn't get buried under an old, larger
// backlog batch just because it has fewer items.
function newestCreatedAt(items: ReviewQueueItem[]): string {
  return items.reduce((max, i) => (i.created_at && i.created_at > max ? i.created_at : max), '');
}

// Grouped by source rather than shown flat — "the old system kept different
// kinds of cards in different boxes rather than labeling each card," and
// the natural review unit is really "everything that came in from this one
// thing I just added," not one card at a time. Items with no source_id
// (rare — e.g. plain pasted text with nothing to cite) fall into one shared
// group rather than each becoming their own singleton stack.
function groupBySource(items: ReviewQueueItem[], sourceTitles: Map<string, string>): Stack[] {
  const groups = new Map<string, ReviewQueueItem[]>();
  for (const item of items) {
    const key = item.source_id ?? '__no_source__';
    (groups.get(key) ?? groups.set(key, []).get(key)!).push(item);
  }
  return Array.from(groups.entries())
    .map(([key, groupItems]) => {
      const rawTitle = key === '__no_source__' ? 'No source' : (sourceTitles.get(key) ?? 'Unknown source');
      return { key, title: displayTitle(rawTitle, groupItems), items: groupItems };
    })
    .sort((a, b) => newestCreatedAt(b.items).localeCompare(newestCreatedAt(a.items)));
}

function StackCard({ stack, onPress }: { stack: Stack; onPress: () => void }) {
  const totalEdges = stack.items.reduce((sum, i) => sum + i.outgoing_edges.length + i.incoming_edges.length, 0);
  const orphanCount = stack.items.filter((i) => i.outgoing_edges.length + i.incoming_edges.length === 0).length;
  const lowConfidenceCount = stack.items.filter((i) =>
    [...i.outgoing_edges, ...i.incoming_edges].some((e) => e.confidence < REVIEW_CONFIDENCE_CUTOFF)
  ).length;

  return (
    <Pressable onPress={onPress}>
      <ThemedView type="backgroundElement" style={styles.card}>
        <ThemedView style={styles.cardMain}>
          <ThemedText numberOfLines={2}>{stack.title}</ThemedText>
          <ThemedView style={styles.badgeRow}>
            <ThemedText type="small" themeColor="textSecondary">
              {stack.items.length} {stack.items.length === 1 ? 'item' : 'items'}
            </ThemedText>
            {orphanCount > 0 && (
              <ThemedText type="small" themeColor="textSecondary">
                {orphanCount} with no connections
              </ThemedText>
            )}
            {lowConfidenceCount > 0 && (
              <ThemedText type="small" style={styles.lowConfidenceFlag}>
                {lowConfidenceCount} low-confidence
              </ThemedText>
            )}
            {totalEdges === 0 && stack.items.length > 1 && (
              <ThemedText type="small" style={styles.lowConfidenceFlag}>
                no connections between them either
              </ThemedText>
            )}
          </ThemedView>
        </ThemedView>
        <ThemedText type="small" themeColor="textSecondary">
          ›
        </ThemedText>
      </ThemedView>
    </Pressable>
  );
}

export default function ReviewScreen() {
  const [stacks, setStacks] = useState<Stack[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  // Same generic tracker the Slip Box tab reads — without this, a note or
  // summary card still mid-ingestion looks like a silent gap here instead
  // of something on its way, right when "is it actually caught up?" matters
  // most.
  const pendingIngestions = useSyncExternalStore(subscribePendingIngestions, getPendingIngestionsSnapshot);

  const load = useCallback(async () => {
    const [queueResult, sourcesResult] = await Promise.all([getReviewQueue(), listSources()]);
    if (!queueResult.ok) {
      setError(queueResult.error);
      return;
    }
    const sourceTitles = new Map<string, string>(
      sourcesResult.ok ? (sourcesResult.sources as Source[]).map((s) => [s.source_id, s.title]) : []
    );
    setStacks(groupBySource(queueResult.items, sourceTitles));
    setError(null);
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

  function openStack(stack: Stack) {
    setActiveReviewStack(stack.title, stack.items);
    router.push('/review-stack');
  }

  return (
    <ThemedView style={styles.container}>
      <SafeAreaView style={styles.safeArea} edges={['bottom']}>
        <ScrollView
          contentContainerStyle={styles.scroll}
          refreshControl={<RefreshControl refreshing={refreshing} onRefresh={handleRefresh} />}
        >
          {pendingIngestions.length > 0 && (
            <ThemedView style={styles.pendingList}>
              {pendingIngestions.map((p) => (
                <PendingRow key={p.sessionId} label={p.label} />
              ))}
            </ThemedView>
          )}
          {error && (
            <ThemedText type="small" style={styles.error}>
              {error}
            </ThemedText>
          )}
          {!stacks && !error && (
            <ThemedView style={styles.center}>
              <ActivityIndicator />
            </ThemedView>
          )}
          {stacks && stacks.length === 0 && pendingIngestions.length === 0 && (
            <ThemedView style={styles.emptyState}>
              <ThemedText type="subtitle">Nothing to review</ThemedText>
              <ThemedText style={styles.emptyBody} themeColor="textSecondary">
                You're caught up.
              </ThemedText>
            </ThemedView>
          )}
          {stacks?.map((stack) => <StackCard key={stack.key} stack={stack} onPress={() => openStack(stack)} />)}
        </ScrollView>
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
  scroll: {
    paddingTop: Spacing.three,
    // Same fix as (tabs)/index.tsx: the tab bar floats over content instead
    // of reserving its own space, so the last card needs room above it or
    // it reads as clipped rather than trailing off naturally.
    paddingBottom: Spacing.three + BottomTabInset,
    gap: Spacing.two,
  },
  pendingList: {
    gap: Spacing.two,
  },
  card: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: Spacing.two,
    borderRadius: Spacing.two,
    padding: Spacing.three,
  },
  cardMain: {
    flex: 1,
    gap: Spacing.one,
  },
  badgeRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.two,
    flexWrap: 'wrap',
  },
  lowConfidenceFlag: {
    color: '#d97706',
  },
  error: {
    marginTop: Spacing.three,
    opacity: 0.7,
  },
  center: {
    marginTop: Spacing.six,
    alignItems: 'center',
  },
  emptyState: {
    marginTop: Spacing.six,
    gap: Spacing.two,
    alignItems: 'center',
  },
  emptyBody: {
    textAlign: 'center',
  },
});
