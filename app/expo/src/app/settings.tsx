import { router } from 'expo-router';
import { useEffect, useState } from 'react';
import { StyleSheet, TextInput } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { ThemedText } from '@/components/themed-text';
import { ThemedView } from '@/components/themed-view';
import { Spacing } from '@/constants/theme';
import { useTheme } from '@/hooks/use-theme';
import { getApiKey, setApiKey } from '@/lib/api';

export default function SettingsScreen() {
  const theme = useTheme();
  const [key, setKey] = useState('');
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    getApiKey().then((existing) => {
      if (existing) setKey(existing);
    });
  }, []);

  async function handleSave() {
    await setApiKey(key.trim());
    setSaved(true);
    setTimeout(() => router.back(), 400);
  }

  return (
    <ThemedView style={styles.container}>
      <SafeAreaView style={styles.safeArea}>
        <ThemedText type="subtitle">API Key</ThemedText>
        <ThemedText type="small" style={styles.hint}>
          The key for your Slip Box API Gateway (set up once — stored securely on this device).
        </ThemedText>
        <TextInput
          value={key}
          onChangeText={setKey}
          placeholder="Paste your API key"
          placeholderTextColor={theme.textSecondary}
          autoCapitalize="none"
          autoCorrect={false}
          secureTextEntry
          style={[styles.input, { color: theme.text }]}
        />
        <ThemedText type="link" onPress={handleSave} style={styles.saveButton}>
          {saved ? 'Saved ✓' : 'Save'}
        </ThemedText>
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
  hint: {
    opacity: 0.7,
  },
  input: {
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: '#8888',
    borderRadius: Spacing.two,
    padding: Spacing.three,
    fontSize: 16,
  },
  saveButton: {
    textAlign: 'center',
    marginTop: Spacing.two,
  },
});
