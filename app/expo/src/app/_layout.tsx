import { DarkTheme, DefaultTheme, Stack, ThemeProvider, useRouter } from 'expo-router';
import { ShareIntentProvider, useShareIntentContext } from 'expo-share-intent';
import { useEffect } from 'react';
import { useColorScheme } from 'react-native';
import { GestureHandlerRootView } from 'react-native-gesture-handler';

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
    // Required by react-native-gesture-handler (note/[noteId].tsx's swipe-to-
    // navigate) — must wrap the whole app, not just the screen using it.
    <GestureHandlerRootView style={{ flex: 1 }}>
      <ShareIntentProvider>
        <ThemeProvider value={colorScheme === 'dark' ? DarkTheme : DefaultTheme}>
          <ShareIntentListener />
          <Stack>
            <Stack.Screen name="(tabs)" options={{ headerShown: false }} />
            {/* (tabs) is one Stack entry shared by all three tabs, so it has
                no single real title — the default back button would fall
                back to a generic, tab-blind "Back" no matter which tab you
                actually came from. headerBackButtonDisplayMode: 'minimal'
                shows just the chevron instead of a misleading label. True
                per-tab back labels would need each tab to own its own
                nested stack, a bigger restructure than this warrants. */}
            <Stack.Screen name="note/[noteId]" options={{ title: 'Note', headerBackButtonDisplayMode: 'minimal' }} />
            <Stack.Screen name="review-stack" options={{ title: 'Review', headerBackButtonDisplayMode: 'minimal' }} />
            <Stack.Screen name="settings" options={{ title: 'Settings', presentation: 'modal' }} />
            <Stack.Screen name="share" options={{ title: 'Add to Slip Box', presentation: 'modal' }} />
            <Stack.Screen name="index-keyword" options={{ title: 'Add to Index', presentation: 'modal' }} />
          </Stack>
        </ThemeProvider>
      </ShareIntentProvider>
    </GestureHandlerRootView>
  );
}
