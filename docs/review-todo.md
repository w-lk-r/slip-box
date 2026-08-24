# Review TODO — Metadata & Provenance Gaps

Findings from a review of what's actually implemented in `app/MyAgent/` vs. what
`CLAUDE.md` describes. These are cases where the
design treats something as a structured, linkable piece of data, but the code
currently drops it to a flat string, an empty placeholder, or nothing at all.
Ordered by priority.

---

## 1. Relationship edges are never persisted — RESOLVED 2026-08-21

`write_edge` now exists and is deployed; see `docs/build-log.md` Week 3.
Left below for context on what was missing and why. Confidence scoring is
in-agent for now, not a separate classification agent.

The system prompt (`main.py`) tells the ingestion agent to identify
SUPPORTS/EXTENDS/CONTRADICTS/RELATED_TO relationships between notes and "note
them in your response" — but there is no `write_edge` tool. `write_note`
always initializes `supports/contradicts/extends/related_to: []` in
frontmatter and nothing ever populates them. The relationships the agent
finds today live only in the chat transcript and are lost once the
conversation ends.

The classification agent, the `edges` DynamoDB table (`EDGES_TABLE` is
defined in `.env.sample` but referenced nowhere in code), and Neptune are all
designed in `CLAUDE.md` but none exist yet. This is the core feature of the
app and it isn't wired up.

**Fix:** add a classification step/tool that writes `{from_id, to_id, type,
confidence, history}` to the `edges` table, and regenerates the target
note's frontmatter link lists from current edge state (per "Connections live
on the card" in `CLAUDE.md`).

## 2. Confidence scores don't exist — RESOLVED 2026-08-21

Resolved alongside #1 — `write_edge` scores and stores confidence, dropping
below-threshold edges. The "edges near threshold render differently, user
can correct inline" UX is now also built: the Next.js graph view
(`app/web/`) dashes edges below a review-worthy confidence cutoff and
`EdgePanel` lets the user change the type or delete the edge inline — see
`docs/build-log.md` Week 3.

## 3. Source references are a flat, unstructured string — RESOLVED 2026-08-22

