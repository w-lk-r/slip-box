# Review TODO

Open questions and design ideas to revisit before/during implementation. Not committed decisions — see `future-scope.md` once something graduates to a scoped plan.

---

## Bidirectional Obsidian/S3 sync

Currently `future-scope.md` only covers one-way `aws s3 sync` down to a local vault. Consider making it two-way so local edits in Obsidian propagate back.

- **Asymmetric merge rule needed:** body edits from Obsidian should win and flip `edited_by_user: true` on the `Item`; frontmatter connections must stay agent-generated from Neptune and never be merged back from the local copy — otherwise a stale local frontmatter re-upload could silently clobber edge state.
- **Mechanism:** `aws s3 sync` is pull/push, not push-notify, so real two-way sync needs either a local watcher (`fswatch`/`inotify`) pushing edits up on save, or a filesystem mount (`mountpoint-s3`, `rclone mount`) instead of periodic sync. Downward direction needs an S3 Event Notification → Lambda (or a cron pull) to trigger when Neptune/KB writes something new.
- **Tradeoff:** near-real-time bidirectional sync (edit in Obsidian, see it reflected within seconds) is more moving parts than the MVP scope — likely a post-MVP item, not day-one.

