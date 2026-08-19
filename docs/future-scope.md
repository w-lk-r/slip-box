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
- Typed relationships (SUPPORTS / CONTRADICTS / EXTENDS) as Obsidian `[[wikilinks]]` — requires a post-processing step to rewrite edge metadata as wiki-style links
- Two-way sync — edits made in Obsidian propagating back to the graph

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

## Collaborative Vaults

Multi-user knowledge graphs with shared corpora and per-user pending-edge review queues.

---

## Public Graph Sharing

Read-only shareable links to a subgraph — e.g. share the cluster of notes around a specific concept or research thread.
