# Slip Box — Mobile (Expo)

Share-sheet capture app: share a link or text from any other app (Safari, YouTube, Notes) and it gets POSTed to the Slip Box FastAPI backend's `/ingest` endpoint. See `docs/review-todo.md` #12 in the repo root for the design notes this was scoped from, and the root `CLAUDE.md`/`docs/build-log.md` for the wider project.

Not built yet (deliberately out of scope for this pass): read-only graph/item browsing, and useful YouTube transcript extraction (sharing a YouTube link works mechanically today, but `fetch_url` on the agent side just strips HTML off the watch page — see `docs/review-todo.md` #6).

## One-time setup

This app uses native config plugins (`expo-share-intent`, `expo-secure-store`), so it **cannot run in Expo Go** — you need a development build.

1. `npm install`
2. `eas login` (your own Expo account)
3. `eas build --profile development --platform ios` — and/or `--platform android`. First iOS build will prompt for Apple Developer credentials (App Group entitlement + provisioning for the share extension target) — follow the interactive prompts.
4. Install the resulting build on your device (EAS gives you a link/QR code).
5. `npx expo start` — from here on, iterate on JS/TS normally; you only need to repeat step 3 if you change native config (`app.json` plugins, add a new native dependency).
6. Open the app once, go to Settings, paste in the API key for the deployed backend (`agentcore/cdk/lib/api-stack.ts`'s `DemoKey` — retrieve via `aws apigateway get-api-key --api-key <id> --include-value`). Stored in the device Keychain/Keystore via `expo-secure-store`, not baked into the build.

## Try it

Share a URL from Safari (or the YouTube app, or any app with a share sheet) → Slip Box should appear as a share target → tap it → confirm → "Sent". Check `GET /items` (or `aws dynamodb scan --table-name slip-box-items`) a few seconds later to confirm it landed.

## Structure

- `src/app/` — Expo Router screens (`index.tsx` home, `settings.tsx` API key entry, `share.tsx` the share-preview/send screen)
- `src/lib/api.ts` — SecureStore-backed API key storage + the `ingest()` call to `/ingest`
- `src/lib/shareIntent.ts` — maps `expo-share-intent`'s `{ text, webUrl }` shape to the API's `{url} | {text}` payload
- `src/components/`, `src/hooks/`, `src/constants/theme.ts` — small reusable theming primitives kept from the initial scaffold
