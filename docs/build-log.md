# Build Log

Chronological record of decisions and progress.

---

## Week 1 — Scaffold & Deploy (Aug 18–19, 2026)

- Ideated concept: Zettelkasten-inspired research agent with typed relationships and confidence-gated human review
- Set up Strands hello world (`my_agent/`)
- Ran `agentcore create` to scaffold AgentCore project structure
- Migrated dependency management to `uv` / `pyproject.toml`
- Moved AgentCore scaffold to repo root (flattened `SlipBox/` nesting)
- `agentcore dev` confirmed working locally
- `agentcore deploy` confirmed — MyAgent live on AgentCore Runtime (ap-southeast-2)
- Gitignored `aws-targets.json`, added `aws-targets.sample.json`

---

- Added `SlipCaseMemory` via `agentcore add memory` (SEMANTIC, 365-day) — then identified 365-day hard cap as incompatible with a persistent second brain. AgentCore Memory's expiry is schema-enforced (`@max 365`) with no unlimited option, making it unsuitable as the primary knowledge store for a tool meant to retain notes indefinitely.
- **Decision:** replace AgentCore Memory with **Bedrock Knowledge Base + S3 `.md` files** as the persistent note store. Notes are written as `.md` files to S3, the Knowledge Base syncs from S3 and creates embeddings for semantic retrieval. Benefits: indefinite persistence, human-readable source of truth, and S3 sync to Obsidian becomes a one-liner — collapsing the "Obsidian export" future scope item into the core architecture.

---

- `agentcore add knowledge-base` — added `SlipCaseKB` backed by `s3://slip-box-notes`
- `SlipCaseMemory` (AgentCore Memory) already absent from config — no removal needed
- Deployed KB, uploaded test `.md` note, triggered sync, queried via `aws bedrock-agent-runtime retrieve` — semantic retrieval confirmed working (score 1.0)

---

---

## Week 2 — Ingestion Agent (Aug 20, 2026)

- Rewrote `app/MyAgent/main.py` as a real ingestion agent:
  - Zettelkasten system prompt: single idea → one atomic note; longer doc → multiple notes with explicit linkages
  - `write_note` tool — writes `.md` + `.md.metadata.json` sidecar to S3; sidecar keeps frontmatter out of KB embeddings so retrieval stays semantic
  - `search_notes` tool — semantic retrieval via Bedrock Knowledge Base
  - `trigger_kb_sync` tool — lists data sources, starts ingestion job so new notes become searchable
  - `fetch_url` tool — httpx GET with HTML stripping, capped at 50k chars
  - LRU session cache (128 sessions) keyed by `session_id` for AgentCore Runtime isolation
- Added `.env` / `.env.sample` for local dev; `S3_BUCKET` and `KB_ID` wired into `agentcore.json` `envVars` for cloud
- IAM permissions codified in `policies/agent-permissions.json` (S3 PutObject/GetObject/ListBucket, KB Retrieve, KB StartIngestionJob/ListDataSources) and referenced in `agentcore.json` `additionalPolicies`
- Tested locally via `agentcore dev`: single-idea ingest → one note, multi-idea doc → four notes with verbally identified relationships
- Deployed to AgentCore Runtime and confirmed working end-to-end in cloud (S3 write + KB search)
- Generated `docs/architecture.png` via `diagrams` library (full stack: User → Next.js → FastAPI → AgentCore agents → Bedrock → Knowledge Store)

---

**Decision (Aug 20):** Dropped pending-edge review queue. All edges above `EDGE_CONFIDENCE_THRESHOLD` (0.65, in `config.py`) are auto-written; below threshold edges are dropped entirely. Low-confidence edges render differently in the graph view so the user can correct inline. No `pending_edges` table needed.

**Decision (Aug 20):** `.md.metadata.json` sidecar exists because Bedrock KB requires it — it cannot be replaced by DynamoDB. The KB reads S3 directly and uses the sidecar to separate filterable metadata from embedded content. Keep it minimal (type, source, date, tags only); full metadata lives in DynamoDB.

**Decision (Aug 20):** Skip Neptune for MVP. Use DynamoDB `edges` table (`from_id`, `to_id`, `type`, `confidence`, `history`) — covers all MVP graph query needs without VPC complexity. Neptune remains the production target and stays in the architecture diagram.

**Decision (Aug 20):** PermanentNote write path bypasses the agent entirely (frontend → FastAPI → S3 + DynamoDB). Two authoring paths: **selection-first** (recommended) — user selects literature notes before writing, they appear in a reference panel alongside the editor, `GROUNDED_IN` edges written from selection on save (`authored_by: user`); **raw write** — user writes without pre-selecting, edges added manually or via agent afterward. Both paths support optional "Find more connections" post-save to let the classification agent propose additional edges (`authored_by: model`, additive only). Reference panel is the same component as the lit-note excerpts sidebar — just triggered pre-save.

## Up Next

- [ ] Provision DynamoDB — `items` table + `edges` table
- [ ] Build classification agent — proposes typed edges with confidence scores; writes edges ≥ threshold; drops below threshold; runs on both new literature notes and newly saved permanent notes
- [ ] FastAPI backend — `/ingest`, `/notes` (permanent note write), `/edges/{id}` (edit/delete), `/graph` endpoints
- [ ] Next.js frontend — two MVP screens: Ingest + permanent note editor, Graph view (inline edge editing)
