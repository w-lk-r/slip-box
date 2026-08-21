# Review TODO

Open questions and design ideas to revisit before/during implementation. Not committed decisions — see `future-scope.md` once something graduates to a scoped plan.

---

## Bidirectional Obsidian/S3 sync

Currently `future-scope.md` only covers one-way `aws s3 sync` down to a local vault. Consider making it two-way so local edits in Obsidian propagate back.

- **Asymmetric merge rule needed:** body edits from Obsidian should win and flip `edited_by_user: true` on the `Item`; frontmatter connections must stay agent-generated from Neptune and never be merged back from the local copy — otherwise a stale local frontmatter re-upload could silently clobber edge state.
- **Mechanism:** `aws s3 sync` is pull/push, not push-notify, so real two-way sync needs either a local watcher (`fswatch`/`inotify`) pushing edits up on save, or a filesystem mount (`mountpoint-s3`, `rclone mount`) instead of periodic sync. Downward direction needs an S3 Event Notification → Lambda (or a cron pull) to trigger when Neptune/KB writes something new.
- **Tradeoff:** near-real-time bidirectional sync (edit in Obsidian, see it reflected within seconds) is more moving parts than the MVP scope — likely a post-MVP item, not day-one.

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

