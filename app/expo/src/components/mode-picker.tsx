import { Pressable, StyleSheet } from 'react-native';

import { ThemedText } from '@/components/themed-text';
import { ThemedView } from '@/components/themed-view';
import { Spacing } from '@/constants/theme';
import type { IngestMode } from '@/lib/api';

export const MODE_OPTIONS: { value: IngestMode; label: string; hint: string }[] = [
  { value: 'auto', label: 'Auto', hint: "Agent decides — one note, or several if there's a lot here" },
  { value: 'single', label: 'One idea', hint: 'Exactly one note — pick a topic below, or let it choose' },
  { value: 'all', label: 'All ideas', hint: 'One note per distinct idea in the source' },
];

export default function ModePicker({ mode, onChange }: { mode: IngestMode; onChange: (m: IngestMode) => void }) {
  return (
    <ThemedView style={styles.modeRow}>
      {MODE_OPTIONS.map((opt) => {
        const selected = opt.value === mode;
        return (
          <Pressable key={opt.value} onPress={() => onChange(opt.value)} style={styles.modeChipWrap}>
            <ThemedView
              type={selected ? 'backgroundSelected' : 'backgroundElement'}
              style={styles.modeChip}
            >
              <ThemedText type="small" themeColor={selected ? 'text' : 'textSecondary'}>
                {opt.label}
              </ThemedText>
            </ThemedView>
          </Pressable>
        );
      })}
    </ThemedView>
  );
}

const styles = StyleSheet.create({
  modeRow: {
    flexDirection: 'row',
    gap: Spacing.two,
  },
  modeChipWrap: {
    flex: 1,
  },
  modeChip: {
    paddingVertical: Spacing.two,
    borderRadius: Spacing.two,
    alignItems: 'center',
  },
});
