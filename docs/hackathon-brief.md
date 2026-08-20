# Project Brief: Research-Connections Agent
**Agents for Humans Hackathon (AWS/Devpost) — deadline Sep 14, 2026**

## Concept

A "second brain" / Zettelkasten-inspired research agent. You send it sources (articles, YouTube transcripts, text, PDFs); it extracts, summarizes, and finds connections between items and larger concepts — solving the real problem that tools like Obsidian and physical slip-boxes get abandoned because managing the system is more overhead than the value of using it.

**Differentiation from existing tools** (NotebookLM, Mem, Sinapsus, Obsidian+Smart Connections):
- Existing tools show *similarity*. This shows **typed relationships** (SUPPORTS / CONTRADICTS / EXTENDS) with **confidence-gated human review** — the agent reasons about *how* things relate, not just *that* they're similar.
- Existing tools are inward-only (act on what's given). This has an **on-demand outward research mode** that fans out to find corroborating/contradicting material.

## Core Design: Two-Tier Ingestion

- **Default (no flag):** send item → embed → auto-match against existing corpus → fast, cheap, always-on. This is the MVP backbone.
- **`--research` flag:** same ingestion, but triggers outward research (search + fetch related/contradicting sources), builds a small sub-corpus around the item, analyzes it (optionally SWOT-style), then folds the richer cluster into the graph. Slower, deliberate, shows off agentic depth.

## Confidence-Filtered Connections

- Agent classifies proposed edge type (SUPPORTS/CONTRADICTS/EXTENDS) with a confidence score.
- **≥ threshold** → written to Neptune automatically.
- **< threshold** → dropped entirely — no queue, no noise in the graph.
- Threshold lives in `app/MyAgent/config.py` (`EDGE_CONFIDENCE_THRESHOLD = 0.65`) — tune once real classification output is observed, not before.
- **All edges are user-editable/deletable** from the graph view after the fact; append-only `history` log per edge for provenance.
- In the graph view, edges near the threshold render visually differently (dashed / muted) so the user can spot and correct anything they disagree with inline. To re-examine dropped connections, the user can ask the agent directly ("what else is this connected to?") and classification reruns on demand.

**Connections live on the card, matching the original method.** Luhmann's slip-box notes carried explicit references to other notes, written on the card itself — not in a separate index. Reflecting that:
- Connections are written into the note's own **frontmatter** (not the body) as typed link lists — `supports: ["[[item-1234]]"]`, `contradicts: [...]`, `extends: [...]`, `related_to: [...]` — using `[[wikilinks]]` so Obsidian's native graph/backlinks picks them up. Regenerated from Neptune's current edge state on every change, never appended, so the file can't drift out of sync. Body stays pure prose; frontmatter stays system-generated — no risk of a sync process clobbering hand-written text.
- Excluded from KB embedding (same principle as the rest of frontmatter) — mirrored into `.md.metadata.json` instead, so Bedrock KB can filter by connection without diluting semantic retrieval.
- **Neptune stays the source of truth for the graph.** S3 remains source of truth for note *content*; the frontmatter connections are a generated reflection, never authored directly.

## Note Taxonomy: Literature Notes, Ideas, and Summary Cards (stretch feature)

Real Zettelkasten distinction, not just naming — and not a uniform rule across all three types. `Item` and `SummaryCard` are *information transformation* (extract, summarize, roll up existing material) — AI doing this well doesn't undercut the method. `PermanentNote` is different: the value of a permanent note is the human forming the idea in their own words: that's the cognitive work the whole method is built around, so it's user-authored only, no model draft state.

- **Literature note** (`Item`) — source-bound, extracted/summarized in relation to its source. Carries `authored_by: model | user`.
  - `authored_by: model` — the default: ingestion agent extracts/summarizes on ingest, auto-written, no confidence gate (it's an extraction, not a claim).
  - `authored_by: user` — user writes/replaces the note directly instead of accepting the agent's extraction.
  - `edited_by_user: bool` flags a model-authored note that was later hand-edited (hybrid provenance).
- **Idea** (`PermanentNote`) — atomic, in the user's own words, decontextualized. **Always user-authored — no `authored_by` field, no draft state.**
  - **Write path bypasses the agent entirely:** frontend → FastAPI → S3 + DynamoDB + KB sync trigger. The agent never writes to the note body.
  - **Recommended path (selection-first):** user selects literature notes from the graph/list before opening the editor. Selected notes appear in a reference panel alongside the writing surface — reading them IS part of the thinking. On save, `GROUNDED_IN` edges are written from the selection automatically (`authored_by: user`). Mirrors Luhmann pulling physical notes onto the desk before writing. This is the primary UX, not the only one.
  - **Alternative path (raw write):** user writes without pre-selecting. Edges can be added manually afterward or via "Find more connections."
  - In both cases: optional "Find more connections" triggers the classification agent post-save to propose additional edges the user didn't explicitly choose — `authored_by: model`, additive only, never overwrites user edges. Same confidence threshold applies.
  - The reference panel (selected notes alongside editor) is the same component as the literature excerpts sidebar — triggered pre-save rather than post.
- **Summary card** (`SummaryCard`) — a cluster-synthesis rollup spanning multiple items/ideas (e.g. output of the SWOT/analysis agent), distinct from a single-source literature note. Carries `authored_by: model | user`.
  - `authored_by: model` ("model-derived summary card") — the common case: analysis agent synthesizes a cluster, staged `status: draft` pending user confirm, reusing the same pending/confirm/override UX already built for edges.
  - `authored_by: user` — user assembles or edits a rollup card manually.

**Linkages** — no new edge types needed; widen which vertex types the two existing distillation edges connect:
- `DISTILLED_INTO`: `Item | PermanentNote` → `PermanentNote | SummaryCard` — a literature note or idea distilled into a more atomic idea, or several distilled into a broader synthesis card.
- `GROUNDED_IN`: `PermanentNote | SummaryCard` → `Item` — an idea or summary card cites the specific literature notes it's grounded in, keeping an evidence trail back to source-bound notes.

Same append-only `history` log and pending/confirm/override UX as edges — authorship provenance and confidence gating both fall out of the one pattern already in place.

**Structure notes / MOCs — no new vertex type either.** A MOC is just a `PermanentNote` (user-curated, same as any idea) whose content is a set of `RELATED_TO` links to other notes. Luhmann's original Folgezettel numbering encoded a timeline as much as a topic tree — each note's ID reflected when it was inserted relative to its neighbors — so rather than adding a manual ordering field on the edges, every vertex carries `created_at`/`updated_at` (see Neptune section below) and a MOC's linked notes are simply rendered sorted by `created_at`, reconstructing the chronological-insertion structure on the fly.

## Architecture — AWS/Python-native (no Supabase; staying in AWS ecosystem)

**Agent layer:**
- **Strands Agents SDK** — agent logic, tool orchestration. Model-agnostic; calls Bedrock in this build.
- **Amazon Bedrock** — LLM inference (reasoning, classification, embeddings).
- **AgentCore Runtime** — hosting layer. Containerized (arm64, ECR), session-isolated (dedicated microVM per session), supports long-running workloads up to 8 hrs (vs. Lambda's 15-min ceiling) — needed for the multi-agent `--research` chain. Explicitly called out by the hackathon as strengthening Technical Implementation score.
- ~~**AgentCore Memory**~~ — **Replaced.** AgentCore Memory has a hard 365-day expiry cap (schema-enforced, no unlimited option), making it unsuitable as a permanent knowledge store. Replaced with Bedrock Knowledge Base + S3.

**Storage:**
- **S3** — primary document store. Each ingested item written as an atomic `.md` file with YAML frontmatter. Human-readable, portable, enables Obsidian sync via `aws s3 sync`. Indefinite persistence.
- **Bedrock Knowledge Base** — syncs from S3, creates embeddings for semantic retrieval. Replaces AgentCore Memory. No expiry, better retrieval control, and notes remain accessible as plain `.md` files independent of the KB.
  - **The `.md.metadata.json` sidecar is a Bedrock KB requirement**, not an application choice. The KB reads it during S3 sync to treat fields (type, source, date, tags) as filterable metadata rather than embedding them as semantic content. Without it, frontmatter bleeds into embeddings and degrades retrieval. The KB cannot read DynamoDB; the sidecar cannot be removed. Keep it minimal — only what the KB needs for filtering. Full metadata lives in DynamoDB.
  - **Chunking strategy is deliberate, not default fixed-size.** Use hierarchical or semantic chunking for literature notes (longer, source-bound) so retrieval returns coherent sections instead of mid-thought cuts. Short atomic `PermanentNote`s will mostly embed as a single chunk regardless, which is fine.
  - Get this right from the start of MVP step 1 — retrofitting the sidecar/chunking pattern later means a full KB re-sync.
- **DynamoDB** — `items` table: structured metadata for all note types (`literature-note`, `permanent-note`). `edges` table: (`from_id`, `to_id`, `type`, `confidence`, `history`) — covers all MVP graph query needs without VPC complexity. Neptune is the production target for the full graph but not needed for the demo.
- **Amazon Neptune (graph DB)** — the actual connections model. Vertices: `Item`, `Concept`, `PermanentNote`, `SummaryCard` (stretch — see Note Taxonomy below), `Source`. Every vertex carries `created_at`/`updated_at` — not just incidental metadata, it's what powers the timeline/MOC view below. Typed edges: `MENTIONS`, `SUPPORTS`, `CONTRADICTS`, `EXTENDS`, `RELATED_TO`, `RESEARCHED_VIA`, `DISTILLED_INTO`, `GROUNDED_IN`. Chosen over pure vector search because the product is literally about a graph of typed relationships — more visible/demoable design choice than nearest-neighbor lookup.
- (Alternative considered: OpenSearch Serverless for custom vector control; S3 Vectors for cheapest/simplest. Neptune preferred for the graph-native fit.)

**Tools (Strands):**
- Bedrock Knowledge Base retrieval — semantic search against ingested `.md` notes.
- Web search/fetch tools (Tavily/Exa via `strands_tools`) — outward research fan-out.
- Custom `@tool` functions — Neptune writes, DynamoDB writes, YouTube transcript extraction (youtube-transcript-api / yt-dlp), SWOT logic.
- `handoff_to_user` — human-in-the-loop confidence gating.
- MCP considered but not required for this build — mostly relevant if reaching third-party services with existing MCP servers; custom tools suffice for AWS-native pieces.

**Multi-agent split:** ingestion agent, classification agent (edge typing), research agent (search/fetch), SWOT/analysis agent — separate agents, not one mega-prompt (stronger Technical Implementation signal). Worth reviewing Strands multi-agent primitives (Agent-as-Tool, Swarm, A2A) before wiring these together.

**Frontend:**
- **Next.js / TypeScript** (chosen over FastAPI+HTMX/Streamlit/Reflex — lower risk given existing fluency, better UI ceiling for Design scoring).
- **FastAPI** as the backend layer between Next.js and AWS — exposes `/ingest`, `/edges/{id}` (edit/delete), `/graph`; invokes Strands agents on AgentCore Runtime, reads/writes DynamoDB + Neptune.
- Two MVP screens: **Ingest** (form + `--research` toggle), **Graph view** (node-link graph, color-coded by edge type, low-confidence edges rendered differently — the demo payoff shot). Suggested libs: react-force-graph (speed) or Cytoscape.js (finer edge-label control).
  - **Timeline mode (stretch)** — same node/edge data for a MOC's linked notes or a note's neighborhood, laid out along a time axis (by `created_at`) instead of force-directed, replaying the order ideas were actually connected. A rendering toggle on top of existing graph data, not a new backend concept.
- Hosting: AWS Amplify Hosting (keeps AWS-native story consistent) or Vercel.

## Source Ingestion Scope

- **In scope for MVP/demo:** articles/web pages (readability extraction), YouTube (transcript APIs / yt-dlp + Whisper fallback if no captions), plain text, PDF.
- **Explicitly out of scope:** Instagram/TikTok reels — no stable public API, high ToS risk for something built to be shown publicly. Support via manual fallback only (paste caption/description), mention as future work in the pitch. Judges tend to respect a clearly stated scope boundary.

## Scope: MVP vs. Stretch

- **MVP:** ingest (URL/text/PDF/YouTube transcript) → embed → auto-link (threshold filter) → basic graph view with inline edge editing.
- **Stretch:** `--research` flag fan-out, SWOT analysis, literature/permanent note promotion, frontmatter as a pending-connection review surface.
- Build MVP fully solid first — it's the demo safety net — before investing in stretch features.

## Judging Criteria Strategy (equally weighted, 1–5 scale, +0.6 bonus = 5.6 max)

1. **Technical Implementation** — multiple distinct Strands agents with real tool use (not one mega-prompt); deploy on AgentCore Runtime; ship a live demo link.
2. **Design** — full loop must be visible: ingest → auto-link OR ask-for-input → confirm/override → graph updates. Build the pending-edge review UI properly, not just the ingestion screen.
3. **Potential Impact** — commit to one specific track/audience. Leaning **Professional Agents**, framed narrowly (e.g., independent contractor/consultant synthesizing client research). Use own workflow as the credible use case.
4. **Creativity & Originality** — lead with typed-relationship + confidence-gating differentiation vs. NotebookLM/Mem/Sinapsus; outward research fan-out is the strongest "non-obvious use of Strands" angle.
5. **Presentation** — video: problem → audience → why it matters → live end-to-end demo in one continuous sequence (plain ingest → auto-link → flagged ingest → research fan-out → ambiguous edge → review → graph updates). End on the graph view as payoff shot.

## Bonus: builder.aws.com Blog Posts (0.2 pts each, up to 0.6 total)

Must include **#AgentsForHumans** in title, published publicly on builder.aws.com before deadline.

- **Post 1 (now/early):** brainstorm/journey — problem, personal background, why this idea. *(Draft in progress — Dad-of-two-under-3, returning to serious coding via this hackathon, Obsidian/Zettelkasten abandonment story as the personal stake.)*
- **Post 2 (~week 2):** architecture/AgentCore decisions — why Runtime over Lambda, why Neptune over pure vector search.
- **Post 3 (~week 4):** human-in-the-loop / confidence-gating design rationale.
- Write posts *as you build*, not retroactively — more authentic, easier.
- Check builder.aws.com for a dedicated "Agents for Humans" space before posting into a general one — not confirmed to exist at time of writing; check Devpost Resources tab for official pointer.

## Timeline (target: ship before family trip to Australia)

- **Week 1:** blog post #1, confirm eligibility (Australia is on hackathon's excluded-countries list — likely fine since eligibility is residence-based and residence is Japan, but verify), lock MVP/stretch scope in writing, deploy Strands "hello world" on AgentCore Runtime.
- **Week 2:** build fast-path ingestion pipeline (item → AgentCore Memory → classification → confidence gate → DynamoDB/Neptune writes), minimal pending-edge review UI, blog post #2.
- **Week 3:** build `--research` flagged path, literature/permanent notes if time allows, start recording demo footage incrementally.
- **Week 4 (buffer):** blog post #3, edit demo video, write submission pitch, submit with days to spare.

