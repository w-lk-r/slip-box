# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a hello-world setup for the [Strands Agents](https://strandsagents.com) framework — a Python SDK for building AI agents with tools. The single agent in `my_agent/agent.py` demonstrates the pattern: define tools (custom or from `strands-tools`), create an `Agent`, and invoke it with a message.

## Environment Setup

Python 3.14 with a `.venv` virtual environment:

```bash
source .venv/bin/activate
pip install -r my_agent/requirements.txt
```

## Running the Agent

```bash
python -m my_agent
```

Or directly:

```bash
python my_agent/agent.py
```

## Key Dependencies

- `strands-agents` — core agent framework (provides `Agent`, `tool` decorator)
- `strands-agents-tools` — community tool library (provides `calculator`, `current_time`, etc.)

## Architecture

The agent pattern used here:

1. **Custom tools** — decorated with `@tool`; must have typed args and a docstring (the SDK uses these for tool schemas)
2. **Community tools** — imported from `strands_tools` and passed directly to `Agent(tools=[...])`
3. **Model config** — `agent.model.config` reflects the underlying model settings; Strands defaults to Amazon Bedrock (requires AWS credentials)

To add a new tool, define a function with `@tool`, include a docstring and typed parameters, then add it to the `tools=[]` list in the `Agent` constructor.
