---
name: strands-agents-sdk
description: Strands Agents SDK capabilities relevant to this project — lifecycle hooks, structured output, multiagent primitives (Agent-as-Tool, Graph, Swarm), and session persistence. Verified against the actually-installed SDK source, not general training knowledge — this SDK evolves fast, re-check before trusting anything here on a version bump.
license: MIT
---

# Strands Agents SDK — Capabilities Relevant to Slip Box

Verified against the installed source at `app/MyAgent/.venv/lib/python3.14/site-packages/strands/` (v1.52.0 at time of writing, project pins `strands-agents >= 1.15.0` in `pyproject.toml`). **Check the installed version's actual source before trusting any code pattern here** — this project has already been burned twice by assuming stale/general knowledge about fast-moving SDKs instead of reading the real installed source (see `docs/schema-change-checklist.md`, `CLAUDE.md`'s Testing section). Same rule applies here.

## Lifecycle hooks — the fix for "did this turn actually do anything?"

This project currently has no structured way to know whether an ingestion turn wrote a note, and if not, why — that information only exists as text in a CloudWatch log stream (truncated at 2000 chars in the Worker's own log line — see `docs/future-scope.md`'s "Real ingest-completion tracking" item). Hooks solve this in-process, no log scraping:

```python
from strands.hooks import HookProvider, HookRegistry
from strands.hooks.events import AfterToolCallEvent, AfterInvocationEvent

class IngestOutcomeTracker(HookProvider):
    def register_hooks(self, registry: HookRegistry) -> None:
        registry.add_callback(AfterToolCallEvent, self.on_tool_call)
        registry.add_callback(AfterInvocationEvent, self.on_turn_end)

    def on_tool_call(self, event: AfterToolCallEvent) -> None:
        if event.tool_use["name"] == "write_note" and not event.exception:
            # event.result: ToolResult — the actual structured return value
            # of write_note, e.g. {"note_id": ..., "s3_key": ..., "title": ...}
            self.notes_created.append(event.result)

    def on_turn_end(self, event: AfterInvocationEvent) -> None:
        # event.result: AgentResult | None — final message/stop_reason for the whole turn
        ...

agent = Agent(tools=[...], hooks=[IngestOutcomeTracker()])
```

Key event types (`strands/hooks/events.py`): `BeforeInvocationEvent`/`AfterInvocationEvent` (whole turn), `BeforeToolCallEvent`/`AfterToolCallEvent` (per tool call — `tool_use`, `result: ToolResult`, `exception: Exception | None`), `MessageAddedEvent`. `AfterToolCallEvent`/`AfterInvocationEvent` use **reverse callback ordering** (last-registered runs first) — matters if registering more than one hook provider that touches the same event.

**Use this, not `agentcore logs`/`traces`, for anything that needs to drive application logic** (e.g. writing a session-outcome record) — the AgentCore CLI tools are for ad-hoc debugging convenience, not structured data. See the `bedrock-agentcore` skill.

## Structured output — a typed answer instead of parsing text

`Agent.structured_output()` is **deprecated**. Current pattern passes the model into the call (or sets a default at construction):

```python
from pydantic import BaseModel

class IngestOutcome(BaseModel):
    notes_created: list[str]
    skipped_reason: str | None = None

result = agent(prompt, structured_output_model=IngestOutcome)
result.structured_output  # IngestOutcome instance, or None if the model declined
```

`AgentResult` (`strands/agent/agent_result.py`) is what `agent(prompt)` / the final `stream_async` event actually returns:
```python
@dataclass
class AgentResult:
    stop_reason: StopReason
    message: Message
    metrics: EventLoopMetrics
    structured_output: BaseModel | None
    # + state, interrupts, checkpoint
```

Combine with the `AfterToolCallEvent` hook above for a complete, structured picture of a turn — no text-scraping needed anywhere in the pipeline.

## Multiagent primitives — three real options, not one generic "multi-agent" thing

