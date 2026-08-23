# Front-End UX Spec — Using the Slip Box, Not Just Filling It

Ingestion works well: send a source in, the agent classifies and writes it, done. What's thin is everything *after* that — reading, reviewing, arranging, finding a way back in. This doc solidifies the brainstorm on that gap into something buildable. The original brainstorm (with visual mockups of the card-flip interaction, the desk view, and the review queues) is a published artifact — ask for the link if it's not at hand; this doc supersedes it as the working reference for implementation, and the artifact stays useful for the visual/narrative framing.

This isn't only a nice-to-have. Design is its own hackathon judging criterion, weighted equally with Technical Implementation, and the brief specifically calls for the review loop to be built properly rather than treated as an afterthought to ingestion (see `docs/hackathon-pitch.md`). It's also the project's own thesis: Obsidian and physical slip-boxes get abandoned because maintaining the system costs more than using it pays back. Everything below is aimed at tipping that balance the other way.

Four rituals from the physical method, translated into what a phone and a browser each do best:

| Ritual | Surface | Status |
|---|---|---|
| **Review** — what needs a decision this week | Web (queue UI) | **Spec'd below, building now** |
| **Flipping** — pull a card, follow where it points | Mobile-first (Expo) | Design-level only, see brainstorm artifact |
| **Laying cards out** — arrange a desk before writing | Web (spatial canvas) | Design-level only, see brainstorm artifact |
| **Index cards** — sparse, curated entry points | Both | Design-level only, see brainstorm artifact |

---

## Reviewed status (new — cross-cutting)

A note written by the agent (`write_note`/`write_summary`) is provisional the moment it's created: nobody has actually looked at it, confirmed its framing, or checked its connections. That's a real, useful distinction to track — not unlike Luhmann's *fleeting notes*, which were understood to be unprocessed and not yet trustworthy until worked through properly.

