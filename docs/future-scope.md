# Future Scope & Enhancements

Ideas and enhancements explicitly out of scope for the hackathon MVP but worth building after submission.

---

## Obsidian / Local Sync

Notes are already stored as `.md` files in S3 (the Bedrock Knowledge Base document store), so local sync is straightforward — no special export step required.

```bash
aws s3 sync s3://slip-box-notes/ ~/ObsidianVault/SlipBox/
```

**What's built-in:**
- Each ingested item is written as an atomic `.md` file with YAML frontmatter (source, date, confidence scores, relationship metadata)
- S3 sync brings those files into any local vault

**What remains future work:**
- Two-way sync — edits made in Obsidian propagating back to the graph (design notes in `docs/review-todo.md` #10)
- Reconciling notes created directly in the local vault and pushed up via `aws s3 sync`, rather than through the ingestion agent — needs a sidecar/frontmatter backfill and a way to trigger classification after the fact (design notes in `docs/review-todo.md` #9)

---

## S3 Vectors as KB replacement

Amazon S3 Vectors (launched 2025) stores vector embeddings directly in S3 buckets — same bucket, same `.md` files, vectors stored alongside them. Potentially cheaper at scale than Bedrock Knowledge Base, and keeps everything in one place.

The migration path is clean: call the Bedrock Embeddings API on each `write_note`, store the vector in S3 Vectors, query it for semantic search instead of the KB. The `.md` files don't move. Worth revisiting post-hackathon once S3 Vectors matures and pricing is clearer vs the KB.

---

## Instagram / TikTok Reel Ingestion

Support short-form video content as a source type.

- No stable public API and high ToS risk for a publicly-demoed tool
- Manual fallback only for MVP: paste caption/description as plain text
- Revisit if/when stable APIs exist or a self-hosted transcript approach becomes viable

---

## Mobile Capture

Quick-capture from mobile (share sheet, widget, or dedicated app) to send sources to the agent without opening a browser.

---

## Multi-user Support

Currently single-user — one S3 bucket, one KB, no isolation between users.

**Fix:** S3 prefixes per user (`s3://slip-box-notes/{user-id}/`) + `user_id` in each `.md` file's YAML frontmatter + metadata filtering on KB queries at retrieval time. Bedrock Knowledge Bases support metadata filtering natively, so one bucket and one KB can serve multiple users with full retrieval isolation. No per-user infrastructure needed.

Real per-user auth (Cognito or equivalent — user pool, JWT verification, token refresh) arrives together with this, not before it. The FastAPI backend's MVP auth is a single shared static API key precisely because there's only one user; that stops being sufficient the moment this item gets built, not sooner.

## Collaborative Vaults

Multi-user knowledge graphs with shared corpora and per-user pending-edge review queues.

---

## Public Graph Sharing

Read-only shareable links to a subgraph — e.g. share the cluster of notes around a specific concept or research thread.

---

## `--research` fan-out

Moved out of MVP scope entirely 2026-08-30 (previously MVP Scope item 3 in
`CLAUDE.md`) — blocked on picking a real web-search provider (Tavily or Exa
via `strands_tools`), which needs its own API key. Asked the user
2026-08-22, deferred; asked again 2026-08-30 and the user chose to pull the
whole feature out of the critical path rather than leave a blocked item in
the build order. Revisit once a provider is actually chosen — everything
below is ready to build the moment that happens.

**Blocked on a real decision, not a technical gap**: web search needs a real provider (Tavily or Exa via `strands_tools`), and that means an actual API key. Everything below is ready to build the moment a provider is chosen; building the multi-node orchestration before then risks guessing the wrong shape.

**Concrete SDK answer confirmed 2026-08-22** (see `.claude/skills/strands-agents-sdk/SKILL.md`): Strands' `Graph`/`GraphBuilder` (`strands/multiagent/graph.py`) gives deterministic DAG execution with built-in budget controls — `set_max_node_executions`, `set_execution_timeout`, `set_node_timeout`. **Correction, found 2026-08-22 while verifying the real API directly in the installed source (not assumed)**: these controls are *not* what caps "max search queries" or "max sources fetched" — they bound how many times a *node* re-executes and how long it's allowed to take, not how many times a tool gets called *within* one node's own turn. `add_node(executor: AgentBase | MultiAgentBase, ...)` also confirmed each node is a real `Agent` instance, not a plain function. So the per-tool caps below still need their own enforcement, independent of and complementary to `Graph`'s controls, not replaced by them — the original phrasing here conflated the two.

**Recommended node shape**, now that the real API is confirmed: two `Agent` instances wired via `GraphBuilder` — a research node (system prompt scoped to search+fetch+cite; tools: the chosen provider's search tool, the now-hardened `fetch_url` and `search_notes` to check the KB first) feeding into the existing ingestion agent's node for classification/writing, via `add_edge`.

`CLAUDE.md` describes a `--research` path that fans out to a research agent
before classification, but there's no research agent, no outward
search tool, and no budget enforcement. Notes for the build:

**Tools needed**
- Web search (Tavily or Exa via `strands_tools`) — the one remaining
  blocker, above.
- `search_notes` first, always — check the KB before going outward so
  research doesn't re-fetch what's already grounding an existing note.
- `fetch_url` — already hardened: branches by content type, PDF
  read natively, structured `{title, author, text}` for everything else.
  No further work needed here specifically for `--research`.
- A citation/source-resolution tool that resolves or creates the canonical
  `Source` record from fetched metadata — already exists (`_resolve_source`),
  reusable as-is.

**Limiting expansion size — enforced inside the tools, not via `Graph`'s controls (see correction above)**
Don't rely on the system prompt to self-limit tool-call counts, and don't
rely on `Graph`'s node/timeout caps to do this either — they operate at
the wrong granularity. A `ResearchBudget` object created per `--research`
invocation, threaded through the search/fetch tools as shared state (same
closure pattern as the session cache in `main.py`), hard-stopping on:
- max search queries per run (e.g. 3–5)
- max sources fetched per run (e.g. 5–8), chosen from search snippets by
  relevance, not fetched blind
- max chars per fetched source (lower than the current 50k — research
  content competes with the note-writing budget, not just one page)
- a combined character budget across all fetched sources per run, so a
  handful of huge pages can't each spend the full per-source cap
- max new notes written per research fan-out, same shape as the existing
  4+-notes-triggers-a-summary-card cap

`Graph`'s `set_max_node_executions`/`set_execution_timeout`/`set_node_timeout`
are still worth setting too — they're a real, complementary outer bound on
the whole graph run (total wall-clock, runaway re-execution), just not a
substitute for the per-tool caps above.

Once a cap is hit, the tool should return a truncated/"budget exhausted"
result rather than error, so the agent wraps up with what it has instead of
retrying.

**Getting references into expanded notes**
Reuse the `Source`-vertex fix (`docs/review-todo.md` #3) rather than building
something research-specific: every fetched URL resolves to a canonical
`source_id` (deduped, metadata captured at fetch time). Notes written from
research link to it the same way any directly-ingested note would —
`source: [[source-id]]` — using the `RESEARCHED_VIA` edge type already named
in `CLAUDE.md` (`Item → Source`) to keep "the user gave me this" distinct
from "I went and found this."

---

## Luhmann-style keyword index cards

Raised 2026-08-22, not yet scoped or shaped. Luhmann's actual Zettelkasten had a second, separate card index alongside the numbered slip-box itself: a keyword index (`Schlagwortkatalog`) where each keyword card pointed to just one or two *entry-point* note numbers, not an exhaustive list of every note touching that topic — the idea was to jump into the graph at a good starting point and follow connections from there, not get a flat search-result list.

This project's current retrieval primitives don't quite cover that: `tags` frontmatter + KB semantic search (`search_notes`) both give exhaustive/fuzzy retrieval across everything matching, and MOCs (a `PermanentNote` curating `RELATED_TO` links, see `CLAUDE.md`'s Note taxonomy section) are close in spirit but user-authored and note-shaped, not a lightweight keyword→entry-point lookup. Worth thinking about whether a real "index card" primitive earns its place once the graph gets large enough that flat search/tag results stop being the best way in — or whether MOCs already do this job well enough once there are enough of them. No design decision made yet; flagging so the idea doesn't get lost.

---

## Real ingest-completion tracking — RESOLVED 2026-08-22

Built as designed below, using Strands lifecycle hooks instead of log-scraping to get the structured outcome: a `slip-box-ingest-sessions` DynamoDB table (`session_id`, `status: processing|complete|error`, `notes_created`, `skipped_reason`, `error`, TTL-expired after 7 days), seeded `processing` by `WorkerFunction` before it calls `invoke_agent_runtime`, finalized by the agent's own `IngestOutcomeTracker` hook (`app/MyAgent/hooks.py`, subscribes `AfterToolCallEvent`/`AfterInvocationEvent`) when the turn ends — no log parsing anywhere in the path. Exposed via `GET /ingest/{session_id}` (treats a not-yet-seeded record as `processing`, not 404, since the Worker invocation is async). `app/expo/src/lib/pendingIngestions.ts` polls this instead of guessing on a timer; `share.tsx` surfaces the real outcome (which note(s) got created, or why none did) once polling resolves.

Verified live end-to-end both ways: a note-worthy source correctly flips to `complete` with `notes_created` populated; a deliberately off-topic single-mode request correctly flips to `complete` with `notes_created: []` and the agent's own stated reasoning in `skipped_reason`.

<details>
<summary>Original design note (for reference)</summary>

The Expo app's "Generating notes…" placeholder (`app/expo/src/lib/pendingIngestions.ts`) is a client-only, timeout-based best guess — `POST /ingest` returns `202 processing` immediately and there's no way to actually know when a session finished, so the placeholder just clears itself after ~90s or whenever a newer item shows up, whichever comes first. Fine for a solo hackathon MVP, but it's a guess, not a fact.

**Real fix:** a small DynamoDB record per session (`session_id`, `status: processing|complete|error`, timestamps) written by the `WorkerFunction` before/after it calls `invoke_agent_runtime`, exposed via a `GET /ingest/{session_id}` endpoint. The client polls that instead of guessing — the placeholder clears exactly when the backend says the turn is done, not on a timer.

</details>
