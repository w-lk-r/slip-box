# Hackathon Pitch & Submission Strategy
**Agents for Humans Hackathon (AWS/Devpost) — deadline Sep 14, 2026**

> For current architecture and implementation details, see the root [`CLAUDE.md`](../CLAUDE.md) and the chronological record in [`build-log.md`](build-log.md). This doc is the day-1 pitch framing and submission plan — differentiation angle, judging strategy, blog tracker, timeline. Its original architecture/storage/taxonomy sections have been superseded by `CLAUDE.md` and were removed here to avoid the two drifting apart; keep this file for pitch-writing reference, not architecture reference.

## Concept

A "second brain" / Zettelkasten-inspired research agent. You send it sources (articles, YouTube transcripts, text, PDFs); it extracts, summarizes, and finds connections between items and larger concepts — solving the real problem that tools like Obsidian and physical slip-boxes get abandoned because managing the system is more overhead than the value of using it.

**Differentiation from existing tools** (NotebookLM, Mem, Sinapsus, Obsidian+Smart Connections):
- Existing tools show *similarity*. This shows **typed relationships** (SUPPORTS / CONTRADICTS / EXTENDS) with **confidence-gated auto-write** — the agent reasons about *how* things relate, not just *that* they're similar.
- Existing tools are inward-only (act on what's given). This has an **on-demand outward research mode** that fans out to find corroborating/contradicting material.

## Source Ingestion Scope

- **In scope for MVP/demo:** articles/web pages (readability extraction), YouTube (transcript APIs / yt-dlp + Whisper fallback if no captions), plain text, PDF.
- **Explicitly out of scope:** Instagram/TikTok reels — no stable public API, high ToS risk for something built to be shown publicly. Support via manual fallback only (paste caption/description); see `future-scope.md`. Judges tend to respect a clearly stated scope boundary.

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

Actual day-by-day progress is tracked in [`build-log.md`](build-log.md), not here — this timeline was the week-1 plan, kept as written for reference.