That analogy is doing real work as **motivation** here, but it's deliberately not becoming a new entry in `CLAUDE.md`'s note taxonomy (`Item` / `PermanentNote` / `SummaryCard`). This is a review *status* on the two model-authored types, not a fourth kind of note — `PermanentNote` never gets one (always user-authored, no draft state, and there's no write path for it yet at all per the MVP scope).

**Field**: `reviewed_at: str | None` (ISO timestamp) on `items` rows, `literature-note` and `summary-card` only.

- **Absent, not `null`, when unreviewed** — matches the existing `source_id` sparse-attribute convention `write_note` already uses (a sourceless note simply omits `source_id` rather than storing an empty value). `write_note`/`write_summary` need **zero code changes**: they already don't set it, which is exactly "unreviewed" by omission.
- **Set** by an explicit action only — `POST /items/{note_id}/review`. Never set by merely viewing a note (opening it while browsing shouldn't silently clear a queue item — reviewing is a deliberate, bounded decision, not a side effect of reading).
- **Cleared** automatically by `app/api/reconciler.py`'s existing `body_changed` detection (the `body_hash` diff Stage 1 already computes on every upsert) — a hand-edit invalidates a prior review, so the note falls back into the queue. No new detection logic; one more field added to an `update_item` call that already fires on this exact condition.
- **Un-set manually** too, via `DELETE /items/{note_id}/review` — an escape hatch for correcting an accidental "mark reviewed."

No new DynamoDB table or GSI, so `docs/schema-change-checklist.md`'s process doesn't apply here — worth stating as a deliberate scope call, not an oversight, since that checklist exists specifically for the much heavier new-table/new-GSI case.

---

## Review (building now)

"Review the graph" isn't a task, it's a mood. What actually gets done is a bounded, closable queue — grouped in ways that match how the question actually arises. All of the groupings below run against data that already exists; nothing here needs a new index.

### Data source

`GET /items/review-queue` — unreviewed items (`FilterExpression=Attr("reviewed_at").not_exists()` against the existing `recent-index` Query, same pattern `GET /items` already uses), each enriched with its own edges:

```json
{
  "items": [
    {
      "note_id": "...", "title": "...", "type": "literature-note", "tags": [...], "created_at": "...",
      "outgoing_edges": [{"edge_id": "...", "to_id": "...", "to_title": "...", "type": "RELATED_TO", "confidence": 0.72}],
      "incoming_edges": [{"edge_id": "...", "from_id": "...", "from_title": "...", "type": "EXTENDS", "confidence": 0.93}]
    }
  ]
}
```

Edge counts come from the existing `edges_table` `from_id` partition Query and `to_id-index` Query — two extra reads per unreviewed item. Bounded by however many notes are currently unreviewed, which stays small in ordinary use (you review as you go); a personal-scale tradeoff, stated here explicitly rather than left as a silent limitation. If review backlog ever grows large enough for this to matter, the fallback is a denormalized edge-count field maintained on write — not built now, since nothing today needs it.

The frontend does the grouping/labeling, not the backend — matching the precedent `GraphView.tsx` already set with its own `REVIEW_CONFIDENCE_CUTOFF` (0.85, distinct from the write-gating `EDGE_CONFIDENCE_THRESHOLD` of 0.65): the backend hands back raw counts and confidence values, the UI decides what counts as "orphan," "rising," or "worth a second look."

- **Orphan**: `outgoing_edges.length + incoming_edges.length === 0`
- **Rising** (fan-out worth a look): total edge count ≥ 3 — a candidate for a summary card before the automatic 4-notes-converge threshold fires on its own
- **Low-confidence edge present**: any edge with `confidence < REVIEW_CONFIDENCE_CUTOFF` (reuse the existing constant, don't fork a second one)

These render as badges on each queue card, not separate tabs, in this first pass — see Open Questions.

### Mutating actions

- `POST /items/{note_id}/review` → sets `reviewed_at`, returns the updated item.
- `DELETE /items/{note_id}/review` → clears it.
- Editing/rejecting a flagged edge reuses the **existing** `PATCH`/`DELETE /edges/{from_id}/{edge_id}` endpoints and the **existing** `EdgePanel.tsx` component unmodified — no new edge-mutation surface. Reviewing a note is: glance at it, resolve any flagged edges via the same panel already used from the graph view, then mark reviewed.

### Browsing by source

A second, related but distinct queue: not "what needs a decision," but "show me everything from one place I already know about" — right after an ingest, or revisiting an old one.

- `GET /sources` — new; lists all `Source` records (small table, plain scan).
- `GET /items?source_id=...` — `GET /items` gains an optional `source_id` param, switching from the `recent-index` Query to the already-existing `source-index` GSI Query (built for the Source model, never yet queried from this endpoint).

### Frontend surfaces

- `app/review/page.tsx` — flat list of `ReviewQueueCard`s (no tabs in v1; see Open Questions). Each card: `NoteCard`-style summary, edge chips color-matched to `GraphView.tsx`'s `EDGE_COLORS`, click a chip to open `EdgePanel`, "Mark reviewed" button removes the card from the local list on success (`EdgePanel`'s existing `onChanged` callback pattern, not a full reload).
- `app/sources/page.tsx` → `app/sources/[sourceId]/page.tsx` — list of sources, click into one for its notes via `NoteCard`.
- Nav: two more corner-pinned links in `GraphView.tsx`, same pattern as the existing "Upload PDFs" link (`fixed bottom-4 right-4`), not a new nav paradigm.

### Open questions (deliberately not decided yet)

- **Tabs vs. one flat list with badges.** Spec'd as one flat list for v1 — simpler to ship, and badges keep all the signal visible at once. Revisit if the queue grows long enough that filtering earns its keep.
- **Does reviewing a summary card mean anything different from reviewing a literature note?** Not addressed here — treated identically for now (same field, same endpoint). A summary card's "genuinely correct" bar might reasonably be higher (it's a synthesis, not a single extraction) — worth a second look once this ships and gets used for real.

---

## Flipping through cards *(design-level — not this pass)*

Mobile-first reading ritual: open a note, see its typed edges as a small deck beneath it, tap to jump; a breadcrumb rail records the path. A shuffle mode for serendipity. On Expo specifically, swipe right follows the strongest/most recent edge with no menu at all. Full detail, including the reasoning for mobile-first vs. web, is in the brainstorm artifact — worth returning to once Review has shipped and been used for a while, since the edge-walking data model this needs is the same one Review already touches.

## Laying cards out *(design-level — not this pass)*

Web composition ritual: a freeform drag-and-drop "desk," deliberately not force-directed, that folds into the existing selection-first `PermanentNote` writing flow rather than sitting beside it as a second panel. Savable as a MOC that remembers roughly how notes were arranged, not just which ones were linked. Highest build cost of the four ideas in the original brainstorm — a genuinely new interaction model, not a new view on existing data.

## Index cards *(design-level — not this pass)*

The second, deliberately sparse index Luhmann kept alongside the numbered slips — a keyword pointing at one or two *entry* notes, not an exhaustive list. Distinct from tags (automatic, exhaustive) by design. Proposed to double as both the app's actual "how do I get in today" home screen and a way to make review bounded ("does this note deserve to become an entry point?") rather than open-ended. Needs one new, small primitive (keyword → entry note_ids) — not a big one, but a genuinely new one, unlike Review above which needed none.
