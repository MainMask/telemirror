# HANDOFF: Junction-parity upgrade (read this first)

**Last updated:** 2026-11-19, at the end of the first session.
**Status:** Phases 0–3 are **done**. The task is **paused at the ⛔ STOP gate** (owner Q&A). The owner said: "I will implement these features later; do nothing now." **Do not start Phase 4/5 or touch code until the owner explicitly resumes.**

---

## 1. What this task is
- The owner wants telemirror (this repo) upgraded to the feature and UX level of **Junction Bot** (junctionbot.io), a commercial Telegram forwarding/copying bot.
- The full spec is in [`TASK.md`](TASK.md), verbatim. It covers: Phases 0–5, the STOP gate after Phase 3, and the final report.
- Hard rules from the spec and from the owner:
  - **Chat with the owner in Russian. Every file in `.ai-memory/` is in English. The bot's UI copy stays Russian**, as it is today.
  - **Exclude everything payment-related**: plans, subscriptions, billing, prices, promo codes, balance, affiliate.
  - **No code changes** until the owner approves the plan.
  - **No commits, branches or pushes** without an explicit "да" in the current conversation. When a push is allowed, push straight to `master`. These are standing owner rules; see `CLAUDE.md` and the user's Claude memory.
  - Copy Junction's architecture, logic and UX **1:1, but never its name, logo or branding**. Write UI copy in our own words.
  - Tag every claim about Junction `[doc]` (stated in the docs) or `[inferred]` (our deduction).
  - "Files are the memory, not the context": write results to `.ai-memory/` immediately. Use subagents for bulk reading.
- `CLAUDE.md` in the repo root applies on top of all this: think first, simplicity, surgical changes, propose a plan before coding, keep example configs (`.env-example`, `.configs/mirror.config.yml-example`) in sync with any config change.

## 2. Scope decisions made with the owner
- **Pages crawled:** `ru/documentation/*` (11), `ru/instructions` (the index plus 26 pages) and `ru/features/*` (13), **51 pages in total**.
  - The owner chose "docs + features".
  - Out of scope: articles, solutions, plans, about and other marketing pages.
