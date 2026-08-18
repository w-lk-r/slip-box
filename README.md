# Slip Box

A personal AI agent that builds your second brain for you — capturing ideas, articles, and research notes automatically, so you can keep reading without losing what mattered.

Built for the [Agents for Humans Hackathon](https://agentsforhumans.devpost.com) using the [AWS Strands Agents SDK](https://strandsagents.com).

---

## The Problem

I love reading and researching. I've tried Obsidian. I've tried physical index cards and the [Zettelkasten method](https://en.wikipedia.org/wiki/Zettelkasten). Every time, the overhead of managing the system beats the joy of using it — and within a month the ideas I had are gone like they never happened.

This project is an attempt to fix that by offloading the note management entirely to an agent. The goal: keep reading, keep thinking, and let the agent handle the slip case.

## What It Does

Slip Box is an AI agent backed by an LLM (via AWS Bedrock) with tools tuned specifically for knowledge capture and retrieval. Rather than requiring you to format and file notes yourself, the agent:

- Accepts raw input — an article link, a quote, a half-formed idea
- Structures and stores it as an atomic note (Zettelkasten-style)
- Surfaces connections to what you've captured before
- Gets out of the way

## Status

This is an active hackathon build. Current state:

- [x] Hello world Strands agent running locally
- [ ] Note ingestion tool
- [ ] Local note storage and retrieval
- [ ] Link/connection surfacing between notes
- [ ] AgentCore deployment

Follow along via build stories on [builder.aws.com](https://builder.aws.com/content/3I4MB64uMOmRn5cpegeXNukBqEt/agents-for-humans-ideating-and-information-gathering).

## Getting Started

**Requirements:** Python 3.14+, AWS credentials configured for Bedrock access.

```bash
# Clone and set up
git clone https://github.com/jonathanwalker/slip-box.git
cd slip-box

python -m venv .venv
source .venv/bin/activate
pip install -r my_agent/requirements.txt

# Run the agent
python -m my_agent
```

AWS credentials must have permission to invoke Bedrock models. The Strands SDK uses Bedrock as its default LLM provider.

## Tech Stack

| Layer | Technology |
|---|---|
| Agent framework | [Strands Agents SDK](https://strandsagents.com) |
| LLM | AWS Bedrock |
| Language | Python 3.14 |
| Community tools | [strands-agents-tools](https://github.com/strands-agents/tools) |

## Hackathon

**Agents for Humans** — hosted by AWS on Devpost  
Track: **Professional Agents** (enhancing workplace productivity)  
Submission deadline: September 14, 2026  
Prize pool: $40,000

## License

MIT
