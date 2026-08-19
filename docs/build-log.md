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

## Up Next

- [ ] Rewrite `app/MyAgent/main.py` — ingestion agent system prompt + `ingest_source` tool (writes `.md` to S3, triggers KB sync)
- [ ] Wire KB retrieval into agent tools
- [ ] Provision DynamoDB — `items` table and `pending_edges` table