Root `CLAUDE.md` names "Agent-as-Tool, Swarm, A2A" as needing review before building the planned classification/research agent split (`docs/review-todo.md` #7, #8). That review is done — here's the actual shape of each:

- **`Agent.as_tool()`** (`strands/agent/_agent_as_tool.py`) — wraps an `Agent` as a tool another agent can call. First-class method, not a DIY wrapper:
  ```python
  classification_agent = Agent(name="classifier", description="Scores typed relationships between notes")
  classify_tool = classification_agent.as_tool(name="classify_relationships", preserve_context=False)
  ingestion_agent = Agent(tools=[write_note, write_edge, ..., classify_tool])
  ```
  `preserve_context=False` (default) resets the wrapped agent's state before every call — matches "score what I just found" with no cross-call bleed. Also callable standalone (`classification_agent(prompt)`) for the on-demand "what else is this connected to?" case.
  **→ Fit for the classification-agent split (review-todo #8).**

- **`Graph`** (`strands/multiagent/graph.py`, via `GraphBuilder`) — deterministic DAG execution with **built-in budget controls**, not a hand-rolled `ResearchBudget` object:
  ```python
  from strands.multiagent import GraphBuilder

  builder = GraphBuilder()
  builder.add_node(ingestion_agent, "ingest")
  builder.add_node(research_agent, "research")
  builder.add_edge("ingest", "research", condition=needs_research)
  builder.set_max_node_executions(8)     # hard cap on total node runs
  builder.set_execution_timeout(120.0)   # total wall-clock budget (s)
  builder.set_node_timeout(30.0)         # per-node budget (s)
  result = builder.build()(prompt)       # GraphResult
  ```
  **→ Fit for `--research` fan-out (review-todo #7)** — `set_max_node_executions`/`set_execution_timeout`/`set_node_timeout` cover the "max search queries," "max sources fetched," and total-time caps that doc currently sketches as something to build by hand.

- **`Swarm`** (`strands/multiagent/swarm.py`) — autonomous peer collaboration, agents self-organize and hand off with no central control. **Wrong shape for this project** — nothing here needs agents deciding among themselves who acts next; every planned flow (ingest → classify, or ingest → research fan-out) has a known, deterministic structure.

- **A2A** (`strands/multiagent/a2a/`) — cross-process agent-to-agent protocol over HTTP, exposing an agent as an A2A server. **Not relevant** — this project is one AgentCore Runtime, not multiple independently-deployed agent services.

## Session persistence — a real built-in option, not just the hand-rolled LRU cache

`main.py` currently hand-rolls an LRU cache (128 sessions) that resets on every cold start (per root `CLAUDE.md`'s own description of it). `strands/session/` has built-in alternatives:

```python
from strands.session import S3SessionManager

session_manager = S3SessionManager(
    session_id=session_id,
    bucket="slip-box-notes",   # or a dedicated bucket/prefix — avoid mixing with note content
    prefix="agent-sessions/",
    region_name="ap-southeast-2",
)
agent = Agent(session_manager=session_manager, tools=[...])
```
Persists session metadata + per-message history to S3, survives cold starts (the LRU cache doesn't). Other managers in the same module: `FileSessionManager` (local disk — wrong for this stateless Lambda-style runtime), `SnapshotSessionManager` (versioned snapshots + checkpoint/restore — more machinery than this project's single-turn-per-session pattern needs). Worth adopting if cold-start session loss ever actually matters for this project's usage pattern (mostly one-shot ingests, not long multi-turn conversations) — not an obvious win today, but a real option, not a gap.

## Tools

Beyond the `@tool` decorator already used for all 7 of this project's tools (`app/MyAgent/tools/notes.py`): `strands/tools/structured_output/` is what actually powers the `structured_output_model` mechanism above, not a separate thing to adopt. `strands/tools/mcp/`, `tools/loader.py` cover dynamic/MCP tool loading — not relevant, nothing in this project needs tools resolved at runtime rather than statically defined.

## Premade tools (`strands-agents-tools` / `strands_tools`) — check before hand-building

A separate community package (`strands-agents-tools` on PyPI, imports as `strands_tools`) ships a library of ready-made `@tool` functions — **not currently a dependency of this project** (only core `strands-agents` is installed; root `CLAUDE.md`'s "Key Strands tools" section already names two of these aspirationally). Confirmed by installing it into a scratch dir and reading the real package contents (not assumed from memory) — relevant ones for this project's still-unbuilt features:

- **`tavily` / `exa`** — real-time web search + content extraction/crawl tools, wrapping the Tavily and Exa APIs. This is the literal answer to `CLAUDE.md`'s "Web search/fetch (Tavily/Exa via strands_tools) — research fan-out" line and `review-todo.md` #7's "Web search... returning ranked snippets" requirement — don't hand-write a search-API wrapper, use one of these.
- **`http_request`** — HTTP requests with auth/session/metrics handling built in. A more capable base than `fetch_url`'s current bare `httpx` call, if `fetch_url` ever needs auth-aware fetching.
- **`file_read`** — multi-format file reading **with real PDF text extraction** (`.pdf` is a directly supported format, confirmed in its source). Directly relevant to the deferred PDF-ingestion work (`review-todo.md` #3/#6) — check this before adding a PDF-extraction library by hand.
- **`retrieve`** — Bedrock Knowledge Base semantic retrieval. This project already has its own hand-written equivalent (`search_notes` in `tools/notes.py`) — no need to switch, just noted so nobody reaches for both or reinvents it a third time.
- **`handoff_to_user`** — human-in-the-loop handoff. Root `CLAUDE.md`'s tools table already names this ("`handoff_to_user` — confidence-gated human review") but it isn't actually wired into `main.py`'s tool list yet — it's a premade import away, not something to build.
- **`python_repl` / `use_llm` / `think`** — sandboxed Python execution, dynamic sub-LLM instantiation, and a recursive multi-step reasoning tool, respectively. No current fit in this project's scope; noted for completeness.
- **`agent_graph.py` / `graph.py` / `swarm.py` / `workflow.py`** — this package's *own* older multiagent orchestration helpers. **Don't use these** — they predate and are superseded by the core SDK's `strands.multiagent` primitives (`Graph`/`GraphBuilder`, `Swarm`) documented above, which is what `Agent.as_tool()`/`Graph` guidance in this skill already points to. Installing `strands_tools` for search/PDF/handoff tools doesn't mean adopting its orchestration tools too.

Not installed yet — adding it (`uv add strands-agents-tools`) is a real prerequisite before building `--research` fan-out or PDF ingestion, not optional scaffolding.
