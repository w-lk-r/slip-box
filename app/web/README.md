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

## Deploy

Not yet connected to hosting. Per root `CLAUDE.md`, target is AWS Amplify Hosting (Gen 2, officially supports Next.js App Router). Connecting the GitHub repo and setting `API_KEY` in the Amplify Console's environment variables is an interactive AWS-console step — see `docs/build-log.md` for the handoff note.

## Structure

- `app/page.tsx` — Client Component, `next/dynamic(..., { ssr: false })`-loads `GraphView` (canvas-based graph libraries are hard client-only; in this Next.js version `ssr: false` is only permitted inside a Client Component, not a Server Component, hence `page.tsx` itself being `"use client"`)
- `components/GraphView.tsx` — `react-force-graph-2d`, node/edge coloring by type, edge dashing for lower-confidence edges
- `components/NodePanel.tsx` / `components/EdgePanel.tsx` — click-through detail and correction UI
- `app/api/graph`, `app/api/items/[noteId]`, `app/api/edges/[fromId]/[edgeId]` — Route Handlers proxying to the backend
- `lib/backend.ts` — shared server-only fetch helper (attaches `x-api-key`)
- `lib/types.ts` — types mirroring the backend's response shapes
