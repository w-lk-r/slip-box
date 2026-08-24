import { ActivityIndicator, StyleSheet } from 'react-native';

import { ThemedText } from '@/components/themed-text';
import { ThemedView } from '@/components/themed-view';
import { Spacing } from '@/constants/theme';

// Shared by the Slip Box tab (ingest spinner rows) and the Review tab — a
// note or summary card mid-ingestion shouldn't look like a silent gap in
// the queue on either screen. Both read the same generic session-status
// polling from lib/pendingIngestions.ts.
export default function PendingRow({ label }: { label?: string }) {
  return (
    <ThemedView type="backgroundElement" style={styles.row}>
      <ActivityIndicator size="small" />
      <ThemedText type="small" themeColor="textSecondary">
        {label ?? 'Generating notes from your share…'}
      </ThemedText>
    </ThemedView>
  );
}

const styles = StyleSheet.create({
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.two,
    padding: Spacing.three,
    borderRadius: Spacing.two,
  },
});
