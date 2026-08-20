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

## Dependencies

Managed with `uv`. To install: `uv sync`

Runtime deps are in `pyproject.toml`. The `.env` file (gitignored) holds local config — see `.env.sample` for the expected keys. In the cloud, `S3_BUCKET` and `KB_ID` are set via `envVars` in `agentcore.json`; `REGION` comes from `AWS_REGION` automatically.

## Tools

| Tool | Purpose |
|---|---|
| `write_note` | Writes `.md` + `.md.metadata.json` sidecar to S3 |
| `search_notes` | Semantic retrieval against `SlipCaseKB` |
| `trigger_kb_sync` | Starts KB ingestion job so new notes become searchable |
| `fetch_url` | Fetches and strips URL content for ingestion |

Always call `trigger_kb_sync` after one or more `write_note` calls.
