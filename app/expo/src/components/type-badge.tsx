import { StyleSheet, View } from 'react-native';

import { ThemedText } from '@/components/themed-text';
import { Spacing } from '@/constants/theme';
import type { ItemType } from '@/lib/api';
import { NODE_COLORS, TYPE_LABEL } from '@/lib/typeColors';

export default function TypeBadge({ type }: { type: ItemType }) {
  return (
    <View style={styles.row}>
      <View style={[styles.dot, { backgroundColor: NODE_COLORS[type] }]} />
      <ThemedText type="small" themeColor="textSecondary">
        {TYPE_LABEL[type] ?? type}
      </ThemedText>
    </View>
  );
}

const styles = StyleSheet.create({
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.one,
  },
  dot: {
    width: 7,
    height: 7,
    borderRadius: 4,
  },
});
