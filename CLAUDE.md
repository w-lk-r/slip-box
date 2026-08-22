# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Slip Box is a multi-agent "second brain" built with the AWS Strands Agents SDK and hosted on AgentCore Runtime. It ingests sources (articles, YouTube, PDF, plain text), classifies typed relationships between them (SUPPORTS / CONTRADICTS / EXTENDS), and maintains a graph of those connections in Amazon Neptune. All edges are auto-written; confidence score is stored as metadata and surfaced visually in the graph (low-confidence edges render differently) so the user can correct anything they disagree with.

Architecture and design decisions live in this file (below) and in [`docs/build-log.md`](docs/build-log.md) (chronological). The original hackathon pitch/submission strategy is in [`docs/hackathon-pitch.md`](docs/hackathon-pitch.md). AgentCore config and CLI reference is in [`AGENTS.md`](AGENTS.md). Adding a new DynamoDB table or GSI has a real checklist — see [`docs/schema-change-checklist.md`](docs/schema-change-checklist.md) before starting one.

## Project Structure

```
slip-box/
├── agentcore/           # AgentCore config and CDK (managed by agentcore CLI)
├── app/
│   ├── MyAgent/         # Strands agent code — main.py is the entrypoint
│   ├── api/             # FastAPI backend — Lambda + API Gateway (agentcore/cdk/lib/api-stack.ts)
│   ├── expo/            # Mobile app — share-sheet capture (see app/expo/README.md)
│   └── web/             # Next.js web app — graph view (see app/web/README.md)
├── docs/                # Design docs, build log, diagrams
│   └── diagrams/        # Generated architecture diagram(s)
├── scripts/             # Standalone utility scripts (backfill, diagram generation)
├── AGENTS.md            # AgentCore CLI and schema reference
└── CLAUDE.md            # This file
```

## Environment Setup

Dependencies are managed with `uv`. The virtual environment lives in `app/MyAgent/.venv`.

```bash
cd app/MyAgent
uv sync
```

AWS credentials must have Bedrock model invocation permissions.

## Commands

```bash
# Local development (hot-reload + browser inspector)
agentcore dev

# Deploy agent code + AgentCore resources
agentcore deploy

# Deploy application infrastructure (S3, DynamoDB, Neptune later)
# Run from agentcore/cdk/ — builds TypeScript then deploys SlipBox-App-* stack
cd agentcore/cdk && npm run deploy:app

# Invoke deployed agent
agentcore invoke --prompt "Hello"

# Validate agentcore config
agentcore validate

# Add a resource (memory, agent, gateway, etc.)
agentcore add <resource>

# Run the agent's Python test suite (from app/MyAgent/)
uv run pytest
```

Run agentcore commands from the repo root. The agentcore CLI reads `agentcore/agentcore.json` for config.

`npm run deploy:app` compiles TypeScript then deploys the `SlipBox-App-*` stack. npm scripts automatically resolve `cdk` from `node_modules/.bin`, so no global CDK install is needed.

## Testing

This project was verified live (real AWS calls, real deploys) for a long stretch before any automated tests existed — fine for early exploratory work, but it got genuinely expensive building the structured Source model (see `docs/build-log.md`, `docs/schema-change-checklist.md`): real bugs that a millisecond-scale local test would have caught instantly instead cost a multi-minute deploy-and-verify cycle each time.

**Write a test before, not instead of, live verification when:**
- Changing a pure-ish helper in `app/MyAgent/tools/notes.py` or `app/api/linkgen.py` — frontmatter parsing/rendering, source-key normalization, slugify, dedup logic. No AWS dependency, runs in milliseconds, and this exact class of function is where this project's real bugs have actually lived.
- Adding or changing DynamoDB read/write logic in a new shape — a new GSI query, a new dedup/lookup pattern. Use `moto` to mock DynamoDB in-process rather than a real table as the first pass; real-AWS verification still happens after, as integration confidence, not as first-pass debugging.
- Changing a FastAPI route's request/response shape (`app/api/models.py`, `app/api/routers/`) — FastAPI's own `TestClient` catches validator/serialization bugs with no real Lambda or API Gateway involved.

**Not worth it for:**
- The agent's own LLM reasoning/tool-calling judgment (system prompt changes, "should this note get written") — inherently a live-verification thing.
- One-off migration/backfill scripts — they run once against real data by design. What actually de-risks them is that the module functions they call are already tested, not testing the throwaway script itself.
- Frontend UI/visual behavior — `tsc`/`next build` already catch type errors; visual behavior stays a live (`claude-in-chrome`) check.

**General signal, not just the list above:** if verifying some part of the codebase by hand starts eating real time — repeated live checks for the same class of bug, a deploy-and-curl cycle standing in for what should be a fast local check — that's the point to add a test runner or test type for that area, not to just keep doing the slow check again next time. The list above is today's known cases; it isn't exhaustive, and new categories of slow manual checking should turn into new tests the same way.

