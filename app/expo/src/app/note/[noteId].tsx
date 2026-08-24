import { router, Stack, useFocusEffect, useLocalSearchParams } from 'expo-router';
import { SymbolView } from 'expo-symbols';
import { useCallback, useEffect, useState } from 'react';
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, View } from 'react-native';
import { Gesture, GestureDetector } from 'react-native-gesture-handler';
import { SafeAreaView } from 'react-native-safe-area-context';

import NoteDetailContent, { EDGE_TYPE_LABEL } from '@/components/note-detail-content';
import { ThemedText } from '@/components/themed-text';
import { ThemedView } from '@/components/themed-view';
import { Spacing } from '@/constants/theme';
import { useTheme } from '@/hooks/use-theme';
import { getItem, removeIndexKeyword, type EdgeType, type ItemDetail } from '@/lib/api';
import { EDGE_COLORS } from '@/lib/typeColors';

// Deliberately not a hard physical-distance minimum — this is a small
// screen, a confident flick shouldn't need to travel far. Loose enough to
// fire on an intentional swipe, tight enough not to fire on a scroll tap.
const SWIPE_THRESHOLD = 60;

type Connection = {
  id: string;
  title: string;
  type: EdgeType;
  confidence: number;
  direction: '→' | '←';
  // Non-empty when this neighbor is itself a curated index entry — the
  // "sub index card" signal (docs/frontend-ux-spec.md's Index Cards
  // section), discovered by walking edges rather than a separate screen.
  indexKeywords: string[];
};

function orderedConnections(item: ItemDetail): Connection[] {
  const outgoing = item.outgoing_edges.map((e) => ({
    id: e.to_id, title: e.to_title, type: e.type, confidence: e.confidence, direction: '→' as const,
    indexKeywords: e.to_index_keywords,
  }));
  const incoming = item.incoming_edges.map((e) => ({
    id: e.from_id, title: e.from_title, type: e.type, confidence: e.confidence, direction: '←' as const,
    indexKeywords: e.from_index_keywords,
  }));
  // Strongest first, then alphabetical — a stable, predictable order to page
  // through rather than jumping straight to "the one best match" and
  // discarding the rest (the earlier design; too much like teleporting to
  // actually browse the graph with).
  return [...outgoing, ...incoming].sort(
    (a, b) => b.confidence - a.confidence || a.title.localeCompare(b.title)
  );
}

