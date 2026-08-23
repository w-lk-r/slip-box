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