**This isn't hypothetical — it's measured.** The Source model change (`app/MyAgent/tests/test_notes.py`) needed ~30–40 minutes of live-verification friction that the 23 tests written after the fact now cover in under a second: false alarms mistaken for bugs (agent judgment calls investigated via live logs when the question was really "is `_normalize_source_key` correct"), a full live round trip to prove dedup behavior a `moto` test proves instantly, and cleanup of dangling test data that only existed because verification meant creating real notes rather than asserting against a mock.

**Before starting a change like this, not after:** think about what verification the change will actually need once it's built, and whether writing that as a test *first* — before or alongside the implementation, not as a retrospective afterthought — would replace a chunk of live round trips with fast local ones. If the answer is yes, write the test first.

## Agent Code

`app/MyAgent/main.py` is the Strands agent wrapped in `BedrockAgentCoreApp` for AgentCore Runtime hosting:

- `BedrockAgentCoreApp()` — the hosting wrapper; handles HTTP serving and session isolation
- `@app.entrypoint` — called by AgentCore on each invocation (replaces direct `agent(message)` calls)
- `tools = []` — add custom `@tool` functions and community tools here
- `agent.stream_async` — streaming response back to caller
- Session management — LRU cache (128 sessions) keyed by `session_id`; resets on cold start

Custom tools follow the same pattern as standard Strands: `@tool` decorator, typed args, docstring for the tool schema.

**Default build type is CodeZip** (source packaged as zip, no Docker required). Container build is opt-in via `agentcore.json`.

## Architecture

![Slip Box architecture diagram](docs/diagrams/architecture.png)

*Solid lines are live today; dashed/dotted are planned (frontend, split-out agents, Neptune). Regenerate with `uv run python scripts/generate_architecture_diagram.py` (run from `app/MyAgent/` so it picks up the venv) after any change to what's actually wired up.*

### Multi-agent design

Four separate Strands agents — not one mega-prompt:

| Agent | Role |
|---|---|
| Ingestion agent | Extract, summarize, embed incoming source |
| Classification agent | Propose and score edge type (SUPPORTS/CONTRADICTS/EXTENDS) |
| Research agent | Outward search/fetch fan-out (`--research` mode only) |
| SWOT/analysis agent | Cluster synthesis and analysis |

Review Strands multi-agent primitives (Agent-as-Tool, Swarm, A2A) before wiring these together.

### Two-tier ingestion

- **Default path:** ingest → write `.md` to S3 → trigger KB sync → semantic retrieval → classification → write to DynamoDB + Neptune
- **`--research` flag:** same, but triggers the research agent to fan out before classification

### Confidence and edge correction

- Classification agent scores each proposed edge with a confidence value (0–1).
- **Threshold (`EDGE_CONFIDENCE_THRESHOLD` in `app/MyAgent/config.py`, default 0.65):** edges at or above threshold are written to Neptune; edges below are dropped entirely — no queue, no noise.
- Confidence is stored as metadata on the Neptune edge and in the `.md.metadata.json` sidecar.
- In the graph view, edges near the threshold render differently (dashed line / muted colour) so the user can spot and correct anything they disagree with inline.
- All edges are user-editable/deletable from the graph view; append-only `history` log per edge for provenance.
- To re-examine dropped connections, the user can ask the agent "what else is this connected to?" and classification reruns on demand.

