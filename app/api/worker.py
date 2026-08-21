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

from clients import AGENT_RUNTIME_ARN, agentcore

log = logging.getLogger(__name__)
log.setLevel(logging.INFO)


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
