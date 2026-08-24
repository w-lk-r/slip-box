import { router } from 'expo-router';
import { SymbolView } from 'expo-symbols';
import { useEffect, useState } from 'react';
import { ActivityIndicator, Alert, Pressable, ScrollView, StyleSheet } from 'react-native';
import { Gesture, GestureDetector } from 'react-native-gesture-handler';
import { SafeAreaView } from 'react-native-safe-area-context';

import NoteDetailContent from '@/components/note-detail-content';
import { ThemedText } from '@/components/themed-text';
import { ThemedView } from '@/components/themed-view';
import { Spacing } from '@/constants/theme';
import { useTheme } from '@/hooks/use-theme';
import { deleteItem, getItem, markReviewed, type ItemDetail, type ReviewQueueItem } from '@/lib/api';
import { getActiveReviewStack } from '@/lib/reviewStack';

const SWIPE_THRESHOLD = 60;

// Same swipe gesture shape note/[noteId].tsx uses, but a swipe here just
// moves through this fixed, already-known list of note_ids — no edge
// following, no re-fetch of "what's next", so no per-swipe network call
// beyond loading the newly-current item's own full detail.
export default function ReviewStackScreen() {
  const theme = useTheme();
  const [stack, setStack] = useState<{ title: string; items: ReviewQueueItem[] } | null | undefined>(undefined);
  const [index, setIndex] = useState(0);
  const [detail, setDetail] = useState<ItemDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [marking, setMarking] = useState(false);

  useEffect(() => {
    setStack(getActiveReviewStack());
  }, []);

  const current = stack?.items[index];

  useEffect(() => {
    setDetail(null);
    setError(null);
    if (!current) return;
    getItem(current.note_id).then((result) => {
      if (result.ok) setDetail(result.item);
      else setError(result.error);
    });
  }, [current]);

  function goNext() {
    setIndex((i) => Math.min(i + 1, (stack?.items.length ?? 1) - 1));
  }

  function goPrevious() {
    setIndex((i) => Math.max(i - 1, 0));
  }

  async function handleMarkReviewed() {
    if (!current) return;
    setMarking(true);
    const result = await markReviewed(current.note_id);
    setMarking(false);
    if (!result.ok) return;
    const removedId = current.note_id;
    setStack((prev) => {
      if (!prev) return prev;
      const items = prev.items.filter((i) => i.note_id !== removedId);
      // Removing the current item shifts everything after it back by one —
      // staying at the same index shows what was previously "next", except
      // at the end of the list, where it must clamp to the new last index.
      setIndex((i) => Math.min(i, Math.max(items.length - 1, 0)));
      return { ...prev, items };
    });
  }

  function handleTag() {
    if (!current) return;
    router.push({ pathname: '/index-keyword', params: { noteId: current.note_id } });
  }

  async function confirmDelete(target: ReviewQueueItem) {
    const result = await deleteItem(target.note_id);
    if (!result.ok) return;
    // Optimistic, same as handleMarkReviewed — the actual DynamoDB cleanup
    // is asynchronous via the reconciler (see DELETE /items/{note_id}'s own
    // comment), nothing to poll for here.
    setStack((prev) => {
      if (!prev) return prev;
      const items = prev.items.filter((i) => i.note_id !== target.note_id);
      setIndex((i) => Math.min(i, Math.max(items.length - 1, 0)));
      return { ...prev, items };
    });
  }

  function handleDelete() {
    if (!current) return;
    // Capture now, not inside the Alert callback — by the time the user
    // taps through the native dialog, `current` could have already moved
    // on if state re-rendered in between.
    const target = current;
    Alert.alert('Delete this note?', 'This removes it and its connections permanently.', [
      { text: 'Cancel', style: 'cancel' },
      { text: 'Delete', style: 'destructive', onPress: () => confirmDelete(target) },
    ]);
  }

  const swipeGesture = Gesture.Pan()
    .runOnJS(true)
    .activeOffsetX([-20, 20])
    .failOffsetY([-20, 20])
    .onEnd((event) => {
      if (event.translationX < -SWIPE_THRESHOLD) goNext();
      else if (event.translationX > SWIPE_THRESHOLD) goPrevious();
    });

  if (stack === undefined) {
    return (
      <ThemedView style={[styles.container, styles.center]}>
        <ActivityIndicator />
      </ThemedView>
    );
  }

  if (!stack || stack.items.length === 0) {
    return (
      <ThemedView style={styles.container}>
        <SafeAreaView style={styles.safeArea}>
          <ThemedText type="subtitle">All caught up</ThemedText>
          <ThemedText type="small" themeColor="textSecondary" style={styles.doneBody}>
            Nothing left in this stack to review.
          </ThemedText>
          <Pressable onPress={() => router.back()} style={styles.doneButton}>
            <ThemedText type="link">Back to Review</ThemedText>
          </Pressable>
        </SafeAreaView>
      </ThemedView>
    );
  }

  return (
    <ThemedView style={styles.container}>
      <GestureDetector gesture={swipeGesture}>
        <SafeAreaView style={styles.safeArea} edges={['bottom']}>
          <ThemedView style={styles.header}>
            <ThemedText type="small" themeColor="textSecondary" numberOfLines={1} style={styles.headerTitle}>
              {stack.title}
            </ThemedText>
            <ThemedText type="small" themeColor="textSecondary">
              {index + 1} of {stack.items.length}
            </ThemedText>
          </ThemedView>

          {error && <ThemedText type="small">{error}</ThemedText>}
          {!error && !detail && (
            <ThemedView style={styles.center}>
              <ActivityIndicator />
            </ThemedView>
          )}
          {detail && (
            <ScrollView contentContainerStyle={styles.scroll}>
              <NoteDetailContent item={detail} swipeHint="Swipe to move through the stack — nothing here marks it reviewed" />
            </ScrollView>
          )}

          <ThemedView style={styles.actionRow}>
            <Pressable onPress={handleDelete} disabled={!detail} style={styles.actionButton}>
              <SymbolView name="trash" size={22} tintColor={theme.textSecondary} />
              <ThemedText type="small" themeColor="textSecondary">
                Delete
              </ThemedText>
            </Pressable>
            <Pressable onPress={handleTag} disabled={!detail} style={styles.actionButton}>
              <SymbolView name="tag" size={22} tintColor={theme.textSecondary} />
              <ThemedText type="small" themeColor="textSecondary">
                Tag
              </ThemedText>
            </Pressable>
            <Pressable onPress={handleMarkReviewed} disabled={marking || !detail} style={styles.actionButton}>
              <SymbolView name="checkmark.circle" size={22} tintColor={theme.text} />
              <ThemedText type="smallBold">{marking ? 'Marking…' : 'Mark reviewed'}</ThemedText>
            </Pressable>
          </ThemedView>
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
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
  },
  safeArea: {
    flex: 1,
    paddingHorizontal: Spacing.four,
  },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingVertical: Spacing.two,
    gap: Spacing.two,
  },
  headerTitle: {
    flex: 1,
  },
  scroll: {
    paddingBottom: Spacing.three,
    gap: Spacing.three,
  },
  actionRow: {
    flexDirection: 'row',
    justifyContent: 'space-around',
    paddingVertical: Spacing.three,
  },
  actionButton: {
    alignItems: 'center',
    gap: Spacing.one,
  },
  doneBody: {
    marginTop: Spacing.two,
  },
  doneButton: {
    marginTop: Spacing.three,
  },
});
