/**
 * expo-share-intent hands off from the iOS extension via a deep link built
 * with expo-linking's createURL("dataUrl=") — e.g. slipboxmobile://dataUrl=...
 * That path doesn't match any real route, so without this file Expo Router
 * shows "Unmatched Route" instead of opening the app. This intercepts any
 * incoming system path before routing and redirects share-intent handoffs
 * to the real /share screen.
 * https://docs.expo.dev/router/advanced/native-intent/
 */
export function redirectSystemPath({ path }: { path: string; initial: boolean }): string {
  if (path.includes('dataUrl=')) {
    return '/share';
  }
  return path;
}