- **Skipped as payment-related:** `instructions/how-to-purchase-a-plan`, `how-to-disable-auto-renewal`, `how-to-top-up-balance`.
- **EN vs RU:** the EN site has exactly the same pages as RU; nothing is EN-only.
- **`.ai-memory/` stays in the repo** (the owner's choice; not gitignored). As of this handoff it is **untracked and uncommitted**.

## 3. What was produced (all under `.ai-memory/`)
| File | What it is |
|---|---|
| `TASK.md` | Original spec, verbatim |
| `HANDOFF.md` | This file |
| `decisions.md` | Owner answers to the open questions, one row each (see §5) |
| `current-project/overview.md` | Phase 0: full map of telemirror (stack, modules, processes, panel menu tree, data model, filters, ops, feature table, limitations) |
| `junctionbot/README.md` | Index of the Junction knowledge base and its conventions |
| `junctionbot/inventory.md` | Checkpoint: 54 URLs → 51 read, 3 skipped, 0 failed |
| `junctionbot/sitemap-2026-11-19.txt` | Raw sitemap snapshot used to build the inventory |
| `junctionbot/pages/*.md` | 51 files: full English translation of each page, RU UI labels in parentheses, a "Features mentioned" list. `features__and-more.md` is an empty template on the live site |
| `junctionbot/features.md` | **181 features**, IDs `JB-<AREA>-NN` across 15 areas (ACC, FWD, TOP, HIST, FLT, PROC, AI, PUB, MOD, DIG, PROJ, INT, DIAG, CMD, UI). Includes a summary table, a settings menu map, the processing order and a list of **19 contradictions** between Junction's own pages |
| `junctionbot/ux-flows.md` | 23 commands, screen tree, 70 numbered flows (F1–F70), feedback/error patterns, 4 Mermaid diagrams |
| `junctionbot/architecture.md` | 23 entities, an [inferred] 34-table schema with an ER diagram, pipelines and state machines, limits table, 7 Mermaid diagrams |
| `junctionbot/glossary.md` | About 100 terms (EN, RU UI label, definition, feature IDs) |
| `gap-analysis.md` | Phase 3. §2: table of all 181 IDs (yes 50 / partial 55 / no 76), with code locations verified by grep. §3: top gaps. §4: UX gap. §5: architecture gap (items A1…A12). §6: what telemirror has that Junction lacks. §7: **17 open questions with recommended defaults** |
| `tools/html2md.py` | Stdlib HTML-to-text extractor used for the crawl. Usage: `curl -sL -A "Mozilla/5.0" URL -o x.html`, then `python3 -I tools/html2md.py x.html`. The site is server-rendered (Webflow), so no JS is needed. The content container is `<main class="docs-content…">` |
| `tools/check_updates.py` | `diff`: report new, removed and changed pages against `junctionbot/baseline.tsv`. `snapshot`: rewrite the baseline |
| `junctionbot/baseline.tsv` | Site baseline on 2026-11-19: URL, sitemap `lastmod`, hash of the extracted text |
| `tools/mark.py` | Marks `pending` rows in `inventory.md` as `read` when the pages file exists |

## 4. Key findings (short version)
- **Telemirror is at or above parity** on the core engine: copying and forwarding, history replay, text processing, dedup, failure tracking with replay, and ops.
- **Whole areas are missing:**
  - AI (10 features);
  - moderation (5);
  - digests (16);
  - delayed and scheduled publishing;
  - most non-keyword filters: media type, author, forwarded, own messages, time window, engagement.
- **P0 gaps:**
  - DIAG-01, DIAG-02, CMD-01: "🔎 Где копия?" / `/track`, plus recording which filter dropped a post. Today `telemirror/outcomes.py` keeps a reason only for failures.
  - FWD-03: chats can be entered only as `-100…` ids (`bot/configparse.py:11`). It should accept `@username`, `t.me` links and invite links, and the picker should show the **account's** dialogs.
  - FLT-12: media-type filter.
  - UI-02: a full forwarding-creation wizard.
- **Architecture blockers** (gap-analysis §5):
  - Config is read once at import time (`telemirror/config.py`, `CHAT_MAPPING` at line 222), so every panel save needs a restart.
  - Posts published while the mirror is down are lost: there is no catch-up.
  - There is no persistent job store or scheduler for moderation, delays or engagement filters.
  - Panel and mirror talk through files (polling about every 15 s).
  - Per-direction settings can be edited only in YAML.
  - One account per project; replay and task runs pause live.
- **Already wired but unused:** Telethon `schedule=` (`telemirror/_patch/sending.py`), so native scheduled publishing is cheap.

## 5. Where the Q&A stands (resume here)
The questions are in `gap-analysis.md` §7 (17 of them, each with a default). In chat they were presented to the owner as **16 Russian questions**: Q17 "commits" is already a standing rule, and some items were merged. The owner wants to go **one question at a time, starting again from Q1**.

What happened so far:
1. **Q1, single owner or multi-user service.**
   - The owner first answered **"single owner"** (recorded in `decisions.md`).
   - Later the owner asked: "Maybe build it as a service for other people right away?" I gave my view, summarized below.
   - The owner then said: stop, first show all missing features, then answer the questions **from the very beginning**. **Q1 is therefore REOPENED.**
2. **Q2, YAML vs database as the source of truth.** Discussed, not decided.
   - The owner asked whether Postgres is always required.
   - Answer given: no. Today there are two backends: Postgres, and in-memory (`USE_MEMORY_DB=true`, `telemirror/storage.py:262`). The in-memory store is capped at 100 messages per process and is lost on restart. The local `.env` uses in-memory; `deploy/README.md:39` assumes `postgresql.service` on the VPS.
   - New features need persistent state: moderation queue, scheduled posts, traces, catch-up. So the recommendation was **Postgres on the VPS, in-memory only for tests**. SQLite is the alternative if the owner wants no DB server, at the cost of a third `Database` backend (M effort) and write locking across processes.
   - The owner asked "A or B?". My recommendation was **A: YAML as source of truth plus runtime data in Postgres**, because:
     - a single owner gains nothing from B;
     - the YAML write path is already safe (comment-preserving, validated in a subprocess, `.bak`, conflict check);
     - YAML can be edited by hand when the panel is down;
     - it gives git history and rollback;
     - B means rewriting `telemirror/config.py` and `bot/configstore.py` / `configedit.py` / `configparse.py`, plus a migration.
   - The cost of A: a stable `id:` per direction, and per-direction panel screens that read and write YAML.
   - Not yet confirmed by the owner.
3. **The "service for other people" question** (still open; the owner must choose):
   - I advised **against a public self-service SaaS for now**:
     - it means storing other people's Telegram sessions (security);
     - userbot ban risk for users;
     - legal exposure: restrict-saving bypass and watermark removal offered as a service look like content theft;
     - it needs option B, a multi-client process model, quotas, onboarding and support: months of work;
     - payments are excluded, so all costs fall on the owner.
   - I proposed a **middle option: "managed service"**:
     - each client is a project, set up by the owner;
     - the client gets panel access only to their own project;
     - this needs per-project permissions instead of the flat `PANEL_ADMIN_IDS`, a few days' work, and keeps A and systemd.
   - The recommended path:
     - reach parity as a single-owner tool first;
     - put a `project` column in every new DB table and plan per-project panel rights, so the managed option stays cheap;
     - treat a public SaaS as a separate future project.
   - The choice was put to the owner as three options: "Только я" (recommended) / "Я + клиенты, которых я веду" / "Публичный сервис для всех". **Unanswered.**
4. After that, the owner asked to see every missing feature (the 76 "no" rows) and every partial one (the 55 "partial" rows). Both lists were shown in chat, in Russian, grouped by area, and taken from `gap-analysis.md` §2.
   - Partial rows by priority: 5 × P0 (FWD-03, DIAG-01, DIAG-02, CMD-01, UI-02), 14 × P1, the rest P2.
   - Then the owner decided **to postpone implementation** and asked for this handoff.

**Next steps when the owner resumes:**
0. **Re-check the reference site for updates first. The owner explicitly asked for this.** Then extend the memory before continuing the Q&A:
   1. Run `python3 -I .ai-memory/tools/check_updates.py diff` from the repo root. It compares the live sitemap and each page's extracted text against `junctionbot/baseline.tsv` (taken 2026-11-19: 54 URLs, the 3 payment pages included). It prints the NEW, REMOVED and CHANGED TEXT pages. Hashes were confirmed stable across repeated runs, so a change is a real content change.
      - Also look for new sections outside the scope regex. Grep the sitemap for new path prefixes, e.g. a new `/ru/<something>/` docs area. Tell the owner and ask before widening the scope.
   2. **For each NEW or CHANGED page** (payment-related pages stay `skipped (payment)`):
      - re-crawl it with the same method and page template as before (see the crawl prompt recipe in §6);
      - overwrite or add `junctionbot/pages/<section>__<slug>.md`, and add or update its row in `junctionbot/inventory.md`.
   3. **For each REMOVED page:** mark it `removed (YYYY-MM-DD)` in `inventory.md` and keep its pages file as history.
   4. **Propagate the changes:**
      - add new features to `junctionbot/features.md`, with new IDs continuing each area's numbering; never renumber existing IDs;
      - mark changed or removed features in place, e.g. `Changed 2026-xx-xx: …` or `Removed 2026-xx-xx`;
      - update `ux-flows.md`, `architecture.md` and `glossary.md` where affected;
      - add or adjust rows in `gap-analysis.md`: §2 table, per-area counts, and new open questions in §7 if any.
      - **Re-check the "yes/partial" rows against the current code** as well, since this repo may have changed too.
   5. Run `python3 -I .ai-memory/tools/check_updates.py snapshot` to move the baseline forward. Add a "Crawl history" line to `junctionbot/README.md` (date, N new / changed / removed).
   6. Tell the owner, in Russian, what changed on the site and how it affects the gap analysis. Then continue with step ½.

½. **Before any question, show the owner both feature lists in Russian. The owner explicitly asked for this.**
   - The lists are: (a) every feature **missing** in telemirror ("нет"), (b) every **partial** one ("частично").
   - Build them from the current `gap-analysis.md` §2, including any site updates from step 0; see §10 "Regenerating the Russian feature lists".
   - Group them by area. Columns: ID / function / what it does or what's missing / priority.
   - Mark anything new or changed since 2026-11-19.
   - Show the "нет" list first. Then ask whether to show the "частично" list. Then ask whether to go on to the questions.
1. Re-ask the questions **one by one from Q1**, in Russian, short. Give each question's trade-offs and a recommended default (from `gap-analysis.md` §7 and §5 above).
   - Record each answer in `decisions.md` right away, one row per question, dated.
   - Keep in mind that the answer to Q1 (single owner / managed / public SaaS) changes Q2 and most of the architecture.
2. Once every question is answered, write **Phase 4** `target-architecture.md`, then **Phase 5** `upgrade-plan.md`, exactly as specified in `TASK.md`: phases that keep the bot working after each one, feature IDs, tasks, files, reversible migrations, DoD, tests, risks.
3. Then give the **final report in Russian**: pages studied (51; 0 failed; `features/and-more` is empty on the live site), top 10 gaps, phase order, and links to all files.
4. Implementation only after the owner approves `upgrade-plan.md`. Even then: no commits without "да".

## 6. Tips for the next agent
- Don't re-crawl everything. Re-crawl only what `check_updates.py diff` reports (step 0 above).
  - Crawl recipe used on 2026-11-19: parallel general-purpose subagents, 6–10 pages each. Each one:
    - runs `curl` into its own fresh scratch dir, then `python3 -I .ai-memory/tools/html2md.py`, with WebFetch as fallback;
    - writes the **full** page (not a summary) translated to English, keeping RU UI labels in parentheses, using the template `# Title (RU title)` / Source / EN / Fetched+method / `## Content` / `## Features mentioned` (tagged [doc]) / `## Open questions`;
    - drops site chrome and related-articles blocks;
    - replaces any payment details with `[payment-related content omitted]`, but keeps functional limits ("plan-dependent");
    - returns one summary line per page.
- `features.md` and `gap-analysis.md` are large (about 1900 and 475 lines). Grep them by ID instead of reading them whole. The summary tables are at the top of `features.md` and in §2 of `gap-analysis.md`.
- **Verify code claims before relying on them.** All code references (`file:line`) in `overview.md` and `gap-analysis.md` were taken on `master` at commit **`67ae470`** with a clean working tree. Any "not committed" notes in the user's older Claude memories are stale: that work is in `67ae470`. If `master` has moved on, run `git diff 67ae470..master --stat` to see what changed, and re-verify the affected rows.
- Junction contradicts itself in places (see the end of `features.md`). Proposed resolutions are in `gap-analysis.md` §7 Q15. They are not yet approved by the owner.

## 7. Quality: what was verified and what was not
Most files were written by subagents. The main session verified only the items below, so treat the rest as good but unaudited.
- **Verified:**
  - `inventory.md`: 51 read, 3 skipped, 0 pending; the `pages/` count matches.
  - No prices leaked: grep for currency and price words across `pages/` found only regex `$1` and "BTC/USD" examples.
  - Every one of the 181 IDs appears exactly once in `gap-analysis.md` and matches `features.md`.
  - Gap-analysis claims checked by hand against the code:
    - config is read once at import (`CHAT_MAPPING`, `telemirror/config.py:222`);
    - chat refs accept only `-100…` (`bot/configparse.py:11`);
    - `schedule=` is present (`telemirror/_patch/sending.py`);
    - `outcomes.py` keeps a reason only for failures;
    - there is no catch-up code.
  - Crawl completeness, checked against the live site on 2026-11-19:
    - For all 51 pages, the word count of the English translation is 0.48–1.38× the extracted Russian text (median 0.86). The low ratios come from site chrome the subagents correctly dropped (headers, feedback-form strings); `instructions__how-to-replace-a-word…` was compared line by line and is complete. `features__ai-digests` is shorter because prices were omitted.
    - On the 5 largest documentation pages, heading counts match within 3–4. The difference is the trailing related-blog-articles block, dropped on purpose.
- **Not verified:**
  - Translation accuracy, sentence by sentence.
  - Whether every feature in `pages/` reached `features.md`. A sample-based cross-check is recommended before Phase 4.
  - The `[inferred]` reconstructions in `architecture.md` (the 34-table schema, the pipeline order beyond filters, replacements and AI) and in `ux-flows.md` (screen ordering, bot message texts). These are educated guesses, not documented facts.
  - Effort and priority estimates in `gap-analysis.md`. These are one subagent's judgement and still need the owner's input.
- **Known inconsistency:** `documentation__getting-started.md` keeps the plan tier names (Economy/Express/Direct/Expert); other pages say "plan-dependent". Both are acceptable: tiers are capability gates only, never prices.

## 8. How the owner likes to work (observed this session)
- Wants to go **one question at a time**, in order. Does not want a long list answered all at once.
- Asks "как лучше?" and expects a **clear recommendation with reasons**, plus a short pros/cons table, not a neutral survey.
- Asks clarifying "why" questions before deciding (e.g. "Is Postgres always required?"). Answer them concretely, with file references.
- May reconsider earlier answers. Q1 was reopened after the "service for other people" idea. Record answers as provisional until the owner confirms.
- Wanted to see the full missing and partial feature lists in Russian before deciding anything. Expect them to want to see the whole picture first.
- Decided to **postpone implementation**. Do not push them toward starting code.
- Standing rules (also in the user's Claude memory): replies in Russian; no commit, branch or push without an explicit "да" in the current conversation; pushes normally go straight to `master`. The exception is a separate branch for this research, which the owner asked for (see the "Branch" section once it exists).

## 9. Process lessons
- **Rate limits:** a long subagent hit the account's 5-hour usage limit mid-write. Its work so far was saved, and it was resumed with `SendMessage` to the same agent ID. Tell subagents to **write large files in chunks** (create the file, then append sections), so an interruption loses little.
- Fan-out that worked: 6 crawl subagents and 1 project-map subagent in parallel, then synthesis subagents in sequence (`features.md` + `glossary.md` → `ux-flows.md` + `architecture.md` ‖ `gap-analysis.md`). Downstream files depend on the IDs in `features.md`, so it must come first.
- Keep the main session's context light. Ask subagents for summaries of 10–20 lines, and grep the big files instead of reading them whole.

## 10. Loose ends
- **Question numbering: chat ≠ file.** The owner saw **16 questions in Russian** in chat, numbered differently from the 17 in `gap-analysis.md` §7. If the owner says "вопрос N", map it like this:

  | Chat # (RU) | Topic | `gap-analysis.md` §7 # |
  |---|---|---|
  | 1 | Single owner vs service | 1 |
  | 2 | YAML vs DB | 2 |
  | 3 | Live reload instead of restart | 3 |
  | 4 | Catch-up after downtime | 4 |
  | 5 | Publish through a bot | 5 |
  | 6 | Account per project vs per direction | 6 |
  | 7 | Delay: Telegram scheduler vs own queue | 10 |
  | 8 | AI provider/key/budget | 8 |
  | 9 | Moderation place & expiry | 9 |
  | 10 | Digests | 11 |
  | 11 | Niche (Drive, Max, Stories, script copy, feedback buttons) | 12 |
  | 12 | Generic rule filter vs class per filter | 14 |
  | 13 | Chat panel vs mini-app/web | 7 |
  | 14 | Watermark removal: develop or freeze | 13 |
  | 15 | Reference contradictions | 15 |
  | 16 | Build order | 16 |
  | — | Commits (already a standing rule, not asked) | 17 |

  When re-asking "from the beginning", use the chat order above. The owner has seen it.
- **VPS facts not verified.** This session had no access to the VPS. Assumed from the repo but unconfirmed:
  - that production runs PostgreSQL (`deploy/README.md:39`);
  - which projects and units are live;
  - the Python and Telethon versions there.
  - The local `.env` uses `USE_MEMORY_DB=true`.
  - Ask the owner, or ask them to run a check on the VPS, before relying on any of these. This matters most for Q2.
- **Site redesign trap.** `tools/html2md.py` picks `<main class="docs-content…">` (Webflow). If `check_updates.py diff` reports almost **every** page as changed, suspect a layout or markup change first. Diff one page's extracted text against its `pages/` file before re-crawling everything. If the extractor breaks (empty or garbage output), adjust its `pick()` patterns.
- **Regenerating the Russian feature lists** the owner reviewed ("нет" and "частично"): parse `gap-analysis.md` §2 rows, i.e. lines starting with `| JB-`, split on `|`, column 4 = yes/partial/no. Then translate to Russian and group by area with ID / feature / what's missing / priority. They were not saved as files, since all files here are in English.
- **Owner-facing artifacts outside the repo:** the session plan file lives under `~/.claude/plans/`, and the Claude memory note is `project_junction_upgrade.md` in the user's Claude memory dir. Both only point here; `.ai-memory/` is the source of truth.

## 11. Branch
- At the owner's request, this research lives on the branch **`junction-research`**, created from `master` at `67ae470`. The branch holds **only** `.ai-memory/`; no code changes. `master` does not contain `.ai-memory/`.
- **To resume:** `git fetch && git checkout junction-research`. Then bring in the latest code with `git merge master`, which merges cleanly because the branch touches only `.ai-memory/`. Then follow §5 step 0.
- Re-verify code references against the merged code (§6).
- Commits on this branch still need the owner's explicit "да". When implementation starts, ask the owner whether code work goes on this branch or on `master`.
