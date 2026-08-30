from typing import Any
from collections import OrderedDict

from dotenv import load_dotenv
from bedrock_agentcore.runtime import BedrockAgentCoreApp
from config import SESSION_CACHE_SIZE
from hooks import IngestOutcomeTracker
from agents.ingestion import build_ingestion_agent
from agents.classification import build_classification_agent

load_dotenv()

app = BedrockAgentCoreApp()
log = app.logger

# This file is deliberately just the AgentCore entrypoint: session-cache
# wiring plus dispatch between the two agents (agents/ingestion.py,
# agents/classification.py). Neither agent's system prompt, tools, or
# construction logic lives here — see those two modules for that.


def agent_factory():
    cache = OrderedDict()

    def get_or_create_agent(session_id):
        if session_id in cache:
            cache.move_to_end(session_id)
            return cache[session_id]
        if len(cache) >= SESSION_CACHE_SIZE:
            cache.popitem(last=False)
        cache[session_id] = build_ingestion_agent(hooks=[IngestOutcomeTracker(session_id)])
        return cache[session_id]

    return get_or_create_agent


get_or_create_agent = agent_factory()


def strip_trailing_tool_use(messages: Any) -> list[dict]:
    if not isinstance(messages, list):
        raise ValueError("messages must be a list")
    messages = list(messages)
    while messages:
        last = messages[-1]
        if not isinstance(last, dict):
            raise ValueError("each message must be an object")
        original_content = last.get("content", [])
        if not isinstance(original_content, list) or not all(isinstance(block, dict) for block in original_content):
            raise ValueError("each message content value must be a list of content blocks")
        content = [block for block in original_content if "toolUse" not in block]
        if len(content) == len(original_content):
            break
        if content:
            messages[-1] = {**last, "content": content}
            break
        messages.pop()
    return messages


def _extract_prompt(payload: dict):
    if not isinstance(payload, dict):
        raise ValueError("payload must be a JSON object")
    if "messages" in payload:
        return strip_trailing_tool_use(payload["messages"])
    if "tool_results" in payload:
        tool_results = payload["tool_results"]
        if not isinstance(tool_results, list) or not all(
            isinstance(tr, dict) and isinstance(tr.get("toolUseId"), str)
            for tr in tool_results
        ):
            raise ValueError("tool_results must contain objects with a toolUseId string")
        return [{"role": "user", "content": [{"toolResult": {
            "toolUseId": tr["toolUseId"],
            "status": tr.get("status", "success"),
            "content": tr.get("content", []),
        }} for tr in tool_results]}]
    prompt = payload.get("prompt", "")
    if not isinstance(prompt, str):
        raise ValueError("prompt must be a string")
    return prompt


@app.entrypoint
async def invoke(payload, context):
    session_id = getattr(context, "session_id", "default-session")
    prompt = _extract_prompt(payload)

    if isinstance(payload, dict) and payload.get("mode") == "reclassify":
        log.info("Invoking Slip Box classification agent (reclassification pass)...")
        agent = build_classification_agent(hooks=[IngestOutcomeTracker(session_id)])
    elif isinstance(payload, dict) and payload.get("mode") == "summarize":
        # write_summary is already in the ingestion agent's tools/system prompt
        # (see the SUMMARY CARDS section there) — no separate specialist agent
        # needed here, unlike reclassify. This branch exists purely so the log
        # line doesn't misleadingly say "ingestion agent" for a summarize call.
        log.info("Invoking Slip Box agent (on-demand summarize pass)...")
        agent = get_or_create_agent(session_id)
    else:
        log.info("Invoking Slip Box ingestion agent...")
        agent = get_or_create_agent(session_id)

    async for event in agent.stream_async(prompt):
        if not isinstance(event, dict) or "event" not in event:
            continue
        cbs = event["event"].get("contentBlockStart")
        if cbs is not None and not cbs.get("start"):
            continue
        yield event


if __name__ == "__main__":
    app.run()
