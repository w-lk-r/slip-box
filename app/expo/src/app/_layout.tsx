import { DarkTheme, DefaultTheme, Stack, ThemeProvider, useRouter } from 'expo-router';
import { ShareIntentProvider, useShareIntentContext } from 'expo-share-intent';
import { useEffect } from 'react';
import { useColorScheme } from 'react-native';

function ShareIntentListener() {
  const router = useRouter();
  const { hasShareIntent } = useShareIntentContext();

  useEffect(() => {
    if (hasShareIntent) {
      router.push('/share');
    }
  }, [hasShareIntent, router]);

  return null;
}

export default function RootLayout() {
  const colorScheme = useColorScheme();

  return (
    <ShareIntentProvider>
      <ThemeProvider value={colorScheme === 'dark' ? DarkTheme : DefaultTheme}>
        <ShareIntentListener />
        <Stack>
          <Stack.Screen name="index" options={{ title: 'Slip Box' }} />
          <Stack.Screen name="recent" options={{ title: 'Recent Notes' }} />
          <Stack.Screen name="settings" options={{ title: 'Settings', presentation: 'modal' }} />
          <Stack.Screen name="share" options={{ title: 'Add to Slip Box', presentation: 'modal' }} />
        </Stack>
      </ThemeProvider>
    </ShareIntentProvider>
  );
}
