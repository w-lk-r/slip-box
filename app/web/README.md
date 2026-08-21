# Slip Box — Web (Graph View)

Force-directed graph view of the Slip Box knowledge graph, plus inline edge correction (the "confirm/override" half of the design loop — see root `CLAUDE.md`). Reads from the same FastAPI backend the Expo app uses.

Not built yet (deliberately out of scope for this pass): an Ingest screen (mobile's share-sheet already covers capture), summary-card cluster collapse/expand, timeline mode.

## How auth works

Unlike the mobile app (which stores the API key on-device via `expo-secure-store`), this app proxies every backend call through its own Next.js Route Handlers (`app/api/*`), which hold the key server-side (`API_KEY` env var, never `NEXT_PUBLIC_`-prefixed). The browser only ever talks to this app's own origin — the API key never reaches client-side JS.

## Local setup

```bash
npm install
cp .env.local.sample .env.local
# Fill in API_KEY — retrieve with:
# aws apigateway get-api-key --api-key rjd5535v64 --include-value --region ap-southeast-2 --query value --output text
npm run dev
```

Open `http://localhost:3000` — click a node for its full note detail, click an edge to change its type or delete it.

## Deploy (AWS Amplify Hosting)

Set up directly in the **Amplify Console** (Gen 2, `WEB_COMPUTE` platform — officially supports Next.js App Router SSR/Route Handlers), not via CDK. An earlier pass tried managing this as code (`agentcore/cdk/lib/amplify-stack.ts`), but every build failed with Amplify's `Unable to assume specified IAM Role` error regardless of how the service role's trust policy was configured — including the exact role AWS's own Console-driven "Amplify - Backend Deployment" role-creation flow produces. Root cause undetermined (possibly related to this account's use of root credentials rather than an IAM user — service-to-service role assumption can behave differently under a literal root session). Reverted the CDK stack rather than keep fighting it; see `docs/build-log.md` for the full debugging trail if picking this back up later.

**Console setup, one-time:**
1. Amplify Console → **Create new app** → connect the `slip-box` GitHub repo, branch `main`.
2. Monorepo: set the app root to `app/web`.
3. Environment variables: `API_KEY` (same value as this app's `.env.local`), `BACKEND_BASE_URL` (the API Gateway `prod` endpoint).
4. **App settings → IAM roles** — attach a service role (Console-created via the "Amplify - Backend Deployment" use case).
5. **App settings → General → Edit** — enable HTTP Basic Auth, set a username/password. This is mandatory, not optional: `API_KEY` only protects the AWS backend from unauthorized direct calls, it does nothing to stop anyone who finds the Amplify URL from viewing note content or using the edge-correction UI.
6. Save, then trigger the first build manually (Console → "Run build") — connecting the app doesn't auto-build until the next push.

**Critical, easy-to-miss step:** Amplify Console environment variables are only available at *build* time by default — Next.js Route Handlers (which run inside the SSR compute Lambda at request time) don't see them, so `/api/*` routes 500 with "must be set" even though the Console clearly shows the values configured. Fix: **App settings → Build settings → Edit**, and add a line to the `build` phase, before `npm run build`, that writes the needed vars into `.env.production` (relative to the app root — the build phase's working directory is already `app/web`, not the repo root, despite what AWS's own monorepo docs example implies):
```yaml
build:
  commands:
    - env | grep -e API_KEY -e BACKEND_BASE_URL >> .env.production
    - npm run build
```
Next.js loads `.env.production` at build time and those values become part of the server bundle, available to `process.env` inside Route Handlers at runtime.

## Structure

- `app/page.tsx` — Client Component, `next/dynamic(..., { ssr: false })`-loads `GraphView` (canvas-based graph libraries are hard client-only; in this Next.js version `ssr: false` is only permitted inside a Client Component, not a Server Component, hence `page.tsx` itself being `"use client"`)
- `components/GraphView.tsx` — `react-force-graph-2d`, node/edge coloring by type, edge dashing for lower-confidence edges, hover tooltips on both nodes and edges
- `components/NoteCard.tsx` — shared note renderer (title/type/date/tags/body), used by both panels below
- `components/NodePanel.tsx` — click a node → full note detail via `NoteCard`
- `components/EdgePanel.tsx` — click an edge → both connected notes (via `NoteCard`) with a visual connector carrying the type/confidence + change/delete controls; note titles are clickable to drill into that note's own `NodePanel` view
- `app/api/graph`, `app/api/items/[noteId]`, `app/api/edges/[fromId]/[edgeId]` — Route Handlers proxying to the backend
- `lib/backend.ts` — shared server-only fetch helper (attaches `x-api-key`)
- `lib/useItem.ts` — shared fetch-by-`note_id` hook (`EdgePanel` needs it twice, once per endpoint)
- `lib/types.ts` — types mirroring the backend's response shapes