**Connections live on the card, matching the original method** (Luhmann's notes carried references to other notes on the card itself, not in a separate index):
- Connections are written into the note's own frontmatter (not the body) as typed link lists (`supports`, `contradicts`, `extends`, `related_to`) using `[[wikilinks]]`, so Obsidian's graph/backlinks picks them up. Regenerated from Neptune's current edge state on every change, never appended. Body stays pure prose; frontmatter is system-generated — no clobbering risk.
- Excluded from KB embedding like the rest of frontmatter; mirrored into `.md.metadata.json` for KB filtering.
- **Neptune stays the source of truth for the graph** — S3 is source of truth for note content, frontmatter connections are a generated reflection, never authored directly.

### Storage

- **S3** — source of truth. Each ingested item is written as an atomic `.md` file with YAML frontmatter (source, date, confidence scores, relationship metadata). Human-readable, portable, enables Obsidian sync via `aws s3 sync`.
- **Bedrock Knowledge Base** — syncs from S3, creates embeddings for semantic retrieval. Indefinite persistence (no expiry). Replaces AgentCore Memory which has a hard 365-day cap incompatible with a permanent second brain.
  - The `.md.metadata.json` sidecar is a **Bedrock KB requirement**, not an application choice — the KB reads it during S3 sync to treat those fields (type, source, date, tags) as filterable metadata rather than embedding them as content. Without it, frontmatter bleeds into the embedding and degrades retrieval. The KB cannot read DynamoDB; the sidecar cannot be eliminated.
  - Keep the sidecar minimal: only the fields the KB needs for filtering. Full metadata lives in DynamoDB.
  - Use hierarchical/semantic chunking (not default fixed-size) for longer literature notes so retrieval doesn't cut mid-section.
- **DynamoDB** — `items` table (structured metadata for all note types: `literature-note`, `permanent-note`; `recent-index` GSI — constant `gsi_pk`, sort key `created_at` — so the Recent list can `Query` newest-first instead of an unordered `Scan`; `source-index` GSI, keyed on `source_id`, answers "every note from this source"), `edges` table (`from_id`, `to_id`, `type`, `confidence`, `history`; `to_id-index` GSI for reverse lookups), and `sources` table (`source_id`, `source_key`, `title`, `author`, `type: web|youtube|pdf`, `url`, `retrieved_at`; `source-key-index` GSI on `source_key` — a normalized URL, or a content hash once PDF ingestion lands — for write-time dedup, so the same source cited by multiple notes resolves to one shared record). Notes reference their source via `source: [[source-id|Title]]` in frontmatter, same wikilink pattern as edges. Neptune is the production graph target but DynamoDB covers all MVP query needs without VPC complexity.
- **Amazon Neptune** — graph DB for typed edges. Vertex types: `Item`, `Concept`, `PermanentNote`, `SummaryCard` (see Note taxonomy below), `Source`. Every vertex carries `created_at`/`updated_at` — powers the timeline/MOC view (see Frontend below). Edge types: `MENTIONS`, `SUPPORTS`, `CONTRADICTS`, `EXTENDS`, `RELATED_TO`, `RESEARCHED_VIA`, `DISTILLED_INTO`, `GROUNDED_IN`. `Source` and `RESEARCHED_VIA` are implemented today in DynamoDB (above) but not yet as graph-visible Neptune vertices/edges — that's deferred until Neptune itself is wired up.

### Hosting

- **AgentCore Runtime** — session-isolated microVM. Required over Lambda because `--research` multi-agent chains can exceed Lambda's 15-min ceiling.
- **Build type:** CodeZip by default. Switch to Container in `agentcore.json` only if needed.

### Frontend

- **FastAPI** — backend API between Next.js and AWS, deployed as two Lambda functions behind API Gateway (`agentcore/cdk/lib/api-stack.ts`, `app/api/`). `POST /ingest` is asynchronous — an `ApiFunction` validates input and hands off to a `WorkerFunction` that calls `invoke_agent_runtime` (sidesteps API Gateway's ~29s Lambda-proxy timeout, which a synchronous multi-tool-call ingest can exceed); the frontend polls `GET /items` for the result. `GET /items`, `GET /graph`, and `PATCH`/`DELETE /edges/{from_id}/{edge_id}` (composite path — the edges table's key is PK `from_id` + SK `edge_id`, no GSI for point-addressing by `edge_id` alone) read/write DynamoDB directly, no agent involved. Auth via API Gateway's native API Key + Usage Plan (single shared key — real per-user auth arrives with multi-user support, see `docs/future-scope.md`).
- **Next.js / TypeScript** (`app/web/`, App Router) — graph view built; Ingest screen not built (mobile's share-sheet already covers capture, see the Mobile section below). Inline edge editing — no separate pending-review queue, since edges are auto-written above threshold, see Confidence and edge correction below.
- Graph visualization: `react-force-graph-2d` (the 2D-only sub-package — the combined `react-force-graph` package pulls in three.js/WebGL for 3D/VR support this project doesn't need). Node color by type, edge color by type, edge dashing below a review-worthy confidence cutoff (separate constant from `EDGE_CONFIDENCE_THRESHOLD`, which gates writes, not rendering).
- Auth: Next.js Route Handlers as a backend-for-frontend proxy (`app/web/lib/backend.ts`) hold the API key server-side — unlike the mobile app's on-device `expo-secure-store`, a web JS bundle is inherently public, so the key never reaches the browser. The deployed app therefore never hits CORS either (same-origin); CORS is still enabled on the API Gateway (`defaultCorsPreflightOptions` in `api-stack.ts`) for local dev iteration against the live API directly.
- Timeline mode (stretch): same graph data, laid out by `created_at` instead of force-directed, for viewing a MOC's linked notes or a note's neighborhood in chronological/insertion order
- Hosting: AWS Amplify (Gen 2 — officially supports Next.js App Router). Set up directly via the Amplify Console rather than CDK — an earlier CDK-managed attempt hit a persistent, unresolved `Unable to assume specified IAM Role` build error even with AWS's own blessed service-role setup; see `app/web/README.md` for the working Console setup steps and `docs/build-log.md` for the debugging trail.

### Mobile

- **Expo / React Native** (`app/expo/`) — share-sheet capture (`expo-share-intent`, one config plugin for both iOS and Android) plus a lightweight recent-notes browse view. Same backend as the web app; API key stored on-device via `expo-secure-store` rather than a server-side proxy, since there's no server tier in a mobile app to hold it. See `app/expo/README.md`.

### Key Strands tools

- Bedrock Knowledge Base retrieval — semantic search against ingested `.md` notes
- Web search/fetch (Tavily/Exa via `strands_tools`) — research fan-out
- Custom `@tool` functions — Neptune writes, DynamoDB writes, YouTube transcript extraction, SWOT logic
- `handoff_to_user` — confidence-gated human review

### Note taxonomy: literature notes, ideas, summary cards

Not a uniform rule across all three: `Item` and `SummaryCard` are information transformation (AI doing this well doesn't undercut the method) and carry `authored_by: model | user`; `PermanentNote` is where the human forming the idea in their own words is the actual point, so it's user-authored only.

- `Item` = literature note (source-bound). `authored_by: model` is the default (ingestion agent extraction, auto-written, no gate); `authored_by: user` when the user writes/replaces it directly. `edited_by_user: bool` flags a model note later hand-edited.
- `PermanentNote` = idea, atomic, decontextualized. **Always user-authored — no `authored_by` field, no draft state.** Agent never creates a `PermanentNote` vertex or writes to its body. Write path is direct: frontend → FastAPI → S3 + DynamoDB + KB sync trigger (no agent in the loop).
  - **Recommended path (selection-first):** user browses graph/note list and clicks literature notes to select them as the basis before writing. Selected notes appear in a reference panel alongside the editor — the act of selecting and reading IS the thinking. On save, `GROUNDED_IN` edges are written automatically from the selection (`authored_by: user`). Mirrors Luhmann pulling physical notes onto the desk before writing.
  - **Alternative path (raw write):** user opens a blank editor and writes directly without pre-selecting. Edges can be added manually after, or via "Find more connections."
  - In both cases: optional "Find more connections" button triggers the classification agent post-save to propose additional `RELATED_TO` / `GROUNDED_IN` edges the user didn't explicitly choose. Agent edges are `authored_by: model`, additive only — never removes or overwrites user-created edges.
  - The reference panel showing selected lit notes while writing is the same component as the literature excerpts sidebar, just triggered pre-save rather than post.
- `SummaryCard` = cluster-synthesis rollup spanning multiple items/ideas. `authored_by: model` or `authored_by: user`. Written immediately — no draft state. User deletes if unwanted.
  - **Automatic trigger:** after KB search post-ingestion, if 4+ existing notes converge on the same core idea, the ingestion agent writes a summary card grounding it in those notes.
  - **Add to existing cluster:** if a new note belongs to an existing summary card found in search results, agent calls `update_summary` to add it rather than creating a new card.
  - **Overlapping clusters:** a note can belong to multiple summary cards — `update_summary` is called for each. In the graph, a note in two clusters renders as a bridge node between them when both are collapsed, making conceptual bridges visible.
  - **On-demand:** user asks "summarise my notes on X" — agent searches, synthesises, writes.
  - **Graph role:** summary cards are collapsible cluster nodes. `grounded_in` note_ids define cluster membership. Collapsed = one node with edges routing through it; expanded = individual notes visible with summary card as hub. Prevents the graph growing into a hairball as the corpus grows.
  - **Cluster editing:** user can add/remove notes from a cluster via the graph UI (drag in/out), which calls `update_summary` via FastAPI.

**Linkages** — no new edge types; widen the existing distillation edges' allowed vertex types instead:
- `DISTILLED_INTO`: `Item | PermanentNote` → `PermanentNote | SummaryCard`
- `GROUNDED_IN`: `PermanentNote | SummaryCard` → `Item`

**Structure notes / MOCs** — also no new vertex type: a MOC is just a `PermanentNote` whose content is a curated set of `RELATED_TO` links. Rather than a manual ordering field, its linked notes render sorted by `created_at` — replicating Luhmann's Folgezettel numbering, which encoded chronological insertion order alongside topic structure.

## MVP Scope

Build in this order, get each layer solid before moving on:

1. Fast-path ingestion → DynamoDB/Neptune writes
2. Inline edge correction UI (graph view) — pivoted away from a separate pending-review queue, see Confidence and edge correction above
3. `--research` fan-out
4. SWOT analysis and permanent note promotion (stretch)
5. Frontmatter as a pending-connection review surface (stretch)
