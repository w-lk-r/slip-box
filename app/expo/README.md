# Slip Box — Mobile (Expo)

The primary app for using the slip box day to day — capture, browse, review, and now synthesize, not just share-sheet capture alone. Three tabs: **Slip Box** (browse — Index/Recent/Summaries box switcher, flip-through note detail, multi-select-to-summarize), **Add Source** (share-sheet or in-app paste), **Review** (source-grouped swipeable stacks with inline tag/delete/mark-reviewed). Same FastAPI backend as the web app. See the root `CLAUDE.md`/`docs/build-log.md` for the wider project and design rationale — `docs/frontend-ux-spec.md` for the Review/Flipping/Index Cards UX design that this app implements.

Not built yet: read-only graph view (web-only for now), mobile share-sheet PDF support (needs an `app.json` config-plugin change plus a fresh `eas build`), and useful YouTube transcript extraction from a shared link beyond the client-side fetch already in `lib/youtube.ts` (see `docs/review-todo.md` #6).

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

- `src/app/(tabs)/` — the three tab screens: `index.tsx` (Slip Box — box switcher + note/index-card list), `submit.tsx` (Add Source), `review.tsx` (source-grouped review stacks list)
- `src/app/note/[noteId].tsx` — flip-through note detail: pages through a note's own connections one at a time, central note "out"
- `src/app/review-stack.tsx` — swipes through one review stack (a source's batch of unreviewed notes), with inline Delete/Tag/Mark reviewed
- `src/app/index-keyword.tsx` — modal: add a note to an Index Card keyword (existing keywords offered as suggestions first)
- `src/app/share.tsx`, `src/app/settings.tsx` — share-sheet ingest screen (thin wrapper over `useIngestFlow`), API key entry
- `src/lib/api.ts` — SecureStore-backed API key storage + every backend call (`ingest`, `summarize`, `getItem`, `getIndex`, `getReviewQueue`, `deleteItem`, etc.)
- `src/lib/shareIntent.ts` — maps `expo-share-intent`'s `{ text, webUrl }` shape to the API's `{url} | {text, source_url?}` payload — real text content wins over a same-share link (e.g. Kindle attaches both a quote and a link back to the book; the link becomes citation, not a substitute for the quote)
- `src/lib/useIngestFlow.ts` — the shared mode-picker/send/poll logic behind both Add Source and the share-sheet screen
- `src/lib/pendingIngestions.ts` — polls in-flight ingest/summarize sessions, backs the spinner row on both the Slip Box and Review tabs
- `src/lib/reviewStack.ts`, `src/lib/typeColors.ts` — small read-once stores / shared color constants (mirrors `app/web/lib/colors.ts`'s hex values)
- `src/components/` — `note-detail-content.tsx` (shared note rendering between flip-through and review-stack), `index-card-row.tsx`, `type-badge.tsx`, `mode-picker.tsx`, `pending-row.tsx`
- `src/hooks/`, `src/constants/theme.ts` — small reusable theming primitives kept from the initial scaffold
