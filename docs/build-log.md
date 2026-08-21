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

- Refactored `main.py` — tools extracted to `tools/notes.py` (self-contained with own clients); `main.py` slim to entrypoint, system prompt, agent factory only
- `write_note` now writes to DynamoDB `items` table alongside S3
- Added `write_summary` tool — creates `summary-card` notes; auto-triggered when agent finds 4+ converging notes post-search; on-demand on user request; written immediately, no draft
- Added `update_summary` tool — adds/removes notes from existing cluster, regenerates S3 frontmatter preserving body; supports overlapping clusters
- System prompt updated with cluster detection rules
- `scripts/backfill_items.py` — idempotent backfill of 7 existing S3 notes into DynamoDB
- Confirmed end-to-end: summary card created, written to S3 + DynamoDB, `grounded_in` all 7 source notes, synthesis quality strong

---

---

## Week 3 — Review & Edge Writing (Aug 21, 2026)

- Merged `docs/review-todo.md` from a Claude Code cloud session — 9-item gap review of `app/MyAgent/` vs. `CLAUDE.md`. Top finding: the `slip-box-edges` DynamoDB table exists in CDK but nothing ever writes to it — no `write_edge` tool, no classification step. Frontmatter link lists (`supports`/`contradicts`/`extends`/`related_to`) are always initialized empty and never populated.
- Reviewed the codebase against that list to pick the next build target.

**Decision (Aug 21):** Build edge writing next, not the S3→DynamoDB reconciliation Lambda (review-todo #9). Reasoning: the Lambda protects against notes being edited outside the three agent tools (`write_note`/`write_summary`/`update_summary`), and nothing does that yet — no live data-loss path to fix. Edges are the actual core value prop (typed connections between notes) and unblock everything downstream: confidence scoring, the graph view, pending-edge review, "Find more connections." Reconciliation infra can wait until something (Obsidian hand-edits, a FastAPI edit endpoint) actually writes to S3 outside the agent.

- Added `write_edge` tool (`tools/notes.py`) — writes `{from_id, to_id, type, confidence, history}` to DynamoDB `edges`, dropping silently below `EDGE_CONFIDENCE_THRESHOLD`; on write, regenerates the source note's frontmatter link list via a new `_regenerate_note_links` helper
- Added `_parse_frontmatter`/`_render_frontmatter` — small round-trip parser for this project's fixed frontmatter schema (not general YAML). `_regenerate_note_links` reads title/tags/date/etc. from the **S3 copy**, not DynamoDB, before rewriting only the link fields, so it doesn't clobber hand-edits — same fix should be back-ported to `update_summary`'s regeneration path (review-todo #9) next time that function is touched
- Edges render as `[[note_id|Title]]` wikilinks so Obsidian resolves them by filename while displaying the title
- System prompt (`main.py`) updated: agent now calls `write_edge` for relationships instead of just narrating them in its response text; added per-type guidance (SUPPORTS/CONTRADICTS/EXTENDS/RELATED_TO) and an instruction to score confidence honestly rather than inflate it
- Confidence scoring lives in the ingestion agent's own reasoning for now (no separate classification agent yet) — matches the "in-agent to start" plan
- `EDGES_TABLE` env var and DynamoDB IAM permissions were already wired in `agentcore.json`/`policies/agent-permissions.json` from the CDK setup — no infra change needed for this piece

- Tested locally via `agentcore dev`, found and fixed a real bug: the model used `GROUNDED_IN` between two literature notes (only valid `PermanentNote|SummaryCard → Item` per `CLAUDE.md`). `write_edge` now rejects `GROUNDED_IN` unless the source note's DynamoDB `type` is `permanent-note`/`summary-card`, with an error message the model can self-correct from; tool docstring tightened to steer away from it up front. Bad edges deleted, affected notes' frontmatter regenerated to clear the stale `grounded_in` entries.
- `agentcore deploy` run (Jonathan, via `agentcore deploy --yes` — non-interactive flag needed since `!`-prefixed shell commands aren't a TTY)
- Verified against the live deployed runtime with `agentcore invoke`: new note written, 3 correctly-typed edges created (SUPPORTS, EXTENDS ×2), no `GROUNDED_IN` misuse, frontmatter regenerated with `[[note_id|Title]]` wikilinks, note also picked up by `update_summary` into an existing cluster. `slip-box-edges` now has 6 rows total, all valid.

## Up Next

- [ ] Back-port the S3-not-DynamoDB frontmatter-read fix from `write_edge`'s `_regenerate_note_links` into `update_summary` (review-todo #9) — still rebuilds title/tags/date from DynamoDB there
- [ ] Classification agent as its own pass — split out of the ingestion agent once it's doing more than "score what I just found," e.g. re-scoring on demand ("what else is this connected to?")
- [ ] FastAPI backend — `/ingest`, `/notes` (permanent note write), `/edges/{id}` (edit/delete), `/graph`, `/items` (list all notes) endpoints
- [ ] Next.js frontend — two MVP screens: Ingest + permanent note editor (selection-first flow), Graph view with collapsible summary card clusters and inline edge editing