Fixed: a `slip-box-sources` DynamoDB table holds a real Source record per
citation (`source_id`, `title`, `author`, `type: web|youtube|pdf`, `url`,
`retrieved_at`), deduped on write via a `source-key-index` GSI keyed on a
normalized URL (YouTube URLs collapse to just the video ID, so different
tracking params on the same video correctly dedupe to one record — a real
case in this corpus). Notes reference it via `source: [[source-id|Title]]`
in frontmatter, same wikilink pattern as edges, instead of a raw string.
`write_note` gained `source_title`/`source_author` params so metadata
already being fetched (e.g. YouTube's oEmbed title/channel) is preserved
structurally instead of only folded into note body text. A `source-index`
GSI on `slip-box-items` answers "everything I've read from X" directly, as
a query rather than a graph traversal — verified live (a source shared by
two notes correctly returns both).

Backfilled all 46 pre-existing items with a `source_url`: 46 items deduped
down to 6 real Source records. See `docs/build-log.md` for the full
implementation notes and the plan file it was built from.

Explicitly deferred, not part of this fix: Source as a graph-visible node
type (`/graph` showing Source nodes, a `RESEARCHED_VIA` edge). PDF ingestion
itself is now built — see #6's update below; it uses exactly the `type:
"pdf"` + content-hash `source_key` shape sketched here.

## 4. `related_to`/`grounded_in` aren't wikilinks

`update_summary` (`tools/notes.py`) writes `grounded_in` as bare `note_id`
strings, not `[[wikilink]]`-style references. This breaks the stated design
goal that frontmatter connections use `[[wikilinks]]` so Obsidian's
graph/backlinks pick them up — right now they won't resolve.

## 5. No `edited_by_user` / edit path for `Item` notes

`CLAUDE.md` calls for `edited_by_user: bool` to flag a model-authored note
that's later hand-edited, but there's no update tool for `Item` notes at all
(only `update_summary` exists for summary cards). The flag has nowhere to be
set.

## 6. `fetch_url` has no content-type handling — RESOLVED 2026-08-22 (all three cases)

First pass added YouTube handling straight to `fetch_url` (`_fetch_youtube` —
`youtube-transcript-api` + oEmbed), which worked from a local dev machine but
failed for real in production: `youtube-transcript-api`'s own docs turned out
to be right that YouTube blanket-blocks the transcript endpoint from cloud
provider IPs, AWS included (confirmed via CloudWatch — the exact `RequestBlocked`
exception the library documents). No proxy signup was wanted for this, so the
transcript fetch moved to where it isn't blocked: the Expo app fetches it
client-side over the phone's own network connection (`app/expo/src/lib/youtube.ts`,
using the `youtube-transcript` npm package — pure `fetch()`-based, no Node
dependency, confirmed RN/Metro-bundle-compatible) before calling `/ingest`.

This needed a small API contract addition since `text`/`url` were previously
mutually exclusive with no way to attribute a client-fetched transcript to its
real source: `IngestRequest` gained an optional `source_url` field, valid only
alongside `text`, which `_build_prompt` (`app/api/routers/ingest.py`) turns
into an instruction telling the agent to pass it straight to `write_note`
rather than re-fetch it. `fetch_url`'s own YouTube handling stays in place as
a fallback for any non-mobile ingestion path, and as what a share still
degrades to if the client-side fetch itself fails. Verified end-to-end against
the live deployed stack in both directions — see `docs/build-log.md`.

PDF is now handled — RESOLVED 2026-08-22, but via a separate upload path,
not `fetch_url`: a web upload page (`app/web/app/upload/page.tsx`) presigns
direct-to-S3 PUTs into a new `slip-box-uploads` bucket, then `POST /ingest`
with a `pdf_key` tells the agent to call the new `read_pdf` tool, which
downloads the object and returns it as a Bedrock **document content block**
(`ToolResultContent`'s native `document` key) — the model reads the PDF
natively (text, tables, layout), no separate Python text-extraction library.
Source dedup uses the S3 object's ETag (the MD5 of its bytes for a
non-multipart PUT) as a content hash, not the S3 key itself, since every
upload gets a fresh key — verified live that two uploads of the
byte-identical PDF under different keys correctly resolve to the same
`Source` record. Mobile share-sheet PDF support was explicitly scoped out
of this pass — `app.json`'s iOS activation rules only allow text/URL today,
adding files needs a native config-plugin change plus a fresh `eas build`.
No page-count/file-size cap yet — a large-enough PDF will hit Bedrock's own
document-size limits and just fail; worth a simple upload-size guardrail
before this is used on anything book-length.

**`fetch_url`'s own remaining gap (a URL that points directly at a PDF, or
a plain web page with no citation metadata) — RESOLVED 2026-08-22.**
`fetch_url` now returns structured `{title, author, text}` for HTML pages
(extracting `<title>` and an author meta/OG tag — previously nothing did
this at all, a citation was always just the bare URL) and, for a URL whose
`content-type` or extension says PDF, the same Bedrock document-block
shape `read_pdf` already uses — `httpx` GET the bytes directly, no S3
round-trip needed since there's no pre-staging step in the fetch-a-URL
case. YouTube's existing transcript/oEmbed handling returns the same
`{title, author, text}` shape now too, instead of prepending a literal
`"Title: X\nChannel: Y"` header into the text and relying on the system
prompt to notice it — removed that convention for anything going through
`fetch_url` itself. It's still needed for one path: the Expo app's
client-side YouTube fetch (`app/expo/src/lib/youtube.ts`) sends plain
`text` with that same header baked in client-side, since there's no
structured slot for title/author in the `text`+`source_url` ingest shape —
the system prompt keeps both instructions side by side rather than
regressing that path.

**Live verification of the above, 2026-08-23, surfaced two more real bugs — both found, fixed, and re-verified live.**

1. **PDF document name could contain characters Bedrock rejects, crashing the whole turn.** Ingesting `https://arxiv.org/pdf/1706.03762` (arXiv serves PDFs with no `.pdf` suffix at all) produced document name `"1706.03762"` — a period, which Bedrock's document content block disallows (only alphanumeric, whitespace, hyphens, parens, brackets). `ConverseStream` threw an unhandled `ValidationException`, killing the entire model turn, not just a tool call. Same latent bug existed in `read_pdf`'s upload path too: `os.path.splitext(filename)[0]` only strips the *last* extension, so any real-world filename with an internal period or underscore (`"notes.v2.pdf"`, `"draft_final.pdf"` — both common) would hit the same crash. Fixed with a shared `_sanitize_document_name` helper (`tools/notes.py`) applied to both `read_pdf` and `fetch_url`'s PDF branch — strips disallowed characters, collapses whitespace, falls back to `"document"` if nothing survives. Re-verified live: the same arXiv URL now correctly ingests as one note citing "Attention Is All You Need" (the real title, read natively off the PDF, not the URL slug).
2. **A crashed turn was recorded as a clean completion.** The `ValidationException` above also exposed a real gap in `hooks.py`'s `IngestOutcomeTracker`: `AfterInvocationEvent` fires "regardless of whether it completed successfully or encountered an error" (Strands' own docstring) but carries no exception field — `result` is `None` on the error path, and the old code did `event.result.message if event.result else None`, which silently wrote `status: "complete"`, `notes_created: []`, `skipped_reason: ""` for a turn that had actually crashed. Indistinguishable from the agent legitimately deciding there was nothing to write — exactly the ambiguity this tracker was built to eliminate (see Week 3's ingest-outcome-tracking entry in `docs/build-log.md`). Fixed: `_on_turn_end` now checks `event.result is None` first and writes `status: "error"` with a pointer to check the runtime logs for that `session_id`, matching `worker.py`'s existing `status: "error"` pattern for its own failure path. Covered by a new unit test constructing a real `AfterInvocationEvent(result=None)` — the actual crash-detection logic, not LLM judgment, so this stays in the automated suite rather than a live-only check.

Also confirmed live, not a bug: a YouTube URL with no transcript available (blocked by YouTube's cloud-IP ban, same known constraint documented above) correctly fell back to title/channel-only, and the agent reasonably declined to write a content-free note rather than hallucinating one.

## 7. Research agent (`--research` fan-out) doesn't exist yet — design notes for when it's built

**Blocked on a real decision, not a technical gap**: web search needs a real provider (Tavily or Exa via `strands_tools`), and that means an actual API key — asked the user 2026-08-22, deferred ("not sure yet"). Everything below is ready to build the moment a provider is chosen; building the multi-node orchestration before then risks guessing the wrong shape.

**Concrete SDK answer confirmed 2026-08-22** (see `.claude/skills/strands-agents-sdk/SKILL.md`): Strands' `Graph`/`GraphBuilder` (`strands/multiagent/graph.py`) gives deterministic DAG execution with built-in budget controls — `set_max_node_executions`, `set_execution_timeout`, `set_node_timeout`. **Correction, found 2026-08-22 while verifying the real API directly in the installed source (not assumed)**: these controls are *not* what caps "max search queries" or "max sources fetched" — they bound how many times a *node* re-executes and how long it's allowed to take, not how many times a tool gets called *within* one node's own turn. `add_node(executor: AgentBase | MultiAgentBase, ...)` also confirmed each node is a real `Agent` instance, not a plain function. So the per-tool caps below still need their own enforcement, independent of and complementary to `Graph`'s controls, not replaced by them — the original phrasing here conflated the two.

**Recommended node shape**, now that the real API is confirmed: two `Agent` instances wired via `GraphBuilder` — a research node (system prompt scoped to search+fetch+cite; tools: the chosen provider's search tool, the now-hardened `fetch_url` — see #6, resolved 2026-08-22 — and `search_notes` to check the KB first) feeding into the existing ingestion agent's node for classification/writing, via `add_edge`.

`CLAUDE.md` describes a `--research` path that fans out to a research agent
before classification, but there's no research agent, no outward
search tool, and no budget enforcement. Notes for the build:

**Tools needed**
- Web search (Tavily or Exa via `strands_tools`) — the one remaining
  blocker, above.
- `search_notes` first, always — check the KB before going outward so
  research doesn't re-fetch what's already grounding an existing note.
- `fetch_url` — already hardened (see #6): branches by content type, PDF
  read natively, structured `{title, author, text}` for everything else.
  No further work needed here specifically for `--research`.
- A citation/source-resolution tool that resolves or creates the canonical
  `Source` record from fetched metadata — already exists (`_resolve_source`,
  built for #3), reusable as-is.

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
Reuse the `Source`-vertex fix from #3 rather than building something
research-specific: every fetched URL resolves to a canonical `source_id`
(deduped, metadata captured at fetch time). Notes written from research link
to it the same way any directly-ingested note would —
`source: [[source-id]]` — using the `RESEARCHED_VIA` edge type already named
in `CLAUDE.md` (`Item → Source`) to keep "the user gave me this" distinct
from "I went and found this."

## 8. Multi-agent split shouldn't be a routing supervisor — dispatch by endpoint instead — RESOLVED 2026-08-23

**Built and live-verified 2026-08-23.** New `app/MyAgent/classification.py`: a separate `Agent` ("classifier") whose only tools are `search_notes` and `write_edge` — it doesn't have `write_note`/`write_summary` at all, so "don't create notes, only score connections" is structural, not a prompt-level request. `write_edge` moved off the ingestion agent's tool list entirely; all edge-writing (same-source sibling connections *and* cross-corpus connections) now goes through it.

Used both ways `Agent.as_tool()` is designed for:
- **As a tool**: wrapped once at import time via `.as_tool(name="classify_relationships", preserve_context=False)` and added to the ingestion agent's tool list. After writing note(s), the ingestion agent calls it exactly once per source, passing a text description of every note it just wrote (id, title, one-line summary) — the classification agent checks those for same-source relationships itself, then calls `search_notes` on its own to find cross-corpus connections, then `write_edge`s anything genuine.
- **Standalone**: `main.py`'s entrypoint gained an explicit `mode` field on the invoke payload — `"reclassify"` routes straight to a freshly-built classification agent instead of the ingestion agent, a real `if` in Python rather than the LLM parsing prompt text to decide its own behavior (applying this item's own stated principle — "shouldn't be an LLM router" — to Stage 2's dispatch, not just the ingest-endpoint dispatch this item originally scoped). `reconciler.py`'s `_trigger_stage2` (review-todo #9) sets `mode: "reclassify"` and dropped the old "do NOT call write_note or write_summary" prompt language entirely — no longer needed as a request since the classification agent structurally can't. `worker.py` forwards `mode` through untouched when present.

`search_notes` deliberately stays on *both* agents — the classification agent uses it for connection-finding, the ingestion agent keeps its own separate call for summary-card cluster detection ("4+ notes converge → write_summary"), which stayed on the ingestion agent per `CLAUDE.md`'s four-agent table and is unrelated to edge-scoring. That's one extra KB query per ingest turn, an explicit accepted tradeoff for keeping the split clean rather than threading search results back out of the sub-agent call.

`write_summary`/`update_summary`'s own `GROUNDED_IN` edges are unaffected — they already call the internal `_write_edge_record` helper directly, never the `@tool`-decorated `write_edge`, so removing `write_edge` from the ingestion agent's tools didn't touch that path. Confirmed via `grep` before building, not assumed.

Live-verified both paths against the real deployed stack: a real multi-idea ingest (LRU/FIFO cache eviction) correctly called `classify_relationships` exactly once with all 3 new notes described together, which connected the two algorithm notes to each other (`RELATED_TO`, confidence 0.88), the synthesis note to both siblings (`EXTENDS`, 0.92–0.93), and — via its own `search_notes` call — found a genuine unrelated-topic connection to an existing corpus note (0.72 `RELATED_TO`, to a Zettelkasten-design note, an honestly low-but-real score, not forced). Separately, hand-editing a note's body directly in S3 correctly fired Stage 2 with `mode: reclassify`, confirmed via CloudWatch that this dispatched to the classification agent (not the ingestion agent — log line: "Invoking Slip Box classification agent (reclassification pass)..."), and it correctly declined to force any new connection since the genuinely related notes were already linked and the rest of the corpus wasn't actually about caching — `slip-box-ingest-sessions` recorded `notes_created: []` with real classification reasoning as `skipped_reason`, exactly matching the outcome-tracking shape Stage 2 already relied on before this change.

Two real bugs caught and fixed along the way (unrelated to the SDK composition itself, but blocking verification of it):
- `classification.py`'s module-level `Agent` construction called `load_model()` (reads `GUARDRAIL_ID`/`GUARDRAIL_VERSION` from `os.environ`) at import time, but `main.py` imports `classification` *before* its own `load_dotenv()` call runs — broke local dev. Fixed by having `classification.py` call `load_dotenv()` itself at its own top, matching `tools/notes.py`'s existing self-sufficient pattern (each module that reads env vars at import time loads its own `.env`, doesn't rely on import order elsewhere).
- A pre-existing (though only 1-day-old, from this session's own `test_ingest_prompt.py`) test-isolation bug: `test_ingest_prompt.py` imported `routers.ingest` at module level, unmocked — since that transitively imports `clients.py`'s module-level boto3 objects, and Python caches module imports, this being the alphabetically-first unmocked import poisoned every other test file's own `mock_aws()`-wrapped import for the rest of the `uv run pytest` session (28 of 50 tests failing with real `UnrecognizedClientException` errors). An earlier `git stash` comparison this session had wrongly concluded this was pre-existing/unrelated — flawed, because `stash` without `-u` leaves untracked files in place, and `test_ingest_prompt.py` was untracked at the time, so it silently poisoned both sides of that comparison. Fixed by wrapping the import in `mock_aws()`, matching `test_ingest_status.py`'s existing pattern; found and fixed the same latent issue in `test_uploads.py` while at it, since it had the identical unmocked module-level `from main import app` pattern. `uv run pytest -q` (bare, no arguments) now passes cleanly end to end — 50/50, not just when the right files happen to be listed together.

**Concrete SDK answer confirmed 2026-08-22** (see `.claude/skills/strands-agents-sdk/SKILL.md`): `Agent.as_tool(name=..., preserve_context=False)` (`strands/agent/_agent_as_tool.py`) wraps a classification `Agent` as a first-class tool the ingestion agent can call — `preserve_context=False` resets the wrapped agent's state per call, matching "score what I just found" with no cross-call bleed, and it's also callable standalone for the on-demand "what else is this connected to?" case. Fits the split described below directly; no custom wrapper needed.

`CLAUDE.md`'s four-agent table (Ingestion / Classification / Research /
SWOT) implies something needs to decide which agent handles a request. It
shouldn't be an LLM router: the MVP UI (`Ingest` / `Pending edge review` /
`Graph view` screens, `/ingest`, `/pending-edges`, `/edges/{id}`, `/graph`)
already disambiguates intent at the FastAPI-route level, so an LLM
re-deciding "which agent should handle this" on top of that is redundant
latency, cost, and a new misrouting failure mode for zero benefit.

Map dispatch directly to call sites instead of routing through a supervisor:
- `POST /ingest` (with an explicit `research: bool` from the UI, not
  inferred by an agent) → ingestion agent directly.
- "Find more connections" button on a `PermanentNote` → classification agent
  directly.
- 4+ notes converge in `search_notes` results → **not an agent decision at
  all**, just a count check in the ingestion flow that calls `write_summary`
  (`if len(matches) >= 4`).
- On-demand "summarise my notes on X" → summary agent directly, if it's its
  own UI action rather than free text.

The one place a routing supervisor would still earn its keep is a genuine
free-text omnibox (paste a URL, ask a question, request a summary, all in
one box with no UI pre-categorization) — none of the three MVP screens
obviously have one; confirm with whoever owns the frontend before building
a router for a case that may not exist.

Separately, "specific agent entry points" has a deployment-shape question to
settle before building: separate system prompts sharing one AgentCore
Runtime entrypoint (current shape — cheap, one deploy, shared session
cache) vs. actually separate AgentCore-hosted agents per flow (`agentcore
add agent` per route — matches the "four separate Strands agents" framing
literally, isolates blast radius/scaling/cost per flow, but means N cold
starts and N deploy surfaces instead of one).

**This deployment-shape question is still open — not resolved by the 2026-08-23 build above.** Both the ingestion and classification agents run inside the same shared AgentCore Runtime process/entrypoint today; the split built is a composition change (two `Agent` objects, `Agent.as_tool()` wiring, payload-level `mode` dispatch), not a change to how many Runtime resources are deployed. Worth revisiting once/if `--research` (`#7`) adds a third agent to the mix — three agents sharing one entrypoint is a different cost/blast-radius tradeoff than two.

**On-demand summarize — RESOLVED 2026-08-23, matching the dispatch prediction above exactly.** Built as `POST /summarize` → `mode: "summarize"` on the same `main.py` payload-dispatch mechanism (a real UI action — multi-select notes, "Summarize these" — not a free-text omnibox), reusing the default agent rather than a third specialist since `write_summary`/`update_summary` were already on its tool list. See `docs/build-log.md`'s "On-demand summarize" entry for the full build.

## 9. DynamoDB has no reconciliation path for edits made directly in S3/KB — Stage 1 + Stage 2 RESOLVED 2026-08-22, staging bucket still open

**Flagged next up 2026-08-22** — reprioritized ahead of #7 (`--research` fan-out) and #8 (classification split). The remaining Lambda half below has been sitting as "not urgent, no trigger yet" since the clobber-bug fix, but every schema-touching feature landed since (Source model, ingest-outcome tracking, PDF ingestion, Guardrails) has widened the surface for DynamoDB/S3 to drift — worth closing this gap while the schema is still relatively simple rather than letting more features stack on top of a known-inconsistent read path.

`update_summary`'s clobber bug is fixed: it now reuses `write_edge`'s
`_parse_frontmatter`/`_render_frontmatter` helpers to regenerate frontmatter
from the current **S3** copy, only touching `grounded_in`, instead of
rebuilding `title`/`tags`/`date` from the (possibly stale) DynamoDB item.
Verified against a real summary card — hand-edited its title directly in
S3, called `update_summary`, confirmed the hand-edit survived (it would
previously have been silently reverted to DynamoDB's value).

The broader reconciliation gap below is still open — DynamoDB `items` is
only ever written by `write_note` and `update_summary`, so any edit made
outside those two tools (Obsidian sync after `aws s3 sync`, a direct S3
edit, a future FastAPI edit endpoint) is still invisible to DynamoDB. That
half needs the S3 Event Notification → Lambda described below.

Same root cause also means KB reindexing is manual-only (`trigger_kb_sync`
is an agent `@tool`, not an S3 event trigger, so direct content edits sit
unindexed until something remembers to resync) and note renames orphan
`s3_key` in DynamoDB (no rename detection).

This sharpens what `docs/future-scope.md` already flags at a high level
("Two-way sync — edits made in Obsidian propagating back to the graph" is
listed as future work) — the gap isn't just missing two-way sync, the
current code actively fights a one-off S3 edit even without Obsidian in the
picture.

**Combined design, worked out 2026-08-22 — also covers the brand-new
outside-created-note case (previously its own item, now folded in here).**
Two stages, split by whether an LLM is actually needed — Stage 1 owns the
hard consistency guarantee unconditionally; Stage 2 is optional,
best-effort semantic reconciliation layered on top.

**Stage 1 — deterministic, no agent, must never depend on model judgment
succeeding.** S3 event notification (suffix-filtered to `.md`, so the
`.md.metadata.json` sidecar is excluded) → Lambda, fired on both
`ObjectCreated` and `ObjectRemoved`:
- **`ObjectCreated`/modified:** parse frontmatter, upsert the DynamoDB row,
  keyed on the frontmatter's `note_id` field (not the S3 object key) so
  renames self-heal instead of orphaning. If `note_id` is missing entirely
  (a note created outside the system entirely, e.g. via Obsidian sync),
  generate one the same way `write_note` does
  (`{_slugify(title)}-{uuid8}`), rewrite the file's frontmatter with it,
  and backfill other missing required fields with sane defaults (empty
  typed-link lists, `type: literature-note` if unspecified,
  `authored_by: user`) plus a freshly-generated `.md.metadata.json`
  sidecar — all still cheap and deterministic.
- **`ObjectRemoved`:** full three-direction cleanup, not just deleting the
  `items` row — this project got bitten by exactly this gap twice this
  session, hand-cleaning up test notes (see
  `docs/schema-change-checklist.md`'s three-direction rule): delete
  outgoing edges (`from_id` query), delete incoming edges (`to_id-index`
  query), and remove the note from any summary card's `grounded_in` list
  (regenerating that card's frontmatter). Skipping any of the three leaves
  a dangling reference that crashes the graph view's force-simulation on
  load.
- Keyed decision, cheap to compute: only mark a note as needing Stage 2
  (below) when its **body** actually changed — a content-hash comparison
  against the previous S3 version — not on a frontmatter-only edit (tags,
  a typo fix). Otherwise every trivial hand-edit burns a full model
  invocation for no reason.
- Fail soft on malformed frontmatter (log + skip) rather than crash, since
  manual edits will eventually have YAML typos.
- Keep decoupled from KB reindexing — reconciling a DynamoDB row is cheap
  and can fire per-object, but starting a Bedrock ingestion job is
  batched/non-trivial-cost and shouldn't fire on every single write; keep
  `trigger_kb_sync` on its own (debounced or explicit) cadence.
- New infra in the `agentcore/cdk/` app stack (`SlipBox-App-*`), not the
  agent's `agentcore.json` policies.

**Stage 2 — agent-triggered, optional/best-effort, only when Stage 1 flags
it.** Fires an async call into the *same* invocation path `POST /ingest`'s
`WorkerFunction` already uses (`invoke_agent_runtime`), with a prompt
scoped to reconciliation rather than fresh ingestion — e.g. "note
`{note_id}`'s content changed outside the normal flow — search the KB and
check whether its connections still make sense; propose corrections if
not," skipping `write_note` entirely. Reuses the agent's existing
`search_notes` → `write_edge` loop, confidence-gated exactly like every
other edge write — "if and only if needed" falls directly out of the
existing threshold rather than needing new logic. Deliberately **not**
wired into Stage 1's own core guarantee: if Stage 2 never runs (guardrail
false positive, model error, budget skip), DynamoDB is still correct —
only the semantic reclassification is missed, not the sync itself.
- **Delete case, same mechanism, opt-in trigger:** when Stage 1 processes
  an `ObjectRemoved` for a note that had direct edges, capture its former
  neighbor `note_id`s *before* deleting those edges, and optionally fire a
  Stage 2 review asking whether the former neighbors now warrant a direct
  connection to each other. This is **not** automatic transitive
  reattachment (A–B–C does not imply A–C — edge types aren't transitive,
  and deletion is often a deliberate signal the user doesn't want that
  connection anymore) — it's the agent independently re-deriving a
  relationship via its normal `search_notes`/confidence-gate judgment,
  same as any other reclassification.
- **Why route through the FastAPI worker rather than a bespoke
  Lambda→agent call:** invoke asynchronously, don't block on the LLM, IAM
  scoped narrowly to just `InvokeAgentRuntime` — exactly what
  `WorkerFunction` (`app/api/worker.py`) already is. No new pattern, just
  a new caller and prompt template. New plumbing needed: the
  reconciliation Lambda needs `lambda:InvokeFunction` on `WorkerFunction`,
  the same grant `ApiFunction` already has.

**Two alternatives considered and deliberately not adopted:**
- **DynamoDB as source of truth, S3 derived from it** — doesn't actually
  avoid the reconciliation problem, just relocates the clobber risk to the
  side that matters more: this product's core premise is notes as
  portable, human-editable files (`aws s3 sync` to Obsidian), so making
  the file a regenerated artifact risks silently overwriting a human edit
  the same way `update_summary`'s now-fixed clobber bug did to
  frontmatter. Also moot regardless — the Bedrock KB only embeds from S3,
  so the file has to exist no matter which store is "authoritative."
- **DynamoDB Streams → Lambda → S3 for the agent's own writes** (mirroring
  Stage 1 in the other direction) — not adopted, because the agent
  routinely writes several related notes/edges in one turn, and two call
  sites depend on reading DynamoDB back *within that same turn*:
  `_regenerate_note_links`'s title lookup (a same-batch cross-reference
  would resolve to a stale/missing title) and `_resolve_source`'s dedup
  check (a same-batch duplicate source citation would create a redundant
  Source record instead of deduping — the exact bug class already fixed
  once in the Source model build). The agent's tools keep writing S3 and
  DynamoDB directly, synchronously, as they do today; only S3-originated
  changes (human edits, anything outside the agent's own tools) go
  through Stage 1.

**Stage 1 built and live-verified 2026-08-22.** Lives in `app/api/reconciler.py`
— reuses `linkgen.py`'s `parse_frontmatter`/`render_frontmatter`/
`regenerate_note_links` directly (zero duplication: `linkgen.py`'s own
docstring had already named this Lambda as the anticipated third consumer
that would justify extraction, but since the reconciler lives in the same
`app/api/` deployable unit, no extraction was needed at all — just import
it). CDK: a new `ReconcilerFunction` in `api-stack.ts`, wired to
`NotesBucket` (owned by `AppStack`) via `s3.Bucket.fromBucketName(...)` +
`addEventNotification` rather than a cross-stack export — confirmed via a
direct synth that this correctly generates a `Custom::S3BucketNotifications`
resource with `Managed: false`, which CDK's own handler merges across
stacks rather than blindly overwriting (softer than originally assumed —
"whichever deploys last wins" isn't quite right; CDK actually tracks and
merges per-stack notification entries safely).

**Real bug caught in live verification, not by the test suite**:
`regenerate_note_links` (called from Stage 1's own delete-cleanup, and
separately from the agent's `write_edge`/`update_summary`) rewrites a
note's file to S3 — which re-triggers Stage 1's own upsert handler on that
same key. The first implementation used a full `put_item` there, which
silently wiped attributes Stage 1 doesn't manage (`grounded_in`, caught
directly in a live delete test against a real summary card) on that
redundant re-trigger. Fixed by switching to a partial `update_item` (SET
only the fields Stage 1 actually owns), making the self-retrigger
idempotent instead of destructive — and added a regression test
(`test_reupsert_preserves_attributes_it_doesnt_manage`) that reproduces
this exact scenario, since the original test suite never simulated a
same-key re-trigger and wouldn't have caught it.

Also hit, unrelated: a new Lambda importing `linkgen.py` transitively
imports `clients.py`, which reads *every* env var it needs unconditionally
at module import time — so `ReconcilerFunction` needed all of
`clients.py`'s required env vars set (`SOURCES_TABLE`,
`INGEST_SESSIONS_TABLE`, `UPLOADS_BUCKET`, `AGENT_RUNTIME_ARN`), not just
the three `reconciler.py` itself reads. `worker.py`'s own docstring had
already flagged this exact tradeoff as the reason it avoids importing
`clients.py` at all — the reconciler couldn't take that path since it
needs `linkgen.py`, so it just accepts the fuller env var list instead.

Live-verified: a real hand-edit (tags changed, `created_at` preserved); a
real rename (same `note_id`, new key, one row not two); a real delete with
both outgoing and incoming edges plus a summary card grounding the deleted
note (all three cleanup directions confirmed, including the `grounded_in`
fix above); a real missing-`note_id` note (hand-written, no frontmatter
delimiters even) correctly backfilled, rewritten, sidecar generated, and
reachable via `GET /items/{note_id}`. All test data cleaned up afterward.

**Stage 2 built and live-verified 2026-08-22.** Body-diff gate: a
`body_hash` (SHA-256 of the parsed body) added to Stage 1's own managed
fields, compared against the previous value — fires only when a *previous*
hash existed and differs, which naturally excludes the agent's own fresh
`write_note` creates (already classified synchronously in that same turn)
and skips frontmatter-only edits (tags, a typo). Trigger: `reconciler.py`'s
`_trigger_stage2` invokes `WorkerFunction` exactly as `POST /ingest`
already does (`InvocationType='Event'`), which means ingest-outcome
tracking (`slip-box-ingest-sessions`, `GET /ingest/{session_id}`) covers
Stage 2 sessions for free — zero new code needed there. System prompt
(`app/MyAgent/main.py`) gained one new paragraph: the existing "explicit
instruction overrides default judgment" mechanism only covered note
*count* (single/all/auto), not "create nothing, only search and link," so
a dedicated `RECLASSIFICATION PASS` directive was added rather than
stretching that mechanism to cover a case it wasn't built for.

Delete-neighbor review (opt-in, only when ≥2 neighbors): neighbors are
collected from *both* directions — targets of the deleted note's own
outgoing edges, and sources of its incoming edges — not automatic
transitive reattachment (A–B–C still does not imply A–C); the agent
re-derives any connection on its own merits via `search_notes`, same
confidence gate as anything else.

Live-verified both trigger paths end-to-end: a real body-changing hand-edit
correctly fired a Stage 2 session that skipped note creation
(`notes_created: []`), found a genuine existing corpus note via semantic
search, and wrote a real `RELATED_TO` edge at confidence 0.78; a
tags-only edit on the same note correctly did *not* fire a new session; a
real delete of a note with two real neighbors correctly fired a session
naming both — the agent correctly declined to force a connection when it
couldn't verify one (the test notes hadn't been through `trigger_kb_sync`
yet, so they weren't in the semantic index), which is the intended
"if and only if needed" behavior, not a bug. Caught one real gap in the
process: `reconciler.py`'s logger never had its level set, so none of its
`log.info` calls reached CloudWatch at all (Lambda's default root logger
level is WARNING) — verification had to read DynamoDB directly instead of
the logs that were supposed to show it; fixed with `log.setLevel(logging.INFO)`,
matching the pattern `worker.py` already used.

**Second real gap found 2026-08-23, this time during cleanup after the guardrail investigation below**: bulk-deleting 34 interconnected test notes from S3 at once left 10 of them stuck in DynamoDB — their `.md` files were gone from S3 but their `items` rows survived. Root cause: `_handle_delete`'s per-neighbor loop called `regenerate_note_links(from_id)` unguarded; when a neighbor's own S3 file was *also* mid-deletion in the same batch, that call raised an unhandled `AccessDenied` (S3's standard response for `GetObject` on a missing key when the caller lacks `ListBucket` — not a real permissions bug, just S3 declining to confirm non-existence) that propagated out of the handler *before* it reached `items_table.delete_item` for the note the event was actually about. A best-effort step (regenerating a neighbor's frontmatter) was able to block Stage 1's own unconditional guarantee for the note being deleted. Not just a theoretical scenario — this can happen for real whenever several connected notes get removed together (`aws s3 sync --delete` on a folder, or fast manual deletes of related notes in Obsidian). Fixed by wrapping the per-neighbor block in `try`/`except`, logging and continuing on failure rather than aborting — the neighbor's frontmatter staying stale until the next edge write touches it is an acceptable best-effort miss; the deleted note's own row staying orphaned in DynamoDB is not, since that's the exact drift Stage 1 exists to prevent. Regression test in `app/api/tests/test_reconciler.py::TestHandleDelete::test_neighbor_regeneration_failure_does_not_block_own_deletion`. The 10 stuck rows from before the fix were cleaned up by re-invoking the deployed `slip-box-reconciler` Lambda directly with synthetic `ObjectRemoved` events for each, after deploying the fix — confirmed all 10 (and their edges) gone afterward, and confirmed a real, non-test note that had an edge to one of the deleted test notes had its frontmatter correctly regenerated with no dangling reference.

**Follow-on hardening, after Stage 1 is live: a staging bucket for `aws s3
sync`, not a guardrail bolted onto Stage 1 itself.** Stage 1's fail-soft
handling (log + skip on unparseable frontmatter) leaves real gaps once a
human is syncing a whole local vault rather than editing one file by hand:
a skip is silent — nothing tells the user a note didn't make it in, it
just looks like the sync did nothing; `_parse_frontmatter` is duck-typed
on structure, not a real YAML validator, so structurally-plausible-but-
wrong frontmatter (a typo'd field, a list where a scalar belongs) parses
"successfully" into garbage rather than failing at all; and nothing
detects two files claiming the same `note_id` (a copy-pasted note whose id
never got changed) — Stage 1 would just silently overwrite the original's
DynamoDB row.

Rather than adding bespoke defensive logic to Stage 1 for each of these,
gatekeep before anything reaches it: sync targets a new **staging**
bucket, not `slip-box-notes` directly, and a promotion Lambda validates
(parses frontmatter for real, checks the staged `note_id` against what's
already live) before copying a file into `slip-box-notes` — which then
triggers Stage 1 normally. Bad or colliding files never reach the trusted
bucket, DynamoDB, or the KB at all, rather than being written and only
discovered as garbage afterward.

**Must be a separate bucket, not a staging prefix within `slip-box-notes`**
— same reason `slip-box-uploads` is a separate bucket for PDFs, not a
prefix: `slip-box-notes` is the Bedrock KB's entire data source, unscoped
by prefix, so anything landing under it (a `_staging/` prefix included)
gets auto-embedded by the KB directly regardless of validation state.
Mirrors `slip-box-uploads`'s existing shape otherwise: transient,
`DESTROY` + short lifecycle expiry, no direct KB exposure.

**Not urgent for the first build** — this is protection against typos and
interrupted syncs for a solo user syncing their own vault, not a security
boundary against untrusted third parties (unlike Guardrails, which *is*
that). Worth building once `#9`'s Stage 1 is live and `aws s3 sync` is
actually in regular use, not before.

**`_handle_delete`'s trigger gap — RESOLVED 2026-08-23.** Everything documented above about Stage 1's `ObjectRemoved` handling was already correct and already live, but nothing in the app had ever actually deleted an S3 object to fire it — no `DELETE /items/{note_id}` route existed anywhere, and the user-facing API Lambda held no `s3:DeleteObject` grant at all. Built as part of adding Delete to the mobile Review flow: the new endpoint deletes only the S3 object(s) and lets this existing reconciler logic do 100% of the DynamoDB cascade, deliberately not touching `items`/`edges` directly from the API layer (doing so would race `_handle_delete`'s own `s3_key` lookup). See `docs/build-log.md`'s "Review gets Tag and Delete" entry.

## 10. Bidirectional Obsidian/S3 sync — open question, not scoped yet

`future-scope.md` currently only covers one-way `aws s3 sync` down to a local
vault. Whether to make it two-way (local edits in Obsidian propagating back)
is still open, and is the harder half of the #9 reconciliation problem:

- **Asymmetric merge rule needed:** body edits from Obsidian should win and
  flip `edited_by_user: true` on the `Item`; frontmatter connections must
  stay agent-generated from Neptune/DynamoDB and never be merged back from
  the local copy — otherwise a stale local frontmatter re-upload could
  silently clobber edge state. This is the write-path mirror of #9's
  read-path fix (regenerate from S3, never overwrite it).
- **Mechanism:** `aws s3 sync` is pull/push, not push-notify, so real
  two-way sync needs either a local watcher (`fswatch`/`inotify`) pushing
  edits up on save, or a filesystem mount (`mountpoint-s3`, `rclone mount`)
  instead of periodic sync. The downward direction is #9's S3 Event
  Notification → Lambda.
- **Tradeoff:** near-real-time bidirectional sync (edit in Obsidian, see it
  reflected within seconds) is more moving parts than MVP scope — likely
  post-MVP, and only worth building once #9's one-way reconciliation exists
  to build on top of.

## 11. No guardrails between FastAPI input and the agent — RESOLVED 2026-08-22 (both bullets)

Deployed and verified against the live stack: pydantic validation (422s confirmed on empty/conflicting `/ingest` bodies) and API Gateway's native API Key + Usage Plan (403 confirmed with no/wrong key, throttle 5rps/10burst + 2000/day quota attached) cover the first bullet below entirely through infra config, no hand-rolled app code. See `docs/build-log.md` Week 3 for the two real IAM/env bugs this deploy surfaced and fixed.

Bedrock Guardrails (second bullet) now built — a `CfnGuardrail` (`agentcore/cdk/lib/app-stack.ts`) with the five standard content-harm filters plus `PROMPT_ATTACK` detection, wired into `app/MyAgent/model/load.py`'s `load_model()` via `BedrockModel`'s native `guardrail_id`/`guardrail_version` params — exactly the plug-in point this item named. Denied topics and PII/sensitive-info filtering deliberately not included (out of scope, need app-specific tuning — a real follow-on, not silently dropped).

**Real false positive caught during live verification, not guessed at**: the first config (`PROMPT_ATTACK` at `HIGH`) blocked every `single`/`all`-mode ingest outright — including plainly benign agricultural text with zero security vocabulary. Root cause: it wasn't content-based at all — `_build_prompt`'s mode-instruction prefix ("Create exactly ONE atomic note from this source...") followed by pasted content is *structurally* identical to an injected-instruction pattern, which is exactly what `PROMPT_ATTACK` is trained to catch, regardless of what the pasted content actually says. `auto` mode (no instruction prefix) was unaffected — that isolated the cause. Lowered to `MEDIUM`, redeployed as a stable published version, re-verified: benign `single`/`all`-mode ingests succeed again, and a deliberate injection attempt ("SYSTEM OVERRIDE: ignore all previous instructions...") still gets blocked. Worth remembering if `_build_prompt`'s prefix pattern changes shape later — re-check this specific interaction, not just "does the guardrail still fire on attacks."

**Follow-up, 2026-08-23: the `MEDIUM` fix above wasn't the whole story.** A `single`-mode ingest with a `url` source (not `text`) still got blocked — `finish_reason: "guardrail_intervened"` on the very first model turn, before any tool call. Confirmed via `bedrock-runtime apply-guardrail` run directly against the exact blocked prompt: `PROMPT_ATTACK` fired at `confidence: MEDIUM` against the `MEDIUM`-strength filter (Bedrock blocks when confidence ≥ strength), so this is a second, distinct trigger of the same underlying pattern — the imperative override phrasing ("Create exactly ONE atomic note... do not create multiple notes even if...") immediately followed by "Ingest this URL: https://..." reads as an even closer structural match to indirect prompt injection (imperative instruction + "go fetch this") than the `text`-based case that prompted the original `MEDIUM` fix. `mode: auto` (no instruction prefix) with the same URL was unaffected, confirming the prefix itself as the trigger again, not the URL alone. Fix this time was wording, not guardrail strength: reworded `_mode_instruction`'s `single`-mode branches (`app/api/routers/ingest.py`) from a "Create exactly ONE... do not create multiple..." command shape to a declarative "The user selected single-note mode... Summarize the source into one atomic note..." shape — tested directly against `apply-guardrail` before touching any deployed code, confirmed `action: NONE` for both the topic and no-topic variants. Deployed and re-verified live: both `single`-mode variants (with and without `topic`) now complete cleanly against the same Wikipedia URL that was previously blocked. Preferred this over raising `PROMPT_ATTACK` to `HIGH` — that would have papered over the false positive by also letting through genuinely higher-confidence attack patterns; rewording fixes the actual cause without loosening the security posture. Regression-covered in `app/api/tests/test_ingest_prompt.py` (pins the wording, can't exercise the guardrail itself — that stays a live-only check per this project's testing philosophy for LLM/classifier judgment).

Once `/ingest` exists, arbitrary user-submitted URLs/text/PDFs flow straight
into the agent's context, and `fetch_url` pulls in third-party web content
the agent then reasons over with tools that write to S3/DynamoDB
(`write_note`, `write_edge`, `write_summary`, `update_summary`). That's a
classic **indirect prompt injection** surface: a page fetched via
`fetch_url` could contain text aimed at the agent rather than the user —
instructions trying to get it to write bogus notes, mislabel edges with
inflated confidence, or (as more tools land) do something more damaging.
Separately, there's currently no request validation, auth, or
rate-limiting at the API boundary at all — anyone who reaches `/ingest` can
burn Bedrock spend or spam the KB with junk.

**Fix, scoped in layers:**
- **FastAPI-level input validation** — pydantic schemas on every endpoint
  (size caps on `text`/`url` fields, content-type checks), basic auth
  (even a static API key is enough for a hackathon demo) and rate-limiting
  before a request ever reaches `agentcore invoke`/`invoke_agent_runtime`.
- **Amazon Bedrock Guardrails** — the AWS-native layer to apply to the
  model call itself: content filters, denied topics, and prompt-attack/
  jailbreak detection. Worth evaluating specifically for the
  `fetch_url` → agent path, since that's the one place untrusted
  third-party content (not just the user's own input) reaches the model.
- Neither of these exists today. Build them alongside the FastAPI backend,
  not as a follow-up after `/ingest` ships open — an unauthenticated,
  unvalidated ingestion endpoint is an easy thing to demo past and forget.

---

*Recommended order, updated 2026-08-23: #1, #2, #3, #6, #8, #9 (Stage 1 +
Stage 2), and #11 are all resolved; the note-created-entirely-outside-the-
system case (missing `note_id`/sidecar, no linkages — previously its own
item) was folded into #9 and shipped with it, not tracked separately
anymore. Still open under #9: the `aws s3 sync` staging bucket — non-
blocking hardening, not required for the core guarantee. #10 is downstream
of #9 — don't start it first. #7 (`--research` fan-out) is the one big
remaining feature item, still blocked on the deferred search-provider
choice (Tavily/Exa) — #8's classification agent is built and ready for the
research node to hand off to once that's picked. #4–#5 are independent
metadata/provenance polish, no dependency on anything above.*

## 13. Agent session-caching machinery is currently inert — needs a decision, not urgent

Found during a 2026-08-22 QA pass of the codebase against the new `strands-agents-sdk`/`bedrock-agentcore` skills. `main.py`'s `agent_factory()` hand-rolls a 128-slot LRU cache keyed by `session_id`, and `Agent(...)` is constructed with `conversation_manager=NullConversationManager()` — both only matter if a `session_id` gets reused across calls. It never does: `app/api/routers/ingest.py` mints a fresh `uuid.uuid4()`-based `session_id` on every single `/ingest` request, and `worker.py` passes it straight through unchanged. Confirmed via grep that nothing in the API code ever sends the `messages`/`tool_results` payload shapes `main.py`'s `_extract_prompt` supports either — only `prompt`.

In today's actual usage: every request is a cache miss (the cache just holds one-shot entries until evicted or cold-started away), there's no accumulated multi-turn history for `NullConversationManager` to (not) manage, and `_extract_prompt`'s support for other payload shapes is dead code.

Not a bug — nothing behaves incorrectly — but it means this layer was built for a multi-turn conversation pattern the app doesn't currently exercise. **Needs a decision:** (a) keep as intentional future-proofing for eventual multi-turn ingest conversations (`_extract_prompt`'s existing shape-handling suggests that was the original intent), or (b) simplify now — drop the LRU cache since it does nothing today. Same applies to `S3SessionManager` from the `strands-agents-sdk` skill: it would be no more useful than the current setup for the same underlying reason (no session reuse), so it's not an obvious upgrade path either — only worth adopting once (a) is chosen and cold-start session loss actually matters.

---

## Expo vs Next.js for frontend

CLAUDE.md currently specs Next.js/TypeScript + Amplify for the three MVP screens (Ingest, Pending edge review, Graph view). Worth reconsidering given the desire for a native mobile app with share-sheet capture ("share anything to Slip Box easily").

**Case for Expo:** native iOS/Android share extension is a real capture-friction win — the brief's own framing is that Obsidian/Zettelkasten tools get abandoned because *managing* the system is overhead, and one-tap share-to-capture directly attacks that. `react-native-web`/Expo Router also gives a web build from the same codebase.

**Pitfalls found sketching it out:**
- **Graph view doesn't have a good RN-native library.** `react-force-graph`/Cytoscape.js are web-canvas libs; on mobile this likely means wrapping the web graph in a `WebView` rather than a true native render.
- **Rich markdown editor for `PermanentNote` writing is weak on RN.** The selection-first writing flow (reference panel + editor) wants a real editor (TipTap/Milkdown-class); RN mostly offers plain `TextInput` or WebView-wrapped web editors — so the writing screen likely ends up as a WebView too.
- **Share extension isn't a free win.** It needs EAS dev builds + config plugins + an Apple Developer account — not available in Expo Go. Most of Expo's payoff lives behind this one setup cost.
- **Graph cluster drag-and-drop (add/remove notes from a `SummaryCard` cluster) doesn't translate to touch.** Realistically mobile is view/browse-only for the graph; editing stays web-first regardless of stack.
- **Amplify's Next.js-specific SSR support is given up** with Expo's static web export — likely a non-issue since this is an authenticated dashboard app, not SSR-dependent content pages, but worth naming as a tradeoff rather than assuming for free.

**Preferred direction:** rather than one Expo codebase for everything, a *thin* separate Expo app scoped to just capture/share-sheet + read-only browse (hitting the same FastAPI backend as the Next.js web app) — two codebases, each in its strong lane, for a solo maintainer. Leaning this way over fighting RN's weaker graph/editor ecosystem across `Platform.OS` branches in a single unified app.

Either way, this is fully compatible with the FastAPI backend already built (`docs/build-log.md` Week 3) — both a Next.js web app and a thin Expo app would consume the same `/ingest`, `/items`, `/graph`, `/edges/{from_id}/{edge_id}` endpoints, so this decision doesn't block or reshape anything already shipped.
