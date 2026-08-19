# Future Scope & Enhancements

Ideas and enhancements explicitly out of scope for the hackathon MVP but worth building after submission.

---

## Obsidian / Markdown Export

Export the knowledge graph as a local vault of `.md` files compatible with Obsidian and other markdown-based tools.

- Each `Item` and `PermanentNote` becomes an atomic `.md` file
- Typed relationships (SUPPORTS / CONTRADICTS / EXTENDS) represented as Obsidian `[[wikilinks]]` with inline relationship labels
- Confidence scores and edge metadata written as YAML frontmatter
- Vault can be synced locally or via S3 → local sync tool (e.g. `rclone`)
- Stretch: two-way sync — edits made in Obsidian propagate back to the graph

**Why deferred:** AgentCore Runtime is cloud-hosted and can't write to a local filesystem. S3 as the vault store adds sync complexity that competes with the hackathon deadline. The graph UI tells the demo story better for judges. Framed in the pitch as "export to Obsidian" future work.

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
