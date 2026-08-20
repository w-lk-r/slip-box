from typing import Any
from collections import OrderedDict
import re
import uuid
import json
import datetime
import os

import boto3
import httpx
from dotenv import load_dotenv
from strands import Agent, tool
from strands.agent.conversation_manager.null_conversation_manager import NullConversationManager
from bedrock_agentcore.runtime import BedrockAgentCoreApp
from model.load import load_model

load_dotenv()

app = BedrockAgentCoreApp()
log = app.logger

S3_BUCKET = os.environ["S3_BUCKET"]
KB_ID = os.environ["KB_ID"]
REGION = os.environ.get("AWS_REGION", os.environ.get("REGION", "ap-southeast-2"))

s3 = boto3.client("s3", region_name=REGION)
bedrock_agent = boto3.client("bedrock-agent", region_name=REGION)
bedrock_runtime = boto3.client("bedrock-agent-runtime", region_name=REGION)

SYSTEM_PROMPT = """You are the Slip Box ingestion agent — a Zettelkasten assistant that transforms sources into atomic notes in the user's personal knowledge base.

Your job is to read what the user sends you and decide:

SINGLE IDEA OR SHORT PASSAGE → create one atomic note. Write it in clear prose, capturing the core idea in relation to its source. One idea, one note.

LONGER DOCUMENT WITH MULTIPLE IDEAS → identify the discrete ideas or concepts, create one atomic note per idea, then identify obvious relationships between notes from the same source (SUPPORTS, EXTENDS, RELATED_TO) and note them in your response.

For every note:
- Give it a precise, descriptive title (this becomes the filename — be specific, not generic)
- Write the body as clear prose: the idea, why it matters, relevant context from the source
- Tag it with the key concepts it touches
- Record the source URL if one was provided

After writing notes, always search the knowledge base for related existing notes — there may already be things in the slip case that connect to what was just ingested.

Write precisely. The user should be able to understand the idea from the note alone, without returning to the source."""


def _slugify(title: str) -> str:
    slug = re.sub(r'[^\w\s-]', '', title.lower())
    slug = re.sub(r'[\s_-]+', '-', slug)
    return slug.strip('-')[:60]


@tool
def write_note(title: str, body: str, source_url: str = "", tags: list[str] = []) -> dict:
    """
    Write an atomic literature note to the slip case knowledge base.

    Creates a .md file and .md.metadata.json sidecar in S3. The sidecar keeps
    frontmatter metadata out of the KB embeddings so retrieval stays semantic.
    Call trigger_kb_sync after writing all notes for this ingestion.

    Args:
        title: Precise, descriptive title for the note — becomes the filename
        body: Note body in clear prose, capturing the idea in relation to its source
        source_url: URL or citation for the source material
        tags: Concept tags for the note

    Returns:
        dict with note_id, s3_key, and title
    """
    note_id = f"{_slugify(title)}-{uuid.uuid4().hex[:8]}"
    s3_key = f"{note_id}.md"
    today = datetime.date.today().isoformat()

    tag_lines = "\n".join(f"  - {t}" for t in tags) if tags else "  []"
    md_content = f"""---
title: {title}
note_id: {note_id}
type: literature-note
authored_by: model
source: {source_url}
date: {today}
tags:
{tag_lines}
supports: []
contradicts: []
extends: []
related_to: []
---

{body}
"""

    # Sidecar keeps frontmatter out of KB embeddings — only body gets indexed
    metadata = {
        "note_id": note_id,
        "type": "literature-note",
        "authored_by": "model",
        "source": source_url,
        "date": today,
        "tags": ", ".join(tags),
    }

    s3.put_object(Bucket=S3_BUCKET, Key=s3_key, Body=md_content.encode(), ContentType="text/markdown")
    s3.put_object(Bucket=S3_BUCKET, Key=f"{s3_key}.metadata.json", Body=json.dumps(metadata).encode(), ContentType="application/json")

    log.info(f"Written note: {s3_key}")
    return {"note_id": note_id, "s3_key": s3_key, "title": title}


@tool
def search_notes(query: str) -> list[dict]:
    """
    Search existing notes in the knowledge base for content related to the query.
    Use this after writing notes to find existing slip case entries that may connect.

    Args:
        query: Natural language search query

    Returns:
        List of matching notes with content and relevance score
    """
    response = bedrock_runtime.retrieve(
        knowledgeBaseId=KB_ID,
        retrievalQuery={"text": query},
        retrievalConfiguration={"vectorSearchConfiguration": {"numberOfResults": 5}},
    )
    return [
        {
            "score": r.get("score"),
            "content": r.get("content", {}).get("text", ""),
            "location": r.get("location", {}).get("s3Location", {}).get("uri", ""),
        }
        for r in response.get("retrievalResults", [])
    ]


@tool
def trigger_kb_sync() -> str:
    """
    Trigger a sync of the knowledge base to index newly written notes.
    Always call this after writing one or more notes.

    Returns:
        Ingestion job ID
    """
    sources = bedrock_agent.list_data_sources(knowledgeBaseId=KB_ID)
    data_source_id = sources["dataSourceSummaries"][0]["dataSourceId"]
    response = bedrock_agent.start_ingestion_job(knowledgeBaseId=KB_ID, dataSourceId=data_source_id)
    job_id = response["ingestionJob"]["ingestionJobId"]
    log.info(f"KB sync started: {job_id}")
    return job_id


@tool
def fetch_url(url: str) -> str:
    """
    Fetch the text content of a URL for ingestion.
    Use this when the user provides a URL rather than pasting content directly.

    Args:
        url: The URL to fetch

    Returns:
        Page text content (HTML tags stripped, capped at 50k characters)
    """
    with httpx.Client(follow_redirects=True, timeout=30) as client:
        response = client.get(url, headers={"User-Agent": "SlipBox/1.0"})
        response.raise_for_status()
        text = re.sub(r'<[^>]+>', ' ', response.text)
        text = re.sub(r'\s+', ' ', text).strip()
        return text[:50000]


tools = [write_note, search_notes, trigger_kb_sync, fetch_url]


def agent_factory():
    cache = OrderedDict()

    def get_or_create_agent(session_id):
        if session_id in cache:
            cache.move_to_end(session_id)
            return cache[session_id]
        if len(cache) >= 128:
            cache.popitem(last=False)
        cache[session_id] = Agent(
            model=load_model(),
            system_prompt=SYSTEM_PROMPT,
            tools=tools,
            conversation_manager=NullConversationManager(),
        )
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
    log.info("Invoking Slip Box ingestion agent...")
    session_id = getattr(context, "session_id", "default-session")
    agent = get_or_create_agent(session_id)
    prompt = _extract_prompt(payload)

    async for event in agent.stream_async(prompt):
        if not isinstance(event, dict) or "event" not in event:
            continue
        cbs = event["event"].get("contentBlockStart")
        if cbs is not None and not cbs.get("start"):
            continue
        yield event


if __name__ == "__main__":
    app.run()
