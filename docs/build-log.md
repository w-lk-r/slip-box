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

## Up Next

- [ ] `agentcore add memory` — add long-term semantic memory (the knowledge base store for ingested items)
- [ ] Rewrite `app/MyAgent/main.py` — ingestion agent system prompt + `ingest_source` tool
- [ ] Provision DynamoDB — `items` table and `pending_edges` table
