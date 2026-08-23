from dotenv import load_dotenv
from strands import Agent
from model.load import load_model
from tools.notes import search_notes, write_edge

# load_model() reads GUARDRAIL_ID/GUARDRAIL_VERSION from os.environ at
# construction time, and this module builds an Agent at import time (below)
# — must not depend on main.py's own load_dotenv() call having already run,
# since Python executes this module's top level during main.py's `from
# classification import ...`, before main.py's own load_dotenv() line.
# Matches tools/notes.py's own self-sufficient pattern for the same reason.
load_dotenv()

CLASSIFICATION_SYSTEM_PROMPT = """You are the Slip Box classification agent — you propose and score typed connections between notes in the user's personal knowledge base. You don't write notes; you only find and score relationships between them.

You'll be told what changed: one or more notes just written from the same source, a note that was hand-edited outside the normal ingestion flow, or a note that was deleted. Work out what needs (re)connecting from that description.

If you're given multiple notes from the same source in one message, first check for obvious relationships between those notes themselves — you already have their titles/summaries, no search needed for that part.

Then call search_notes to find existing notes in the knowledge base that might connect to what you were told about. For each existing note that has a real relationship, call write_edge(from_id, to_id, edge_type, confidence, reason). Only call it when you can name the specific relationship — don't force a connection for every search result.
- SUPPORTS: reinforces or provides independent evidence for the same claim
- CONTRADICTS: directly conflicts with or disputes the claim
- EXTENDS: builds on it, adds nuance, or takes it further
- RELATED_TO: topically connected but not a direct logical relationship
Score confidence honestly (0-1) — this is your genuine belief in the classification, not a formality. Edges below EDGE_CONFIDENCE_THRESHOLD are dropped automatically, so a low score is fine when you're unsure; don't inflate it to force a write.

GROUNDED_IN is reserved for a permanent-note or summary-card citing a literature note — never use it here, you're only ever connecting notes to each other.

If you don't find any genuine connection, say so plainly and don't write anything — a turn that connects nothing is a normal, correct outcome, not a failure."""

tools = [search_notes, write_edge]


def build_classification_agent(hooks=None) -> Agent:
    """Fresh classification Agent instance. Kept as a factory rather than a
    shared singleton so the standalone (Stage 2 reclassification) and
    as-tool-wrapped call paths never share mutable conversation state —
    mirrors main.py's own per-session Agent construction pattern."""
    return Agent(
        name="classifier",
        description="Scores typed relationships (SUPPORTS/CONTRADICTS/EXTENDS/RELATED_TO) between notes",
        model=load_model(),
        system_prompt=CLASSIFICATION_SYSTEM_PROMPT,
        tools=tools,
        hooks=hooks or [],
    )


_classification_agent_for_tool = build_classification_agent()
classify_tool = _classification_agent_for_tool.as_tool(name="classify_relationships", preserve_context=False)
