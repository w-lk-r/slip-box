import { Link, useFocusEffect } from 'expo-router';
import { useCallback, useState } from 'react';
import { StyleSheet } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { ThemedText } from '@/components/themed-text';
import { ThemedView } from '@/components/themed-view';
import { Spacing } from '@/constants/theme';
import { getApiKey } from '@/lib/api';

export default function HomeScreen() {
  const [hasApiKey, setHasApiKey] = useState<boolean | null>(null);

  useFocusEffect(
    useCallback(() => {
      getApiKey().then((key) => setHasApiKey(!!key));
    }, [])
  );

  return (
    <ThemedView style={styles.container}>
      <SafeAreaView style={styles.safeArea}>
        <ThemedText type="title" style={styles.title}>
          Slip Box
        </ThemedText>
        <ThemedText style={styles.body}>
          Share a link or a passage of text to this app from anywhere — Safari, YouTube, Notes —
          and it gets sent to your slip case for ingestion.
        </ThemedText>

        {hasApiKey === false && (
          <ThemedView type="backgroundElement" style={styles.notice}>
            <ThemedText type="smallBold">No API key set yet</ThemedText>
            <ThemedText type="small">Add one in Settings before sharing anything.</ThemedText>
          </ThemedView>
        )}

        <Link href="/recent" style={styles.link}>
          <ThemedText type="linkPrimary">Recent notes</ThemedText>
        </Link>
        <Link href="/settings" style={styles.link}>
          <ThemedText type="linkPrimary">Settings</ThemedText>
        </Link>
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
    padding: Spacing.four,
    gap: Spacing.three,
  },
  title: {
    marginTop: Spacing.five,
  },
  body: {
    opacity: 0.8,
  },
  notice: {
    padding: Spacing.three,
    borderRadius: Spacing.two,
    gap: Spacing.one,
  },
  link: {
    marginTop: Spacing.two,
  },
});
