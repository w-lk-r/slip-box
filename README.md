# Slip Box

A "second brain" research agent that extracts, summarizes, and finds **typed connections** between your sources — articles, YouTube videos, PDFs, plain text — and flags ambiguous relationships for your review before writing them to the graph.

Built for the [Agents for Humans Hackathon](https://agentsforhumans.devpost.com) using the [AWS Strands Agents SDK](https://strandsagents.com).

---

## The Problem

Tools like Obsidian and physical Zettelkasten slip-boxes get abandoned because managing the system costs more than using it. NotebookLM, Mem, and Sinapsus show you *similarity* — Slip Box shows **typed relationships** (SUPPORTS / CONTRADICTS / EXTENDS) and reasons about *how* things relate. Edges are auto-written above a confidence threshold and dropped below it — no queue, no noise — with confidence stored as metadata so low-confidence edges can render differently in the graph for the user to correct inline.

## What's built

Two Strands agents — an ingestion agent and a classification agent (split out via `Agent.as_tool()`), both live on AgentCore Runtime — plus a full product loop around them: a **Next.js web app** (force-directed graph view with inline edge correction, review queue, source browsing, PDF upload, permanent-note writing) and an **Expo mobile app** (the primary day-to-day app — share-sheet capture, review stacks, flip-through note browsing, a curated keyword index, on-demand summarization), both backed by a **FastAPI + API Gateway + Lambda** service.

Send a source (article, YouTube link, PDF, plain text) → the ingestion agent extracts and writes atomic notes → the classification agent scores typed relationships (SUPPORTS / CONTRADICTS / EXTENDS / RELATED_TO) against the rest of your corpus → confident connections write straight to the graph, low-confidence ones are dropped rather than queued, and anything near the threshold renders differently in the graph view so you can correct it inline.

An outward research fan-out mode (`--research` — search the web for corroborating/contradicting material before classification) was designed but is **not built**; it's out of MVP scope for now, blocked on picking a web-search provider. See [`docs/future-scope.md`](docs/future-scope.md) for the design.

See the root [`CLAUDE.md`](CLAUDE.md) for full architecture and design decisions, and [`docs/build-log.md`](docs/build-log.md) for the build's chronological progress.

## Live Demo

[main.d2viclhggmi7s9.amplifyapp.com](https://main.d2viclhggmi7s9.amplifyapp.com) — password-protected, credentials provided in the Devpost submission.

## Architecture

![Slip Box architecture diagram](docs/diagrams/architecture.png)

## Getting Started

**Requirements:** Python 3.14+, Node.js 20+, `uv`, `agentcore` CLI, AWS credentials with Bedrock access.

```bash
git clone https://github.com/w-lk-r/slip-box.git
cd slip-box

# Install agentcore CLI
npm install -g @aws/agentcore

# Install Python dependencies
cd app/MyAgent && uv sync && cd ../..

# Configure your AWS deployment target
cp agentcore/aws-targets.sample.json agentcore/aws-targets.json
# Edit aws-targets.json with your account ID and region

# Run locally
agentcore dev
```

## Hackathon

**Agents for Humans** — hosted by AWS on Devpost  
Track: **Professional Agents**  
Submission deadline: September 14, 2026

Follow the build on [builder.aws.com](https://builder.aws.com/content/3I4MB64uMOmRn5cpegeXNukBqEt/agents-for-humans-ideating-and-information-gathering).

## License

MIT
