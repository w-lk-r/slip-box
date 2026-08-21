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
- Reconciling notes created directly in the local vault and pushed up via `aws s3 sync`, rather than through the ingestion agent — needs a sidecar/frontmatter backfill and a way to trigger classification after the fact (design notes in `docs/review-todo.md` #12)

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
