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

Defined as code in `agentcore/cdk/lib/amplify-stack.ts` (Gen 2, `WEB_COMPUTE` platform — officially supports Next.js App Router SSR/Route Handlers). One piece can't be IaC'd: connecting to GitHub needs a Personal Access Token, since that's you authorizing AWS to access your own GitHub account — same shape as `eas build` needing your Apple credentials.

**One-time: generate a GitHub PAT.** GitHub → Settings → Developer settings → Personal access tokens → Fine-grained tokens → New token, scoped to just the `slip-box` repo, with **Contents: Read** and **Webhooks: Read and write** permissions (Amplify needs Webhooks to auto-deploy on push). CloudFormation does not persist this token beyond establishing the connection.

**Deploy:**
```bash
cd agentcore/cdk
export GITHUB_TOKEN=<the PAT above>
export API_KEY=<same value as .env.local — the API Gateway DemoKey>
export AMPLIFY_BASIC_AUTH_PASSWORD=<pick a password>   # gates the whole site, see below
npm run deploy:amplify
```

The stack outputs the app's default domain (`https://main.<app-id>.amplifyapp.com`). First deploy triggers Amplify's initial build automatically; every push to `main` after that redeploys via the webhook.

**Site-wide HTTP Basic Auth is mandatory, not optional.** The `API_KEY` env var only protects the AWS backend from unauthorized direct calls — it does nothing to stop anyone who finds the Amplify URL from viewing the pages themselves (your actual note content) or using the edge-correction UI. `AMPLIFY_BASIC_AUTH_PASSWORD` sets a username/password (`slipbox` / whatever you chose) that the browser prompts for before loading anything — set via `basicAuthConfig` in the CDK stack, enforced by Amplify Hosting itself, transmitted over HTTPS (Amplify Hosting is HTTPS-only by default). This is "good enough for a single-user demo," not real per-user auth — that arrives with multi-user support, see `docs/future-scope.md`.

To re-run later without re-exporting everything, keep those three values in your shell profile or a password manager — they're not stored in the repo or echoed back by `cdk deploy` (only the app ID, default domain, and basic-auth *username* are printed as outputs).

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
