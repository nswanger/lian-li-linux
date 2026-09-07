# Handoff — lian-li-linux upstream work

Last updated: 2026-08-25. Supersedes the 2026-08-24 handoff (which lived in
`/tmp` and was lost to a reboot) and the `## Handoff (2026-08-23 11:05)`
section in `NOTES.md`. Written for a fresh agent picking this up cold.

Working dirs:
- `~/Github-Repos/linux-rgb` — Nick's notes/config repo (primary cwd)
- `~/Github-Repos/lian-li-linux` — fork of `sgtaziz/lian-li-linux`
  (`origin` = `nswanger/lian-li-linux`, `upstream` = `sgtaziz/lian-li-linux`)
- `~/Github-Repos/lianli-pkg` — the PKGBUILD that builds the daily driver

## Upstream thread status (verified 2026-08-25)

| Thread | State | Next action | Owner |
|---|---|---|---|
| [PR #159](https://github.com/sgtaziz/lian-li-linux/pull/159) PKGBUILD `host-tuple` | **CLOSED** — we were wrong | none, **do not re-file** | done |
| [PR #161](https://github.com/sgtaziz/lian-li-linux/pull/161) h2 LCD write timeout | OPEN, clean, 2 s | wait for maintainer's hardware window | sgtaziz |
| [Issue #163](https://github.com/sgtaziz/lian-li-linux/issues/163) PushRgbData wedge | OPEN | keep open until the PR below lands | us |
| [PR #152](https://github.com/sgtaziz/lian-li-linux/pull/152) (Mats2208) | OPEN, 16 commits | maintainer testing ~2 weeks from 2026-08-24 | sgtaziz |
| [PR #154](https://github.com/sgtaziz/lian-li-linux/pull/154) LCD stream deadlock | OPEN | being tested with #152/#161 | sgtaziz |
| [Mats2208#1](https://github.com/Mats2208/lian-li-linux/pull/1) defer control while streaming | OPEN, filed 2026-08-25 | **waiting on Mats2208** | Mats2208 |

### The #163 → Mats2208#1 story (resolved this session)

sgtaziz answered the sequencing question on 2026-08-25: *"you can fold this
into the same PR #152 since they're more or less targeting the same core
issue."* That is not directly actionable — #152 is Mats2208's branch on his
own fork, and `maintainerCanModify` grants push to sgtaziz as base-repo
maintainer, **not to us**.

Resolution: opened `nswanger:fix/h2-defer-control-while-streaming-on-152`
→ `Mats2208:fix/hydroshift2-wired` as Mats2208#1, a single commit (`c6c01f8`,
cherry-pick of local `6a52407` onto #152 head `ce3c6e7`). If Mats merges it,
the commit lands in #152 automatically. Verified before filing: clean
cherry-pick, `cargo check` clean, `cargo test -p lianli-devices` 85 passed,
`cargo fmt --check` clean.

**If Mats goes quiet:** ask sgtaziz to push it to #152 himself — he has the
access. Do **not** retarget at `main`; `6a52407` conflicts there in
`enumerate.rs`, `h2_aio.rs` and `lcd/core.rs`. It only builds on #152.

**CI will not report on Mats2208#1.** `rust.yml` filters on
`branches: [main]`, so a PR based on `fix/hydroshift2-wired` never triggers a
run. The local results in the PR body are the only signal.

**Known gap, disclosed in the PR:** the daily-driver soak ran at the 5 s LCD
write timeout, not the 2 s now proposed on #161. The between-chunks flush
path is the part that could care. If the daily driver is ever rebuilt onto
#161 + this commit, that gap closes itself — update the PR body if so.

## Local repo state — read before touching anything

- Checked-out branch: `fix/h2-defer-control-while-streaming` at `6a52407`.
  **Leave it.**
- Installed daemon `lianli-linux-git 0.8.8.r21.g6a52407-1`, installed
  2026-08-23 10:54, is built from that branch = #152 + #154 + `6a52407`.
  It is **not** `main` and **not** the #161 branch.
- `~/Github-Repos/lianli-pkg/PKGBUILD` sources `#branch=main`. Local `main`
  carries cherry-picks of the **5 s** timeout, not the 2 s now on #161. So a
  naive rebuild does not reproduce #161.
- `6a52407` does **not** cherry-pick onto `main` — see above.

## Hard constraints

1. **Never USB-reset the AIO** (`1cbe:a034` or its xHCI controller). It locks
   the header out until a power cycle. See memory `no-usb-resets-on-aio`.
2. **Do not propose a "15 min soak at 2 s"** to validate #161. It is a null
   test — reasoning in `NOTES.md` handoff item 3. Proposed and retracted on
   2026-08-24.
3. **Do not rebuild or restart the daemon** without asking. It is a soaking
   daily driver and the soak is itself evidence.

## Environment note — `grep` is not GNU grep

The 2026-08-24 handoff claimed "plain `grep` segfaults, exit 139". That
diagnosis was wrong. Verified 2026-08-25:

- `grep` is a **shell function** injected by Claude Code's shell snapshot
  (`~/.claude/shell-snapshots/snapshot-*.sh`). It routes most invocations to
  Claude Code's own search binary (reports as `ugrep 7.8.4`) and falls back to
  `command grep` only for certain flags.
- `/usr/bin/grep` is real GNU grep 3.12 and works fine.
- Both now agree with `rg`: 174 `#[test]` matches across `crates/`.

So the hazard is **flag and regex semantics differing from GNU grep**, not a
crash. The practical advice is unchanged — **prefer `rg` or `git grep`** — but
do not repeat the segfault story, and if a result looks surprisingly empty,
cross-check with `rg` before believing it. (This is what produced the
confidently wrong "this repo has no tests" claim on 2026-08-24.)

## Durability warning

`PROTOCOL.md` is **untracked** (`git status` shows `?? PROTOCOL.md`) and
`NOTES.md` has uncommitted modifications. The main deliverable of the last two
sessions is not committed anywhere. Nick has already lost one handoff to a
`/tmp` wipe. Committing these is worth raising early.

## Open work, in priority order

1. **Reshape `PROTOCOL.md`** — Nick's explicit next step. He wants a structure
   that reads better for an LLM; concept and content are agreed. Preserve the
   confidence markings through any restructuring — distinguishing *unproven*
   from *safe* is the point of the document.
2. **Transport test seam (not started)** — see the Backlog entry in `NOTES.md`.
   `HidTransport` is a trait and mockable, `RusbBulk` is concrete, so the one
   path that keeps regressing has no test seam. Encoding the PROTOCOL.md rules
   as tests against a fake transport would make the doc executable rather than
   rot-prone.
3. **Watch Mats2208#1 and #161.** Answer whatever sgtaziz or Mats2208 reply.
4. **Graphify** — researched, not installed. Useful for doc↔code linking
   (turns `// WHY:`/`// NOTE:` comments into graph nodes), not for the
   protocol layer, which no AST can recover. Low-risk to trial; treat its
   token-saving claims as marketing.

## Suggested skills

- **`mattpocock-skills:domain-modeling`** — for item 1. Built for exactly this
  (CONTEXT.md, shared vocabulary, ADRs).
- **`mattpocock-skills:codebase-design`** — for item 2, designing the
  `BulkTransport` seam.
- **`mattpocock-skills:tdd`** — also item 2, once the seam exists.
- **`mattpocock-skills:diagnosing-bugs`** — only if the AIO wedges again. Pair
  with `diag/collect.sh` and constraint 1.

Do **not** reach for `/code-review` on #161 — it has already been through
CodeRabbit and a manual pass.

## Tone note

Nick values being told when something is wrong, including when it is our own
earlier claim. Corrections welcomed so far: #159 being unfounded, the
"undocumented" mischaracterisation of the per-URB timeout (it is documented at
`lianli-transport/src/usb.rs:210`), and the grep segfault story above.
Verify before asserting; say plainly when evidence is thin.

He will also overrule you and that is fine — he chose to keep "several days"
for a ~2 day soak in the Mats2208#1 body, having been shown the exact install
date. Flag once, then proceed.
