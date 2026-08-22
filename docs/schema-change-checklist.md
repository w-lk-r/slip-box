# Adding a New DynamoDB Table or GSI — Checklist

Retrospective from building the structured Source model (`docs/build-log.md`,
Aug 22 2026): one conceptually simple new table (`slip-box-sources`, one
GSI, one field on notes) touched **8 separate files** and needed 4 separate
deploys. Most of the time in that change went to wiring and verification,
not the actual logic. This exists so the next table/GSI goes faster.

## The full touch-point list (confirmed by actually doing it)

1. CDK table/GSI definition — `agentcore/cdk/lib/app-stack.ts`
2. CDK env var injection for the agent — `agentcore/agentcore.json`'s `envVars`
3. CDK env var injection for the API Lambda — `agentcore/cdk/lib/api-stack.ts`'s `environment` block
4. IAM grant for the agent — `app/MyAgent/policies/agent-permissions.json`
5. IAM grant for the API Lambda — inline `PolicyStatement`s in `api-stack.ts`
6. Python env var read in both runtimes — `os.environ["X_TABLE"]` in `app/MyAgent/tools/notes.py` **and** `app/api/clients.py`
7. Local dev env files — `.env`/`.env.sample` in both `app/MyAgent/` and `app/api/`
8. Whatever the actual read/write logic is (the one step that's usually genuinely quick)

**The IAM sub-resource rule bit twice this session** (once for `recent-index`, once for `source-key-index`): `dynamodb:Query` on a GSI needs the index's own ARN granted explicitly — the base table ARN alone 403s. Same pattern already correct for `edges`' `to_id-index`; just easy to forget on a new table.

**GSI creation is not instant.** Even a few-dozen-item table took several minutes to reach `ACTIVE` twice this session. Deploy the CDK change and start the next *non-dependent* piece of work rather than blocking on it — don't sequence "wait for GSI" as the very next step if there's Python/frontend code that doesn't need it yet.

## Worth doing differently next time

- **A single storage manifest, if a 4th/5th table shows up.** Not attempted this session — a one-file source of truth (e.g. `agentcore/tables.json` listing table name, GSIs, and which runtimes read it) that both the CDK stack and a small script generate the `.env.sample` files from would collapse steps 1–3 and 6–7 into one edit instead of six. Overkill for three tables; starts paying for itself around a fourth (Source-as-graph-node and PDF's content-hash index are both plausible next additions per `docs/review-todo.md` #3 and `docs/future-scope.md`).
- **`linkgen.py` duplication is a known, deliberate cost** — any frontmatter/regeneration logic change needs mirroring by hand between `app/MyAgent/tools/notes.py` and `app/api/linkgen.py` (no shared-package convention between the agent and the Lambda). This session got lucky — `_regenerate_note_links` needed zero changes in either copy. When a future change *does* touch both, diff them side by side explicitly rather than trusting memory that they're still in sync.
- **Migration scripts are hand-written every time** — three one-off backfills this session (`gsi_pk`, `GROUNDED_IN` edges, the source model). The one habit worth keeping: import and reuse real module functions (`from tools.notes import _resolve_source, ...`) inside the backfill instead of reimplementing the logic — kept the backfill provably consistent with the live code path with nothing to reconcile afterward. Worth extracting a tiny reusable "scan + transform + update" runner if a fourth backfill shows up.
- **Test-note cleanup needs three checks, not one.** Twice this session a deleted test note left a dangling reference that crashed the graph view's force-simulation on reload, because cleanup only checked outgoing edges. Before deleting any note: check outgoing edges (`from_id` query), incoming edges (`to_id-index` query), *and* whether it's listed in any summary card's `grounded_in` — all three, every time.
- **Verification this session was 100% live** — every check was a real curl, a real CloudWatch log read, a real DynamoDB query. Thorough, but a chunk of session time went into diagnosing test-harness confusion (a UTC-vs-local-date mixup, a 2000-char-truncated log line that looked like a hang) rather than the feature itself. A lightweight local test — even just "call `write_note` against a fake boto3 table/moto, assert the frontmatter shape" with no AWS round-trip — would catch Python-logic bugs before a deploy cycle, leaving live verification for true integration confidence rather than first-pass debugging.

## What already worked well — keep doing this

- **The frontmatter parser is duck-typed on structure, not content.** `_parse_frontmatter`/`_render_frontmatter` never assume what a field *means*, only whether it looks like a scalar (`key: value`) or a list block (`key:` + `  - item` lines). Adding `source: [[id|Title]]` as a new scalar field needed **zero changes** to either function. Keep any new frontmatter field fitting one of those two existing shapes rather than inventing a third, and it keeps getting this same near-zero-cost treatment.
- **Plan mode caught a real simplification before code got written**: the plan assumed `_regenerate_note_links` would need new source-handling logic; actual exploration during implementation showed `source` isn't in `EDGE_TYPE_TO_FIELD` and is simply preserved untouched by the existing loop, needing no change at all. Cheaper to discover that mid-implementation with a small correction than to have built unnecessary code from the plan as originally written.
