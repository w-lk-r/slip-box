"""
Async /ingest worker — invoked directly by Lambda (InvocationType='Event'),
not fronted by API Gateway, so it isn't bound by API Gateway's ~29s
Lambda-proxy integration timeout. Does the one blocking call this project's
ingestion needs: invoke_agent_runtime against the deployed Strands agent, and
waits for it to finish. The agent itself writes notes/edges to S3/DynamoDB via
its own tools — this function does no writes of its own, just invokes and logs.
"""
import json
import logging
import os

import boto3

log = logging.getLogger(__name__)
log.setLevel(logging.INFO)

# Deliberately not importing clients.py: it requires S3_BUCKET/ITEMS_TABLE/
# EDGES_TABLE, which this function's environment doesn't set (least-privilege —
# this worker only ever calls invoke_agent_runtime; the agent's own IAM role
# handles all S3/DynamoDB writes).
AGENT_RUNTIME_ARN = os.environ["AGENT_RUNTIME_ARN"]
REGION = os.environ.get("AWS_REGION", os.environ.get("REGION", "ap-southeast-2"))
agentcore = boto3.client("bedrock-agentcore", region_name=REGION)


def handler(event, context):
    prompt = event["prompt"]
    session_id = event["session_id"]

    log.info(f"Invoking agent for session {session_id}")
    response = agentcore.invoke_agent_runtime(
        agentRuntimeArn=AGENT_RUNTIME_ARN,
        runtimeSessionId=session_id,
        payload=json.dumps({"prompt": prompt}).encode(),
    )

    body = response["response"].read().decode()
    content_type = response.get("contentType", "")
    if "text/event-stream" in content_type:
        text = "\n".join(
            line[len("data: "):] for line in body.splitlines() if line.startswith("data: ")
        )
    else:
        text = body

    log.info(f"Agent finished for session {session_id}: {text[:2000]}")
    return {"session_id": session_id, "status": "complete"}
