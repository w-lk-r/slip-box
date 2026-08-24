import { Link, useFocusEffect } from 'expo-router';
import { SymbolView } from 'expo-symbols';
import { useCallback, useState, useSyncExternalStore } from 'react';
import { ActivityIndicator, FlatList, Pressable, RefreshControl, SectionList, StyleSheet } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import IndexCardRow from '@/components/index-card-row';
import PendingRow from '@/components/pending-row';
import { ThemedText } from '@/components/themed-text';
import { ThemedView } from '@/components/themed-view';
import { BottomTabInset, Spacing } from '@/constants/theme';
import { useTheme } from '@/hooks/use-theme';
import { getIndex, listItems, summarize, type IndexEntry, type Item, type ItemType } from '@/lib/api';
import {
  addPendingIngestion,
  clearPendingBefore,
  getPendingIngestionsSnapshot,
  subscribePendingIngestions,
} from '@/lib/pendingIngestions';

const PAGE_SIZE = 20;

type Box = ItemType | undefined | 'index';

// Luhmann's own system kept literature notes and the permanent slip-box in
// physically separate boxes — you picked which one you were working in, a
// card never had to announce its own kind. Same idea here: a box switcher
// instead of a type label repeated on every row. permanent-note has no
// write path yet (see CLAUDE.md), so it's left out until there's ever
// anything in it to switch to.
//
// "Index" is the default/landing box now (docs/frontend-ux-spec.md's own
// design note anticipated this once Index Cards existed) — a curated,
// alphabetical "how do I get in today," not a chronological feed. "Recent"
// (the old flat "All") still covers a genuinely different need: what's
// freshly written and not yet filed — still on the desk, not back in the
// slip case — so it keeps its own separate box rather than being folded in.
//
// No "Notes" box: it would just be Recent filtered to literature-note,
// still sorted by the same date — a second date-ordered list with no
// distinguishing organizing principle of its own isn't worth the tab.
// "Summaries" earns its own box because it's a meaningfully different,
// much smaller set, not because of how it's sorted.
const BOXES: { value: Box; label: string }[] = [
  { value: 'index', label: 'Index' },
  { value: undefined, label: 'Recent' },
  { value: 'summary-card', label: 'Summaries' },
];

function BoxSwitcher({ value, onChange }: { value: Box; onChange: (v: Box) => void }) {
  return (
    <ThemedView style={styles.boxRow}>
      {BOXES.map((box) => {
        const selected = box.value === value;
        return (
          <Pressable key={box.label} onPress={() => onChange(box.value)} style={styles.boxChipWrap}>
            <ThemedView type={selected ? 'backgroundSelected' : 'backgroundElement'} style={styles.boxChip}>
              <ThemedText type="small" themeColor={selected ? 'text' : 'textSecondary'}>
                {box.label}
              </ThemedText>
            </ThemedView>
          </Pressable>
        );
      })}
    </ThemedView>
  );
}

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

// The backend now queries a GSI sorted by created_at, so pages already
// arrive newest-first — this re-sort is just a cheap safety net, not load-
// bearing, in case that ever changes.
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

function ItemRow({
  item,
  selectionMode,
  selected,
  onToggleSelect,
  onLongPress,
}: {
  item: Item;
  selectionMode: boolean;
  selected: boolean;
  onToggleSelect: () => void;
  onLongPress: () => void;
}) {
  const theme = useTheme();
  const content = (
    <ThemedView type={selected ? 'backgroundSelected' : 'backgroundElement'} style={styles.row}>
      {selectionMode && (
        <SymbolView
          name={selected ? 'checkmark.circle.fill' : 'circle'}
          size={20}
          tintColor={selected ? theme.text : theme.textSecondary}
        />
      )}
      <ThemedText numberOfLines={2} style={styles.rowMain}>
        {item.title}
      </ThemedText>
      {!selectionMode && (
        <ThemedText type="small" themeColor="textSecondary">
          ›
        </ThemedText>
      )}
    </ThemedView>
  );

  // Long-press to enter selection mode (docs/frontend-ux-spec.md's
  // selection-first synthesis flow) — while active, tapping any row toggles
  // it instead of navigating, matching the standard Photos-app pattern
  // rather than a persistent "Select" button.
  if (selectionMode) {
    return (
      <Pressable onPress={onToggleSelect} onLongPress={onLongPress}>
        {content}
      </Pressable>
    );
  }
  return (
    <Link href={`/note/${item.note_id}`} asChild>
      <Pressable onLongPress={onLongPress}>{content}</Pressable>
    </Link>
  );
}

