# Slip Box

A "second brain" research agent that extracts, summarizes, and finds **typed connections** between your sources — articles, YouTube videos, PDFs, plain text — and flags ambiguous relationships for your review before writing them to the graph.

Built for the [Agents for Humans Hackathon](https://agentsforhumans.devpost.com) using the [AWS Strands Agents SDK](https://strandsagents.com).

---

## The Problem

Tools like Obsidian and physical Zettelkasten slip-boxes get abandoned because managing the system costs more than using it. NotebookLM, Mem, and Sinapsus show you *similarity* — Slip Box shows **typed relationships** (SUPPORTS / CONTRADICTS / EXTENDS) and reasons about *how* things relate. Ambiguous edges are surfaced for human review rather than silently written to the graph.

## Two Modes

**Default:** send a source → embed → auto-match → connections written or queued for review. Fast, always-on.

**`--research` flag:** same ingestion, but the agent fans out to find corroborating and contradicting material before folding results into the graph. Slower and deliberate.

See [`docs/hackathon-brief.md`](docs/hackathon-brief.md) for full architecture and design decisions.

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
