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

---

*Recommended order: #1 unblocks #2 and is the app's core value prop; #3–#6
are metadata/provenance polish on top of a graph that, once #1 lands, will
actually get written.*
