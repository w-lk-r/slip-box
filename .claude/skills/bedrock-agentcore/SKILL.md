---
name: bedrock-agentcore
description: Operating Amazon Bedrock AgentCore Runtime for this project — hosting behavior, observability tooling, and hard-won IAM/deploy gotchas. Complements AGENTS.md's schema/CLI reference rather than duplicating it.
license: MIT
---

# Bedrock AgentCore Runtime — Operating Notes

`AGENTS.md` at the repo root is the schema/CLI reference (config shape, resource types, all `agentcore` subcommands) — read that first for "what exists." This skill covers "how it actually behaves" and the mistakes already made in this repo so they don't get repeated.

## Hosting model

- `BedrockAgentCoreApp` (from `bedrock_agentcore`) wraps the Strands agent for Runtime hosting — see `app/MyAgent/main.py`. It's a session-isolated microVM per `session_id`, not a shared process.
- This project's session cache is hand-rolled: an LRU cache (128 sessions) keyed by `session_id` in `main.py`, reset on cold start. There's no built-in AgentCore session persistence beyond the Runtime's own microVM isolation — check the `strands-agents-sdk` skill's Session section before assuming otherwise.
- **Memory has a hard 365-day expiry**, schema-enforced, no unlimited option (`@max 365` in the schema). This project deliberately doesn't use AgentCore Memory for that reason — Bedrock Knowledge Base + S3 `.md` files is the permanent store instead (see root `CLAUDE.md`'s Storage section).
- **Build type**: `CodeZip` (default, no Docker) vs `Container` (needs a `Dockerfile`, built in CodeBuild ARM64). This project uses `CodeZip`. Switch only if a dependency needs something CodeZip can't provide.

## Observability: what to actually reach for

Three tools exist. Use the CLI ones for ad-hoc debugging — don't hand-construct `aws logs describe-log-streams`/`get-log-events` calls with manually-built log group/stream paths, which is slow and easy to get wrong (this session did that repeatedly before finding the better path).

- **`agentcore logs --since <time> --query <text> --json`** — the fast path for "what happened recently." `--query` is a naive server-side text filter, not semantic — a query for a tool name can match the system prompt if the prompt happens to mention that tool by name (hit this directly: `--query "write_note"` matched the system prompt text, not just actual tool calls). Narrow with `--since`/`--level` too.
- **`agentcore traces list --json`** then **`agentcore traces get <traceId> --output file.json`** — downloads a full trace as a JSON array of OTel-style spans. Useful for a complete post-hoc read of one specific invocation, but it's the *same underlying log data* as `agentcore logs`, not true structured distributed-tracing spans with semantic tool-call attributes — don't expect `traces get` to hand you "here's exactly what `write_note` returned" any more cleanly than grepping logs would. Spans do carry real OTel GenAI semantic-convention data (`gen_ai.system`, `eventName: gen_ai.system.message`, etc.) — worth a proper look if building tooling against this, but verify the exact tool-call event shape against a real trace before relying on it, don't assume.
- **For actually driving application logic** (e.g. "record which notes got created this turn," not just debugging) — neither of the above is the right tool. Use Strands SDK hooks instead (`AfterToolCallEvent` gives a structured `ToolResult` per tool call, in-process, no log scraping at all). See the `strands-agents-sdk` skill.

## IAM: the sub-resource gotcha (hit 3 times this session)

A policy scoped to a resource's **base ARN** is not enough for actions that operate on a **sub-resource ARN**. This bit the project three separate times with three different services:

1. `bedrock-agentcore:InvokeAgentRuntime` actually operates on `.../runtime-endpoint/DEFAULT`, not the bare runtime ARN.
2. `dynamodb:Query` on a GSI needs the **index's own ARN** (`.../table/X/index/Y`) granted explicitly — the base table ARN alone 403s.
3. Same DynamoDB rule hit again on a second table when adding the Source model.

**Pattern going forward:** whenever granting IAM for a new AWS resource, ask "does this action actually target a sub-resource, not the parent?" *before* deploying and hitting the 403 — check the service's IAM action reference for the resource type each action operates on, don't assume the parent ARN covers it.

## Premade AgentCore capabilities — check before hand-building

Confirmed installed (`bedrock_agentcore` package, `app/MyAgent/.venv/lib/python3.14/site-packages/bedrock_agentcore/`) but **not currently used anywhere in this project** — listed so a future feature checks here before hand-rolling something AWS already ships as a managed sandbox/service:

- **Browser sandbox** (`bedrock_agentcore.tools.browser_client`, `BrowserClient`) — a managed Playwright browser sandbox (start/stop/automate real page interaction, screenshots, JS execution). Directly relevant to `fetch_url`'s current limitation (`docs/review-todo.md` #6/#7): today's `fetch_url` is regex HTML-stripping on whatever `httpx` returns, which can't handle JS-rendered pages. A managed browser sandbox is the AWS-native upgrade path for that, and for the `--research` fan-out's fetch step — before hand-building a headless-browser fetcher, check this first.
- **Code Interpreter sandbox** (`bedrock_agentcore.tools.code_interpreter_client`) — managed sandboxed code execution (start/stop/invoke). No current fit in this project's scope (no code-execution need), but note it exists rather than reaching for a DIY sandbox if one ever comes up (e.g. a future SWOT/analysis agent doing real data crunching).
- **Gateway** (`bedrock_agentcore.gateway`, `GatewayClient`) — federates external tools/APIs behind one MCP-style gateway endpoint, so multiple backend tool sources look like one to the agent. Relevant if this project ever integrates several external APIs and wants one consistent tool-calling surface instead of a growing pile of individual `@tool` functions.
- **Identity** (`bedrock_agentcore.identity.auth`, `requires_access_token` decorator) — real OAuth token retrieval (M2M, user-federation, or on-behalf-of-token-exchange flows) for calling a third-party API on the user's behalf. This project's current auth is a single static API key (see root `CLAUDE.md`'s Frontend section) — Identity is the path to real OAuth if a future integration needs it, not something to build by hand.
- **Memory** — already covered above (hard 365-day cap, deliberately not used).

None of these are wired into `agentcore.json` today (`credentials: []`, `agentCoreGateways: []` are still empty) — they're documented here as available primitives, not a recommendation to adopt them without a concrete need.

## Deploy sequencing

- `agentcore deploy -y` deploys the agent runtime. `npm run deploy:app` / `npm run deploy:api` (from `agentcore/cdk/`) deploy the separate CDK-managed app/API stacks — these are independent deploy targets, not one command.
- **DynamoDB GSI creation is not instant** — even a table with a few dozen items took several minutes to reach `ACTIVE` twice in this session. Deploy the CDK change and start the next *non-dependent* piece of work rather than blocking on the wait.
