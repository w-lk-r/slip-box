"""
Async /ingest worker — invoked directly by Lambda (InvocationType='Event'),
not fronted by API Gateway, so it isn't bound by API Gateway's ~29s
Lambda-proxy integration timeout. Does the one blocking call this project's
ingestion needs: invoke_agent_runtime against the deployed Strands agent, and
waits for it to finish. The agent itself writes notes/edges to S3/DynamoDB via
its own tools — this function does no writes of its own, just invokes and logs.
"""
import datetime
import json
import logging
import os

import boto3

log = logging.getLogger(__name__)
log.setLevel(logging.INFO)

# Deliberately not importing clients.py: it requires S3_BUCKET/ITEMS_TABLE/
# EDGES_TABLE, which this function's environment doesn't set (least-privilege —
# this worker only ever calls invoke_agent_runtime and seeds ingest-session
# status; the agent's own IAM role handles all S3/items/edges/sources writes).
AGENT_RUNTIME_ARN = os.environ["AGENT_RUNTIME_ARN"]
INGEST_SESSIONS_TABLE = os.environ["INGEST_SESSIONS_TABLE"]
REGION = os.environ.get("AWS_REGION", os.environ.get("REGION", "ap-southeast-2"))
agentcore = boto3.client("bedrock-agentcore", region_name=REGION)
ddb = boto3.resource("dynamodb", region_name=REGION)
ingest_sessions_table = ddb.Table(INGEST_SESSIONS_TABLE)

# Ephemeral status records, not permanent note content — DynamoDB TTL expires
# them automatically rather than needing a cleanup script.
SESSION_TTL_DAYS = 7


def _seed_processing(session_id: str) -> None:
    now = datetime.datetime.now(datetime.timezone.utc)
    ingest_sessions_table.put_item(Item={
        "session_id": session_id,
        "status": "processing",
        "started_at": now.isoformat(),
        "ttl": int((now + datetime.timedelta(days=SESSION_TTL_DAYS)).timestamp()),
    })


def _mark_error(session_id: str, error: str) -> None:
    ingest_sessions_table.update_item(
        Key={"session_id": session_id},
        UpdateExpression="SET #status = :status, #error = :error",
        ExpressionAttributeNames={"#status": "status", "#error": "error"},
        ExpressionAttributeValues={":status": "error", ":error": error},
    )


def handler(event, context):
    prompt = event["prompt"]
    session_id = event["session_id"]

    _seed_processing(session_id)

    agent_payload = {"prompt": prompt}
    if "mode" in event:
        agent_payload["mode"] = event["mode"]

    log.info(f"Invoking agent for session {session_id}")
    try:
        response = agentcore.invoke_agent_runtime(
            agentRuntimeArn=AGENT_RUNTIME_ARN,
            runtimeSessionId=session_id,
            payload=json.dumps(agent_payload).encode(),
        )
    except Exception as e:
        log.exception(f"Agent invocation failed for session {session_id}")
        _mark_error(session_id, str(e))
        raise

    body = response["response"].read().decode()
    content_type = response.get("contentType", "")
    if "text/event-stream" in content_type:
        text = "\n".join(
            line[len("data: "):] for line in body.splitlines() if line.startswith("data: ")
        )
    else:
        text = body

    # Final status (complete + notes_created/skipped_reason) is written by the
    # agent's own IngestOutcomeTracker hook (app/MyAgent/hooks.py), not here —
    # this log line is now a debugging convenience, not the source of truth.
    log.info(f"Agent finished for session {session_id}: {text[:2000]}")
    return {"session_id": session_id, "status": "complete"}
