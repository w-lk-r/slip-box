# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Slip Box is a multi-agent "second brain" built with the AWS Strands Agents SDK. It ingests sources (articles, YouTube, PDF, plain text), classifies typed relationships between them (SUPPORTS / CONTRADICTS / EXTENDS), and maintains a graph of those connections in Amazon Neptune. Ambiguous edges are confidence-gated and routed to the user via `handoff_to_user` rather than written automatically.

Full design rationale is in [`docs/hackathon-brief.md`](docs/hackathon-brief.md).

## Environment Setup

Python 3.14 with a `.venv` virtual environment:

```bash
source .venv/bin/activate
pip install -r my_agent/requirements.txt
```

AWS credentials must have Bedrock model invocation permissions. Strands defaults to Bedrock for LLM inference.

## Running the Agent

```bash
python -m my_agent
```

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

- **Default path:** ingest → AgentCore Memory (embed/retrieve) → classification → confidence gate → write to DynamoDB + Neptune
- **`--research` flag:** same, but triggers the research agent to fan out before classification

### Confidence gating

- Classification agent scores each proposed edge with a confidence value.
- **≥70% (configurable)** → auto-written, `status: auto`
- **<70%** → staged as `pending` in DynamoDB, surfaced to user via Strands `handoff_to_user`
- All edges support override; append-only `history` log per edge for provenance.
- Use `handoff_to_user` from the Strands SDK — do not build custom pause/resume logic.

### Storage

- **DynamoDB** — `items` table (source of truth per ingested item) and `pending_edges` table
- **Amazon Neptune** — graph DB for typed edges. Vertex types: `Item`, `Concept`, `PermanentNote`, `Source`. Edge types: `MENTIONS`, `SUPPORTS`, `CONTRADICTS`, `EXTENDS`, `RELATED_TO`, `RESEARCHED_VIA`, `DISTILLED_INTO`, `GROUNDED_IN`
- **AgentCore Memory** — managed embed/retrieve for the fast default path

### Hosting

- **AgentCore Runtime** — containerized (arm64, ECR), session-isolated. Required over Lambda because `--research` multi-agent chains can exceed Lambda's 15-min ceiling.

### Frontend

- **FastAPI** — backend API between Next.js and AWS (`/ingest`, `/pending-edges`, `/edges/{id}`, `/graph`)
- **Next.js / TypeScript** — three MVP screens: Ingest, Pending edge review, Graph view
- Graph visualization: react-force-graph or Cytoscape.js
- Hosting: AWS Amplify

### Key Strands tools

- `agent_core_memory` — fast-path embed/retrieve
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
