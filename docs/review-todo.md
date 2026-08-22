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
type (`/graph` showing Source nodes, a `RESEARCHED_VIA` edge) and PDF
ingestion itself — both build on this schema (`type: "pdf"`, a content-hash
`source_key` instead of a normalized URL) once picked up.

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

## 6. `fetch_url` has no content-type handling — YouTube half RESOLVED 2026-08-21 (moved client-side)

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

PDF is still unhandled — blind regex HTML-stripping on whatever `httpx`
returns, no branch for PDF text extraction. A PDF URL would still get
mangled rather than routed to a proper extractor.

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

## 9. DynamoDB has no reconciliation path for edits made directly in S3/KB — clobber bug RESOLVED 2026-08-21, Lambda still open

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

**Fix:** S3 event notification (suffix-filtered to `.md`, so the
`.md.metadata.json` sidecar is excluded) → Lambda that parses frontmatter
and upserts the DynamoDB row, keyed on the frontmatter's `note_id` field
(not the S3 object key) so renames self-heal instead of orphaning. Handle
`ObjectRemoved` too, so deleted notes don't leave orphaned rows. Keep this
decoupled from KB reindexing — reconciling a DynamoDB row is cheap and can
fire per-object, but starting a Bedrock ingestion job is a batched,
non-trivial-cost operation and shouldn't fire on every single write; keep
`trigger_kb_sync` on its own (debounced or explicit) cadence. Fail soft on
malformed frontmatter (log + skip) rather than crash, since manual edits
will eventually have YAML typos. This is new infra in the
`agentcore/cdk/` app stack (`SlipBox-App-*` — S3, DynamoDB, Neptune later),
not the agent's `agentcore.json` policies.

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

## 11. No guardrails between FastAPI input and the agent — RESOLVED 2026-08-21 (first bullet only)

Deployed and verified against the live stack: pydantic validation (422s confirmed on empty/conflicting `/ingest` bodies) and API Gateway's native API Key + Usage Plan (403 confirmed with no/wrong key, throttle 5rps/10burst + 2000/day quota attached) cover the first bullet below entirely through infra config, no hand-rolled app code. See `docs/build-log.md` Week 3 for the two real IAM/env bugs this deploy surfaced and fixed.

Bedrock Guardrails (second bullet) remains deferred — plug-in point documented as `app/MyAgent/model/load.py`'s `load_model()`. This item stays open until that's built.

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

## 12. Local-filesystem-created notes need sidecar + frontmatter backfill + linkage triggering, not just DynamoDB reconciliation

Extends #9: the S3 Event Notification → Lambda sketched there handles
metadata reconciliation for notes the agent already wrote (backfilling
DynamoDB when a hand-edit changes title/tags). It doesn't cover the harder
case — a note created **entirely outside the system**, written directly in
a local Obsidian vault, then pushed up via
`aws s3 sync ~/ObsidianVault/SlipBox/ s3://slip-box-notes/` (the push
direction of the one-way sync already documented in `future-scope.md`). A
file arriving this way is missing three things the rest of the system
assumes exist:

1. **No `.md.metadata.json` sidecar** — required by the Bedrock KB to treat
   frontmatter as filterable metadata rather than embedding it as content
   (the sidecar requirement in root `CLAUDE.md`). A raw Obsidian file won't
   have one.
2. **Possibly incomplete/malformed frontmatter** — a hand-written note may
   be missing `note_id`, `type`, `date`, or the typed link-list fields
   (`supports: []` etc.) the rest of the system assumes are present.
3. **No linkages** — the actual point of ingestion (typed-relationship
   classification against the existing corpus) never ran, since the note
   never passed through the ingestion agent's `search_notes`/`write_edge`
   flow.

**Two-stage design, split by whether an LLM is actually needed:**

- **Stage 1 — Lambda-only, no agent involved** (extends #9's Lambda): on
  `ObjectCreated`, parse frontmatter. If `note_id` is missing, generate one
  the same way `write_note` does (`{_slugify(title)}-{uuid8}`) and rewrite
  the file's frontmatter with it, so the S3 copy and DynamoDB agree going
  forward. Backfill other missing required fields with sane defaults
  (empty typed-link lists, `type: literature-note` if unspecified,
  `authored_by: user`). Write/regenerate the `.md.metadata.json` sidecar
  from the now-normalized frontmatter. Upsert the DynamoDB `items` row. All
  of this is cheap, deterministic, and needs no Bedrock call.
- **Stage 2 — needs the agent, triggered from Stage 1's Lambda**: once the
  note is normalized and has a stable `note_id`, fire an async call into
  the *same* invocation path `POST /ingest`'s `WorkerFunction` already uses
  (`invoke_agent_runtime`) — but with a distinct prompt, since this note
  already exists and shouldn't be re-written: something like "note
  `{note_id}` was just added outside the ingestion flow — search the KB
  and propose `write_edge` calls for how it relates to existing notes,"
  skipping `write_note` entirely. This reuses the classification behavior
  already built into the ingestion agent's system prompt instead of
  duplicating search/scoring logic in the Lambda — the Lambda's job stays
  structural normalization, the agent's job stays semantic classification,
  matching the split #8 already argues for.

**Why route through the FastAPI worker rather than a bespoke Lambda→agent
call:** the shape needed here — invoke asynchronously, don't block on the
LLM, IAM scoped narrowly to just `InvokeAgentRuntime` — is exactly what
`WorkerFunction` (`app/api/worker.py`) already is. No new pattern to
design, just a new caller and a new prompt template. The only new plumbing
is IAM: the reconciliation Lambda needs `lambda:InvokeFunction` on
`WorkerFunction`, the same grant `ApiFunction` already has.

**Not urgent for MVP** — like #9's own fix, this only matters once
something writes to S3 outside the agent's own tools. `PermanentNote`'s
direct write path (frontend → FastAPI → S3+DynamoDB, no agent — still
out of scope per the FastAPI backend plan) will exercise this before
Obsidian sync does; worth building alongside `/notes` rather than waiting
for local-sync specifically.

---

*Recommended order: #1 unblocks #2 and is the app's core value prop. #3
(structured Source records, resolved 2026-08-22) and #6 (YouTube half
resolved same day) should land before #7 — the research agent is the
workload that will hammer sourcing hardest, and is the first caller that
actually needs PDF-aware fetching (the one remaining piece of #6) and
real dedup (now built, via #3). #4–#5 are independent metadata/provenance
polish. #8 is a structural decision worth settling before #1 and #7 are
built, since it determines whether classification/research land as
in-process Agent-as-Tool calls or standalone AgentCore agents. #9 should
land early too — it's infra, not agent logic, so it can be built in
parallel with #1, and every other item that writes frontmatter (#1, #3, #4)
benefits from DynamoDB being a reliable materialized view instead of a
separately-mutated copy. #10 is downstream of #9 — don't start it first.
#11 must land with the FastAPI backend itself, not after — the fetch_url →
agent path is a live prompt-injection surface the moment `/ingest` is
public. #12 is downstream of both #9 (extends its Lambda) and the FastAPI
backend (reuses its worker) — don't start it before either exists, and it
has no urgency until something writes new notes to S3 outside the agent.*

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
