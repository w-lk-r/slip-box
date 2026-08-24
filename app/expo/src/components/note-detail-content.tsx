import { router } from 'expo-router';
import { Linking, Pressable, StyleSheet, View } from 'react-native';

import { ThemedText } from '@/components/themed-text';
import { ThemedView } from '@/components/themed-view';
import TypeBadge from '@/components/type-badge';
import { Spacing } from '@/constants/theme';
import type { EdgeType, ItemDetail } from '@/lib/api';
import { EDGE_COLORS } from '@/lib/typeColors';

export const EDGE_TYPE_LABEL: Record<EdgeType, string> = {
  SUPPORTS: 'Supports',
  CONTRADICTS: 'Contradicts',
  EXTENDS: 'Extends',
  RELATED_TO: 'Related to',
  GROUNDED_IN: 'Grounded in',
};

function groupBy<T extends { type: EdgeType }>(list: T[], key: (item: T) => string): Record<string, T[]> {
  const groups: Record<string, T[]> = {};
  for (const item of list) {
    const k = key(item);
    (groups[k] ??= []).push(item);
  }
  return groups;
}

function ConnectionGroup({
  label,
  entries,
  edgeColor,
}: {
  label: string;
  entries: { edgeId: string; id: string; title: string; confidence: number; direction: '→' | '←' }[];
  edgeColor: string;
}) {
  return (
    <View style={styles.connectionGroup}>
      <ThemedText type="small" themeColor="textSecondary">
        {label}
      </ThemedText>
      {entries.map((entry) => (
        <Pressable key={entry.edgeId} onPress={() => router.push(`/note/${encodeURIComponent(entry.id)}`)}>
          <ThemedView type="backgroundElement" style={styles.connectionRow}>
            <View style={[styles.connectionDot, { backgroundColor: edgeColor }]} />
            <ThemedText type="small" numberOfLines={1} style={styles.connectionTitle}>
              {entry.direction} {entry.title}
            </ThemedText>
            <ThemedText type="small" themeColor="textSecondary">
              ›
            </ThemedText>
          </ThemedView>
        </Pressable>
      ))}
    </View>
  );
}

// Shared between note/[noteId].tsx (edge-follow swipe) and the review stack
// (fixed-list swipe) — the note's own content and connections render
// identically either way; only what a swipe *does* differs between callers,
// so that stays owned by each screen, not this component. note/[noteId].tsx
// renders its own swipeable one-at-a-time connection browser instead of this
// static grouped list, so it passes hideConnections — review-stack.tsx keeps
// this list as-is, since paging through a known batch wants "see everything
// for context", not "traverse the graph one connection at a time".
export default function NoteDetailContent({
  item,
  swipeHint,
  hideConnections = false,
}: {
  item: ItemDetail;
  swipeHint?: string;
  hideConnections?: boolean;
}) {
  const outgoingByType = groupBy(item.outgoing_edges, (e) => e.type);
  const incomingByType = groupBy(item.incoming_edges, (e) => e.type);
  const hasEdges = !hideConnections && item.outgoing_edges.length + item.incoming_edges.length > 0;

  return (
    <>
      <ThemedText type="subtitle">{item.title}</ThemedText>

      <ThemedView style={styles.meta}>
        <TypeBadge type={item.type} />
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
        <Pressable disabled={!item.source.url} onPress={() => item.source!.url && Linking.openURL(item.source!.url)}>
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

      {hasEdges && (
        <ThemedView style={styles.connections}>
          <ThemedText type="smallBold">Connections</ThemedText>
          {!!swipeHint && (
            <ThemedText type="small" themeColor="textSecondary" style={styles.swipeHint}>
              {swipeHint}
            </ThemedText>
          )}
          {Object.entries(outgoingByType).map(([type, edges]) => (
            <ConnectionGroup
              key={`out-${type}`}
              label={EDGE_TYPE_LABEL[type as EdgeType] ?? type}
              edgeColor={EDGE_COLORS[type as EdgeType]}
              entries={edges.map((e) => ({ edgeId: e.edge_id, id: e.to_id, title: e.to_title, confidence: e.confidence, direction: '→' as const }))}
            />
          ))}
          {Object.entries(incomingByType).map(([type, edges]) => (
            <ConnectionGroup
              key={`in-${type}`}
              label={EDGE_TYPE_LABEL[type as EdgeType] ?? type}
              edgeColor={EDGE_COLORS[type as EdgeType]}
              entries={edges.map((e) => ({ edgeId: e.edge_id, id: e.from_id, title: e.from_title, confidence: e.confidence, direction: '←' as const }))}
            />
          ))}
        </ThemedView>
      )}
    </>
  );
}

const styles = StyleSheet.create({
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
  swipeHint: {
    opacity: 0.7,
  },
  connectionGroup: {
    gap: Spacing.one,
  },
  connectionRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.two,
    paddingVertical: Spacing.two,
    paddingHorizontal: Spacing.three,
    borderRadius: Spacing.two,
  },
  connectionDot: {
    width: 7,
    height: 7,
    borderRadius: 4,
  },
  connectionTitle: {
    flex: 1,
    opacity: 0.9,
  },
});
