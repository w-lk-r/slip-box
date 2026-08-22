from typing import Any
from collections import OrderedDict

from dotenv import load_dotenv
from strands import Agent
from strands.agent.conversation_manager.null_conversation_manager import NullConversationManager
from bedrock_agentcore.runtime import BedrockAgentCoreApp
from model.load import load_model
from config import SESSION_CACHE_SIZE
from hooks import IngestOutcomeTracker
from tools.notes import write_note, write_edge, search_notes, trigger_kb_sync, fetch_url, write_summary, update_summary

load_dotenv()

app = BedrockAgentCoreApp()
log = app.logger

SYSTEM_PROMPT = """You are the Slip Box ingestion agent — a Zettelkasten assistant that transforms sources into atomic notes in the user's personal knowledge base.

Your job is to read what the user sends you and decide how many notes to create.

If the message includes an explicit instruction about note count (e.g. "Create exactly ONE atomic note..." or "Extract ALL the distinct key ideas..."), follow it exactly — that instruction overrides the default judgment below. Otherwise, decide for yourself:

SINGLE IDEA OR SHORT PASSAGE → create one atomic note. Write it in clear prose, capturing the core idea in relation to its source. One idea, one note.

LONGER DOCUMENT WITH MULTIPLE IDEAS → identify the discrete ideas or concepts, create one atomic note per idea, then identify obvious relationships between notes from the same source and call write_edge for each one.

For every note:
- Give it a precise, descriptive title (this becomes the filename — be specific, not generic)
- Write the body as ONE tight paragraph, roughly 3-6 sentences. Fold in why it matters and relevant context as part of stating the idea itself — don't tack them on as a separate paragraph. If the idea genuinely needs a second paragraph to stand on its own, that's a sign it's two ideas: split it into two notes instead of writing one long note.
- Tag it with the key concepts it touches
- Record the source URL if one was provided, via write_note's source_url param — and if the source material starts with a "Title:"/"Channel:" header (e.g. fetched YouTube content), pass those as source_title/source_author too rather than just repeating them in the note body

After writing notes, always search the knowledge base for related existing notes — there may already be things in the slip case that connect to what was just ingested.

EDGES: For each existing note you find that has a real relationship to one you just wrote, call write_edge(from_id, to_id, edge_type, confidence, reason). Only call it when you can name the specific relationship — don't force a connection for every search result.
- SUPPORTS: reinforces or provides independent evidence for the same claim
- CONTRADICTS: directly conflicts with or disputes the claim
- EXTENDS: builds on it, adds nuance, or takes it further
- RELATED_TO: topically connected but not a direct logical relationship
Score confidence honestly (0-1) — this is your genuine belief in the classification, not a formality. Edges below EDGE_CONFIDENCE_THRESHOLD are dropped automatically, so a low score is fine when you're unsure; don't inflate it to force a write.

SUMMARY CARDS: When searching the knowledge base, pay attention to clusters:
- If you find 4 or more existing notes converging on the same core idea, write a summary card with write_summary, grounding it in those note_ids. The summary card collapses that cluster into a single concept node in the graph.
- If a new note clearly belongs to an existing summary card you found in search results, call update_summary to add it to that cluster instead of creating a new one.
- A note can belong to multiple clusters — call update_summary for each relevant summary card.
- If a user asks you to summarise their notes on a topic, search first, then write a summary card.

Write precisely. The user should be able to understand the idea from the note alone, without returning to the source."""

tools = [write_note, write_edge, write_summary, update_summary, search_notes, trigger_kb_sync, fetch_url]


def agent_factory():
    cache = OrderedDict()

    def get_or_create_agent(session_id):
        if session_id in cache:
            cache.move_to_end(session_id)
            return cache[session_id]
        if len(cache) >= SESSION_CACHE_SIZE:
            cache.popitem(last=False)
        cache[session_id] = Agent(
            model=load_model(),
            system_prompt=SYSTEM_PROMPT,
            tools=tools,
            conversation_manager=NullConversationManager(),
            hooks=[IngestOutcomeTracker(session_id)],
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
