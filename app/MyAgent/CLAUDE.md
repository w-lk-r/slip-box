# CLAUDE.md — MyAgent

Agent-specific guidance for `app/MyAgent/`. Loaded alongside the root `CLAUDE.md`.

## IAM Permissions

**Never apply IAM changes manually via the AWS console or CLI as a permanent fix.** Manual changes are lost on the next `agentcore deploy`. Any permissions the agent needs must be codified:

- Add a policy JSON file under `app/MyAgent/policies/`
- Reference it in `agentcore.json` under the runtime's `additionalPolicies` array
- The agentcore CLI applies these via CDK on every deploy

**Current policy:** `policies/agent-permissions.json`
- `s3:PutObject`, `s3:GetObject`, `s3:ListBucket` on `slip-box-notes`
- `bedrock-agent-runtime:Retrieve` on `SlipCaseKB`
- `bedrock-agent:StartIngestionJob`, `bedrock-agent:ListDataSources` on `SlipCaseKB`
- `dynamodb:PutItem/GetItem/UpdateItem/DeleteItem/Query/Scan` on `slip-box-items`, `slip-box-edges`, `slip-box-sources`, `slip-box-ingest-sessions`, and their GSIs (`to_id-index`, `source-key-index`)

## Dependencies

Managed with `uv`. To install: `uv sync`

Runtime deps are in `pyproject.toml`. The `.env` file (gitignored) holds local config — see `.env.sample` for the expected keys. In the cloud, `S3_BUCKET` and `KB_ID` are set via `envVars` in `agentcore.json`; `REGION` comes from `AWS_REGION` automatically.

## Testing

`uv run pytest` runs `tests/`. `moto` mocks DynamoDB for anything that touches it (`_resolve_source`) — no real AWS calls, no deploy needed. `tests/conftest.py` sets the env vars `tools/notes.py` reads at import time; add new table/env-var names there too if you add one. See root `CLAUDE.md`'s Testing section for when to add a test vs. just verifying live.

## Tools

| Tool | Purpose |
|---|---|
| `write_note` | Writes `.md` + sidecar to S3, record to DynamoDB `items` |
| `write_edge` | Writes a typed edge to DynamoDB `edges` if confidence ≥ `EDGE_CONFIDENCE_THRESHOLD`; regenerates the source note's frontmatter link list |
| `write_summary` | Writes a `summary-card` note grounding a cluster of note_ids |
| `update_summary` | Adds/removes notes from an existing summary card's cluster |
| `search_notes` | Semantic retrieval against `SlipCaseKB` |
| `trigger_kb_sync` | Starts KB ingestion job so new notes become searchable |
| `fetch_url` | Fetches and strips URL content for ingestion |

Always call `trigger_kb_sync` after one or more `write_note` or `write_summary` calls.

## Hooks

`hooks.py`'s `IngestOutcomeTracker` (Strands `HookProvider`) tracks whether a turn actually created a note, and why not when it didn't — written to `slip-box-ingest-sessions` at `AfterInvocationEvent`, read back via the API's `GET /ingest/{session_id}`. Registered per-session in `main.py`'s `agent_factory()`. Replaces grepping a truncated Worker log line with structured, in-process data.
