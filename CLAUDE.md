# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Slip Box is a multi-agent "second brain" built with the AWS Strands Agents SDK and hosted on AgentCore Runtime. It ingests sources (articles, YouTube, PDF, plain text), classifies typed relationships between them (SUPPORTS / CONTRADICTS / EXTENDS), and maintains a graph of those connections in Amazon Neptune. Ambiguous edges are confidence-gated and routed to the user via `handoff_to_user` rather than written automatically.

Full design rationale is in [`docs/hackathon-brief.md`](docs/hackathon-brief.md). AgentCore config and CLI reference is in [`AGENTS.md`](AGENTS.md).

## Project Structure

```
slip-box/
├── agentcore/          # AgentCore config and CDK (managed by agentcore CLI)
├── app/MyAgent/        # Strands agent code — main.py is the entrypoint
├── docs/               # Design docs and hackathon brief
├── AGENTS.md           # AgentCore CLI and schema reference
└── CLAUDE.md           # This file
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

# Deploy to AWS
agentcore deploy

# Invoke deployed agent
agentcore invoke --prompt "Hello"

# Validate agentcore config
agentcore validate

# Add a resource (memory, agent, gateway, etc.)
agentcore add <resource>
```

Run these from the repo root. The agentcore CLI reads `agentcore/agentcore.json` for config.

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

- **Default path:** ingest → write `.md` to S3 → trigger KB sync → semantic retrieval → classification → confidence gate → write to DynamoDB + Neptune
- **`--research` flag:** same, but triggers the research agent to fan out before classification

### Confidence gating

- Classification agent scores each proposed edge with a confidence value.
- **≥70% (configurable)** → auto-written, `status: auto`
- **<70%** → staged as `pending` in DynamoDB, surfaced to user via Strands `handoff_to_user`
- All edges support override; append-only `history` log per edge for provenance.
- Use `handoff_to_user` from the Strands SDK — do not build custom pause/resume logic.

### Storage

- **S3** — source of truth. Each ingested item is written as an atomic `.md` file with YAML frontmatter (source, date, confidence scores, relationship metadata). Human-readable, portable, enables Obsidian sync via `aws s3 sync`.
- **Bedrock Knowledge Base** — syncs from S3, creates embeddings for semantic retrieval. Indefinite persistence (no expiry). Replaces AgentCore Memory which has a hard 365-day cap incompatible with a permanent second brain.
  - Write a `.md.metadata.json` sidecar next to each `.md` file so frontmatter is indexed as filterable metadata, not embedded inline with the note body — keeps embeddings semantic rather than diluted with metadata text.
  - Use hierarchical/semantic chunking (not default fixed-size) for longer literature notes so retrieval doesn't cut mid-section.
- **DynamoDB** — `items` table (structured metadata per ingested item) and `pending_edges` table (confidence-gated edges awaiting review)
- **Amazon Neptune** — graph DB for typed edges. Vertex types: `Item`, `Concept`, `PermanentNote`, `Source`. Edge types: `MENTIONS`, `SUPPORTS`, `CONTRADICTS`, `EXTENDS`, `RELATED_TO`, `RESEARCHED_VIA`, `DISTILLED_INTO`, `GROUNDED_IN`

### Hosting

- **AgentCore Runtime** — session-isolated microVM. Required over Lambda because `--research` multi-agent chains can exceed Lambda's 15-min ceiling.
- **Build type:** CodeZip by default. Switch to Container in `agentcore.json` only if needed.

### Frontend

- **FastAPI** — backend API between Next.js and AWS (`/ingest`, `/pending-edges`, `/edges/{id}`, `/graph`)
- **Next.js / TypeScript** — three MVP screens: Ingest, Pending edge review, Graph view
- Graph visualization: react-force-graph or Cytoscape.js
- Hosting: AWS Amplify

### Key Strands tools

- Bedrock Knowledge Base retrieval — semantic search against ingested `.md` notes
- Web search/fetch (Tavily/Exa via `strands_tools`) — research fan-out
- Custom `@tool` functions — Neptune writes, DynamoDB writes, YouTube transcript extraction, SWOT logic
- `handoff_to_user` — confidence-gated human review

### Literature notes vs. permanent notes (stretch)

- `Item` model = literature note (source-bound)
- `PermanentNote` type = atomic, in user's own words, decontextualized
- Agent never auto-creates permanent notes — it proposes, user confirms. Reuses the same pending/confirm/override UX as edges.

## MVP Scope

Build in this order, get each layer solid before moving on:

1. Fast-path ingestion → DynamoDB/Neptune writes
2. Pending-edge review UI
3. `--research` fan-out
4. SWOT analysis and permanent note promotion (stretch)
