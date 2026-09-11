# Full Production-Readiness Overhaul — telemirror (MainMask fork)

## Language
- Chat replies to the user, and the step-by-step plan you present, must be in **Russian**.
- Everything written into the repository — code, comments, docstrings, commit
  messages, README/config/doc text, REVIEW.md entries — must be in **English
  only**. This includes translating text that is currently Russian (see Phase 5).
- Exception: do not touch runtime, user-facing content strings that are
  intentionally in Russian for a Russian-speaking audience (e.g. channel/brand
  names in `.configs/*.yml` such as "⚜️ Цитадель", watermark text meant for
  end viewers). If you're unsure whether a string is code/docs vs. product
  content, ask instead of guessing.

## Context
You are working in a fork of `khoben/telemirror` (production Telegram
message-mirroring bot, Telethon-based). Remotes:
- `origin` = this fork (MainMask/telemirror)
- `upstream` = khoben/telemirror

This branch is currently 101 commits ahead of `upstream/master`
(`git fetch upstream master && git rev-list --count upstream/master..HEAD`).

Read these before doing anything else — they are the project's existing rules
and prior review history, not optional background:
- `CLAUDE.md` — mandatory engineering rules for this repo. Follow them exactly.
  If any instruction below conflicts with CLAUDE.md in a way not explicitly
  pre-approved in the "Mandate" section, **stop and ask** rather than picking
  an interpretation.
- `REVIEW.md` — a module-by-module review journal from prior passes, with a
  defined checklist, severity levels (P1/P2/P3), and a stop rule. Reuse its
  checklist format and entry style for consistency with the project's own
  conventions — but see Phase 1: this pass is a **full restart**, not a
  continuation. Do not let a module's earlier "closed" status shorten or skip
  its review this time.
- `skylon_set/telemirror-review-prompt.md` — an existing read-only review
  checklist for this same fork (correctness, cleanliness, consistency,
  production readiness, docs, skylon_set audit). Reuse its checklist. Unlike
  that template, **this task is not read-only** — you are expected to fix
  what you find, not just report it.

## Mandate (pre-approved scope beyond CLAUDE.md's default "surgical changes only")
The project owner has explicitly authorized, for this pass:
- Project-wide dead-code removal (not limited to code your own edits orphaned).
- Architecture/structure refactoring where a real SOLID violation exists.
- Full English conversion of all repository text, including historical
  Russian content (REVIEW.md, skylon_set/*, config comments).
- Rewriting git history directly on `master` (squashing commits) — see
  Phase 6 for the required safety steps.

Everything else in CLAUDE.md still applies as written: no speculative
features, minimal diffs otherwise, tests before fixes, ask when unsure.

## Non-negotiable constraint
**Nothing observable may break.** Treat the existing test suite and CI as the
safety net, not a formality:
```
python -m pyflakes $(git ls-files '*.py')
python -m ruff check
python -m pytest
```
Run this full gate to confirm a green baseline *before* changing anything,
and again after every phase. If something can't be covered by automated
tests (systemd units, Docker build, install.sh), say explicitly what you
manually checked and how.

## Phase 0 — Orientation (read-only)
1. Read `CLAUDE.md`, `README.md`, `REVIEW.md` in full, `skylon_set/telemirror-review-prompt.md`,
   `.configs/*`, `deploy/README.md`, and the `tests/` listing.
2. `git fetch upstream master && git log --oneline upstream/master..HEAD` —
   list all 101 commits, then read the full diff
   (`git diff upstream/master...HEAD`) to understand what this fork changed
   and why.
3. Run the verification gate once to record the baseline.
4. Present your plan **in Russian** before editing anything, per CLAUDE.md's
   "propose a plan for non-trivial work → wait for approval" rule. Break the
   remaining phases into concrete steps with a stated verify-criterion for
   each. Pause for approval before anything that changes structure or public
   behavior.

## Phase 1 — Full-codebase audit, from zero
Review the entire tree (`telemirror/`, `skylon_set/`, `tests/`, `main.py`,
`past_mode.py`, `login.py`, `config.py`, `install.sh`, `deploy/`) as if no
prior review had ever happened. Prior REVIEW.md entries are historical
record only — they do not exempt a module from a full, independent re-read,
and a module marked "closed" in an earlier pass is not a reason to skip or
shorten this one. Apply the existing checklist: full read ×2 per module, a
regression test for every fix, pyflakes+ruff clean, P1/P2/P3 severity. Start
a new pass section in `REVIEW.md` (in English) for this restart.

## Phase 2 — Fix bugs & leaks
For every real defect (correctness bugs, connection/file-handle/memory leaks,
plausible unhandled edge cases, race conditions): write a regression test
that reproduces it first, then apply the minimal fix. Record each fix in
`REVIEW.md`, in English, following its existing entry format.

## Phase 3 — Dead code removal
Project-wide. Use ruff/pyflakes plus manual reading to find unused
functions/branches, stale one-shot scripts, commented-out blocks, unused
config keys. List everything removed in your final report.

## Phase 4 — Architecture & SOLID
Restructure only where it earns its keep. Propose the plan for any
non-trivial restructuring before touching it. Prefer the smallest change that
fixes a genuine SOLID violation over a speculative rewrite. Every
moved/split module must keep its existing tests passing (moved, not silently
rewritten, unless a test itself was wrong — flag that case explicitly).

## Phase 5 — Full English conversion
Translate every remaining Russian string in tracked files: docstrings,
comments, `REVIEW.md` (including historical entries), `skylon_set/*` headers
and CLI help text, `.configs/*.yml` comments, `deploy/README.md`, and
`skylon_set/telemirror-review-prompt.md` itself. Respect the exception in
the Language section above for user-facing product content.

## Phase 6 — Git history cleanup, on master
1. Create a backup tag at the current tip before any rebase/reset (cheap
   insurance; does not change where the new history ends up).
2. Squash the fork-specific commits (the original 101 plus whatever this
   task adds) into a coherent set of larger, logically-grouped commits, each
   with a clear English message (imperative mood, explains *why*). Land this
   directly on `master`.
3. Show the proposed commit list before force-pushing. **Do not force-push to
   `origin` until the user explicitly confirms at that point in time** — this
   overwrites already-pushed history the user may rely on elsewhere.

## Phase 7 — Production-readiness checklist
Reuse the checklist from `skylon_set/telemirror-review-prompt.md` (secrets,
`.env-example` completeness, Docker/dependency sync, logging, graceful
shutdown, README/config docs) and confirm each item explicitly.

## Phase 8 — Final report
Verification gate green. Summarize: what was fixed, what was removed, what
was deferred (P3/cosmetic) and why, and the proposed squashed commit list —
then wait for explicit go-ahead before any force-push.

## Working style
- Go step by step; don't batch unrelated phases into one giant edit.
- Use sub-agents / the `/code-review` skill for a second opinion if useful,
  but you own the final judgment and the fixes.
- If you're unsure or see multiple valid interpretations, stop and ask rather
  than guessing.