// "Central item out, not outer in": this screen only ever renders the
// current noteId's own detail plus its own edges — there's no code path
// that shows a peripheral note without it becoming the new center.
// Swiping pages through *this* note's own connections one at a time, in a
// stable reading order — it doesn't jump anywhere by itself. Tapping the
// currently-paged-to connection is what actually navigates and recenters.
export default function NoteDetailScreen() {
  const theme = useTheme();
  const { noteId } = useLocalSearchParams<{ noteId: string }>();
  const [item, setItem] = useState<ItemDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [focusIndex, setFocusIndex] = useState(0);

  useEffect(() => {
    setItem(null);
    setError(null);
    setFocusIndex(0);
    if (!noteId) return;
    getItem(noteId).then((result) => {
      if (result.ok) setItem(result.item);
      else setError(result.error);
    });
  }, [noteId]);

  // Silent refresh on refocus (not a reset — focusIndex/loading state are
  // untouched) — picks up an index keyword added via the index-keyword
  // modal without the paging position jumping back to 0.
  useFocusEffect(
    useCallback(() => {
      if (!noteId) return;
      getItem(noteId).then((result) => {
        if (result.ok) setItem(result.item);
      });
    }, [noteId])
  );

  async function handleRemoveKeyword(keyword: string) {
    if (!item) return;
    const result = await removeIndexKeyword(item.note_id, keyword);
    if (result.ok) {
      setItem((prev) => (prev ? { ...prev, index_keywords: result.indexKeywords } : prev));
    }
  }

  const connections = item ? orderedConnections(item) : [];
  const focused = connections[focusIndex];

  // Reading-direction convention: swipe left moves forward (like turning a
  // page), swipe right moves back — the reverse of what this screen shipped
  // with first, which jumped straight to a single "best" neighbor instead of
  // letting you page through all of them.
  const swipeGesture = Gesture.Pan()
    .runOnJS(true)
    // Constrain to horizontal-dominant motion so this coexists with the
    // ScrollView below it — without this, a normal vertical scroll to read
    // the note body would fight the pan recognizer for the gesture arena.
    .activeOffsetX([-20, 20])
    .failOffsetY([-20, 20])
    .onEnd((event) => {
      if (event.translationX < -SWIPE_THRESHOLD) {
        setFocusIndex((i) => Math.min(i + 1, Math.max(connections.length - 1, 0)));
      } else if (event.translationX > SWIPE_THRESHOLD) {
        if (focusIndex === 0) {
          if (router.canGoBack()) router.back();
        } else {
          setFocusIndex((i) => Math.max(i - 1, 0));
        }
      }
    });

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

  return (
    <ThemedView style={styles.container}>
      {/* This screen's own static title ("Note") isn't enough to tell which
          note you're on when several are stacked from paging through
          connections — set it to the real title once it's loaded. */}
      <Stack.Screen
        options={{
          title: item.title,
          headerRight: () => (
            <Pressable
              onPress={() => router.push({ pathname: '/index-keyword', params: { noteId: item.note_id } })}
              hitSlop={12}
              style={{ marginRight: 4 }}
            >
              <SymbolView name="tag" size={20} tintColor={theme.text} />
            </Pressable>
          ),
        }}
      />
      <GestureDetector gesture={swipeGesture}>
        <SafeAreaView style={styles.safeArea} edges={['bottom']}>
          <ScrollView contentContainerStyle={styles.scroll}>
            <NoteDetailContent item={item} hideConnections />

            {item.index_keywords && item.index_keywords.length > 0 && (
              <View style={styles.indexKeywords}>
                {item.index_keywords.map((keyword) => (
                  <Pressable key={keyword} onPress={() => handleRemoveKeyword(keyword)}>
                    <ThemedView type="backgroundSelected" style={styles.indexPill}>
                      <ThemedText type="small">{keyword} ×</ThemedText>
                    </ThemedView>
                  </Pressable>
                ))}
              </View>
            )}

            {connections.length > 0 && (
              <ThemedView style={styles.connections}>
                <ThemedView style={styles.connectionsHeader}>
                  <ThemedText type="smallBold">Connections</ThemedText>
                  <ThemedText type="small" themeColor="textSecondary">
                    {focusIndex + 1} of {connections.length}
                  </ThemedText>
                </ThemedView>
                <ThemedText type="small" themeColor="textSecondary" style={styles.swipeHint}>
                  Swipe left to page through · swipe right to go back · tap to open
                </ThemedText>

                {focused && (
                  <Pressable onPress={() => router.push(`/note/${encodeURIComponent(focused.id)}`)}>
                    <ThemedView type="backgroundElement" style={styles.focusCard}>
                      <View style={styles.focusMeta}>
                        <View style={[styles.connectionDot, { backgroundColor: EDGE_COLORS[focused.type] }]} />
                        <ThemedText type="small" themeColor="textSecondary">
                          {focused.direction} {EDGE_TYPE_LABEL[focused.type]}
                        </ThemedText>
                      </View>
                      <ThemedText numberOfLines={2}>{focused.title}</ThemedText>
                      <ThemedText type="small" themeColor="textSecondary">
                        confidence {focused.confidence.toFixed(2)}
                      </ThemedText>
                      {focused.indexKeywords.length > 0 && (
                        <ThemedText type="small" themeColor="textSecondary">
                          ↳ index: {focused.indexKeywords.join(', ')}
                        </ThemedText>
                      )}
                    </ThemedView>
                  </Pressable>
                )}
              </ThemedView>
            )}
          </ScrollView>
        </SafeAreaView>
      </GestureDetector>
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
  indexKeywords: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: Spacing.one,
  },
  indexPill: {
    paddingVertical: Spacing.half,
    paddingHorizontal: Spacing.two,
    borderRadius: Spacing.two,
  },
  connections: {
    gap: Spacing.one,
    marginTop: Spacing.two,
  },
  connectionsHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  swipeHint: {
    opacity: 0.7,
    marginBottom: Spacing.one,
  },
  focusCard: {
    padding: Spacing.three,
    borderRadius: Spacing.two,
    gap: Spacing.one,
  },
  focusMeta: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.two,
  },
  connectionDot: {
    width: 7,
    height: 7,
    borderRadius: 4,
  },
});
