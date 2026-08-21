# Slip Box API

FastAPI backend for Slip Box, deployed as two Lambda functions (`ApiFunction`, `WorkerFunction`) behind API Gateway. See `agentcore/cdk/lib/api-stack.ts` for the infra and root `CLAUDE.md`'s Frontend section for the architecture.

## Local development

```bash
uv sync
cp .env.sample .env   # fill in real values
uv run uvicorn main:app --reload
```

## Deploy

```bash
cd ../../agentcore/cdk && npm run deploy:api
```
