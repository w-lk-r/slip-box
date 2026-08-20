# Review TODO — Metadata & Provenance Gaps

Findings from a review of what's actually implemented in `app/MyAgent/` vs. what
`CLAUDE.md` and `docs/hackathon-brief.md` describe. These are cases where the
design treats something as a structured, linkable piece of data, but the code
currently drops it to a flat string, an empty placeholder, or nothing at all.
Ordered by priority.

---

## 1. Relationship edges are never persisted

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

## 2. Confidence scores don't exist

`EDGE_CONFIDENCE_THRESHOLD` is defined in `config.py` but nothing computes or
checks a confidence value anywhere. The "edges near threshold render
differently, user can correct inline" UX has no data to read from. Blocked
on #1 — confidence is scored at edge-classification time.

## 3. Source references are a flat, unstructured string

`write_note`'s `source_url` param goes straight into frontmatter/DynamoDB as
a bare string — no author, title, publish date, retrieved date, or pinpoint
location (page/timestamp). `fetch_url` strips all HTML including the title
and byline that would be needed to build a real citation, so that metadata
is discarded at fetch time, not just at write time.

`CLAUDE.md` lists `Source` as its own Neptune vertex type, but nothing in
code creates one — sources aren't graph citizens the way
`supports`/`contradicts`/`extends`/`related_to` targets are meant to be.
Consequences:
- Re-ingesting the same URL creates a second `note_id` with a duplicate raw
  string — no dedup, no link between notes sharing a source.
- Can't answer "everything I've read from X" as a graph query.
- No way to pin a specific claim to a specific location in a long PDF/video.

**Fix:** resolve/create a canonical `source_id` on write (normalize URL for
dedup), capture structured metadata once, and reference it from the note as
`source: [[source-id]]` instead of a raw string — same pattern as the other
typed links.

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

## 6. `fetch_url` has no content-type handling

Blind regex HTML-stripping on whatever `httpx` returns — no branch for PDF
or YouTube, even though both are named as first-class source types in the
hackathon brief. A PDF or YouTube URL would get mangled rather than routed
to a proper extractor (YouTube transcript API, PDF text extraction).

## 7. Research agent (`--research` fan-out) doesn't exist yet — design notes for when it's built

`CLAUDE.md` describes a `--research` path that fans out to a research agent
before classification, but there's no research agent, no outward
search/fetch tools beyond the ingestion `fetch_url`, and no budget
enforcement. Notes for the build:

**Tools needed**
- Web search (Tavily or Exa via `strands_tools`), returning ranked snippets
  so the agent reads before it fetches.
- `search_notes` first, always — check the KB before going outward so
  research doesn't re-fetch what's already grounding an existing note.
- A hardened fetch replacing `fetch_url` (see #6): branch by content type
  (readable-text extraction for HTML, PDF text extraction, YouTube
  transcript), returning structured `{title, author, published_date, text}`
  instead of a stripped blob — that structure is what feeds citations.
- A citation/source-resolution tool that resolves or creates the canonical
  `Source` record from fetched metadata (depends on #3).

**Limiting expansion size**
Don't rely on the system prompt to self-limit tool-call counts. Enforce a
budget in code: a `ResearchBudget` object created per `--research`
invocation, threaded through the search/fetch tools as shared state (same
pattern as the session cache in `main.py`), hard-stopping on:
- max search queries per run (e.g. 3–5)
- max sources fetched per run (e.g. 5–8), chosen from search snippets by
  relevance, not fetched blind
- max chars per fetched source (lower than the current 50k — research
  content competes with the note-writing budget, not just one page)
- a combined character budget across all fetched sources per run, so a
  handful of huge pages can't each spend the full per-source cap
- max new notes written per research fan-out, same shape as the existing
  4+-notes-triggers-a-summary-card cap

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

## 8. Multi-agent split shouldn't be a routing supervisor — dispatch by endpoint instead

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

---

*Recommended order: #1 unblocks #2 and is the app's core value prop. #3 and
#6 should land before #7 — the research agent is the workload that will
hammer flat-string sourcing hardest (N duplicate unstructured `source_url`
strings per run, no dedup) and is the first caller that actually needs
PDF/YouTube-aware fetching. #4–#5 are independent metadata/provenance
polish. #8 is a structural decision worth settling before #1 and #7 are
built, since it determines whether classification/research land as
in-process Agent-as-Tool calls or standalone AgentCore agents.*