function EmptyState({ box }: { box: Box }) {
  if (box === 'index') {
    return (
      <ThemedView style={styles.emptyState}>
        <ThemedText type="subtitle">No index cards yet</ThemedText>
        <ThemedText style={styles.emptyBody}>
          Open a note from Recent and add it as an entry point for a keyword — a sparse, curated way back in, not an
          exhaustive list.
        </ThemedText>
      </ThemedView>
    );
  }
  const boxLabel = BOXES.find((b) => b.value === box)?.label ?? 'Recent';
  return (
    <ThemedView style={styles.emptyState}>
      <ThemedText type="subtitle">{box ? `No ${boxLabel.toLowerCase()} yet` : 'Nothing here yet'}</ThemedText>
      <ThemedText style={styles.emptyBody}>
        {box
          ? 'Nothing in this box yet — switch to Recent to see everything.'
          : "Share a link or a passage of text to this app from anywhere — Safari, YouTube, Notes — and it gets sent to your slip case for ingestion. Or use the Submit tab to paste something directly."}
      </ThemedText>
    </ThemedView>
  );
}

export default function NotesScreen() {
  const [box, setBox] = useState<Box>('index');
  const [items, setItems] = useState<Item[]>([]);
  const [cursor, setCursor] = useState<string | undefined>();
  const [indexEntries, setIndexEntries] = useState<IndexEntry[]>([]);
  const [refreshing, setRefreshing] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const selectionMode = selectedIds.size > 0;
  const pendingIngestions = useSyncExternalStore(subscribePendingIngestions, getPendingIngestionsSnapshot);

  const loadFirstPage = useCallback(async (activeBox: Box) => {
    if (activeBox === 'index') {
      const result = await getIndex();
      if (result.ok) {
        setIndexEntries(result.entries);
        setError(null);
      } else {
        setError(result.error);
      }
      setLoaded(true);
      return;
    }
    const result = await listItems(PAGE_SIZE, undefined, activeBox);
    if (result.ok) {
      setItems(result.items);
      setCursor(result.cursor);
      setError(null);
      // Pages aren't in date order (see groupByDate's own comment) — scan
      // the whole page rather than assume result.items[0] is the newest.
      const newest = result.items.reduce<string | undefined>(
        (max, i) => (i.created_at && (!max || i.created_at > max) ? i.created_at : max),
        undefined
      );
      clearPendingBefore(newest);
    } else {
      setError(result.error);
    }
    setLoaded(true);
  }, []);

  useFocusEffect(
    useCallback(() => {
      loadFirstPage(box);
    }, [loadFirstPage, box])
  );

  function handleBoxChange(next: Box) {
    setBox(next);
    setLoaded(false);
    setSelectedIds(new Set());
    loadFirstPage(next);
  }

  function handleLongPress(noteId: string) {
    setSelectedIds((prev) => new Set(prev).add(noteId));
  }

  function handleToggleSelect(noteId: string) {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(noteId)) next.delete(noteId);
      else next.add(noteId);
      return next;
    });
  }

  async function handleSummarize() {
    const noteIds = Array.from(selectedIds);
    setSelectedIds(new Set());
    const result = await summarize(noteIds);
    if (result.ok) {
      addPendingIngestion(result.sessionId, `Summarizing ${noteIds.length} notes…`);
    } else {
      setError(result.error);
    }
  }

  async function handleRefresh() {
    setRefreshing(true);
    await loadFirstPage(box);
    setRefreshing(false);
  }

  async function handleEndReached() {
    if (box === 'index' || !cursor || loadingMore) return;
    setLoadingMore(true);
    const result = await listItems(PAGE_SIZE, cursor, box);
    if (result.ok) {
      setItems((prev) => [...prev, ...result.items]);
      setCursor(result.cursor);
    }
    setLoadingMore(false);
  }

  return (
    <ThemedView style={styles.container}>
      <SafeAreaView style={styles.safeArea} edges={['bottom']}>
        <BoxSwitcher value={box} onChange={handleBoxChange} />
        {error && (
          <ThemedText type="small" style={styles.error}>
            {error}
          </ThemedText>
        )}
        {box === 'index' ? (
          <FlatList
            style={styles.list}
            data={indexEntries}
            keyExtractor={(entry) => entry.keyword}
            renderItem={({ item }) => <IndexCardRow entry={item} />}
            ItemSeparatorComponent={() => <ThemedView style={{ height: Spacing.two }} />}
            contentContainerStyle={styles.listContent}
            refreshControl={<RefreshControl refreshing={refreshing} onRefresh={handleRefresh} />}
            ListEmptyComponent={loaded && !error ? <EmptyState box={box} /> : null}
          />
        ) : (
          <SectionList
            style={styles.list}
            sections={groupByDate(items)}
            keyExtractor={(item) => item.note_id}
            renderItem={({ item }) => (
              <ItemRow
                item={item}
                selectionMode={selectionMode}
                selected={selectedIds.has(item.note_id)}
                onToggleSelect={() => handleToggleSelect(item.note_id)}
                onLongPress={() => handleLongPress(item.note_id)}
              />
            )}
            renderSectionHeader={({ section }) => (
              <ThemedText type="smallBold" style={styles.sectionHeader}>
                {section.title}
              </ThemedText>
            )}
            ItemSeparatorComponent={() => <ThemedView style={{ height: Spacing.two }} />}
            stickySectionHeadersEnabled={false}
            contentContainerStyle={styles.listContent}
            refreshControl={<RefreshControl refreshing={refreshing} onRefresh={handleRefresh} />}
            onEndReached={handleEndReached}
            onEndReachedThreshold={0.4}
            ListFooterComponent={loadingMore ? <ActivityIndicator style={styles.footer} /> : null}
            ListHeaderComponent={
              pendingIngestions.length > 0 ? (
                <ThemedView style={styles.pendingList}>
                  {pendingIngestions.map((p) => (
                    <PendingRow key={p.sessionId} label={p.label} />
                  ))}
                </ThemedView>
              ) : null
            }
            ListEmptyComponent={loaded && !error ? <EmptyState box={box} /> : null}
          />
        )}

        {selectionMode && (
          <ThemedView style={styles.actionBar}>
            <Pressable onPress={() => setSelectedIds(new Set())}>
              <ThemedText type="link">Cancel</ThemedText>
            </Pressable>
            <Pressable onPress={selectedIds.size >= 2 ? handleSummarize : undefined}>
              <ThemedText type="link" themeColor={selectedIds.size >= 2 ? undefined : 'textSecondary'}>
                Summarize ({selectedIds.size})
              </ThemedText>
            </Pressable>
          </ThemedView>
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
    paddingHorizontal: Spacing.four,
  },
  boxRow: {
    flexDirection: 'row',
    gap: Spacing.two,
    marginTop: Spacing.three,
  },
  boxChipWrap: {
    flex: 1,
  },
  boxChip: {
    paddingVertical: Spacing.two,
    borderRadius: Spacing.two,
    alignItems: 'center',
  },
  list: {
    flex: 1,
  },
  listContent: {
    paddingTop: Spacing.three,
    // The tab bar floats over content rather than reserving its own space
    // (confirmed: BottomTabInset was defined in theme.ts for exactly this
    // but never actually wired up anywhere) — without this, the last row
    // renders flush against the flex boundary and reads as clipped/cut off
    // rather than trailing off with room to breathe above the tab bar.
    paddingBottom: Spacing.three + BottomTabInset,
  },
  actionBar: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingVertical: Spacing.three,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: '#8888',
  },
  sectionHeader: {
    marginTop: Spacing.three,
    marginBottom: Spacing.two,
  },
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
    gap: Spacing.one,
  },
  pendingList: {
    gap: Spacing.two,
    marginBottom: Spacing.three,
  },
  error: {
    marginTop: Spacing.three,
    opacity: 0.7,
  },
  footer: {
    marginVertical: Spacing.three,
  },
  emptyState: {
    marginTop: Spacing.six,
    gap: Spacing.two,
    alignItems: 'center',
    paddingHorizontal: Spacing.three,
  },
  emptyBody: {
    textAlign: 'center',
    opacity: 0.8,
  },
});
