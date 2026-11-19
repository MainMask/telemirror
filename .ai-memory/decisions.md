# Owner decisions (answers to gap-analysis questions)

Answers to the questions in `gap-analysis.md` §7, recorded one at a time as the owner gives them. These decisions are binding for `target-architecture.md` and `upgrade-plan.md`. See `HANDOFF.md` §5 for the discussion so far.

| # | Question | Decision | Status | Date |
|---|---|---|---|---|
| 1 | Single-owner tool, managed service (clients see only their project), or public multi-user SaaS? | First answer: **single owner**. The owner then raised "a service for other people right away?" and asked to restart the Q&A from the beginning. Recommended: single owner now, with a `project` column on new tables so a managed service stays cheap; a public SaaS is a separate future project. | **REOPENED** | 2026-11-19 |
| 2 | YAML or DB as the source of truth for config? | Discussed. Recommended: **A**, YAML as source of truth plus runtime data in Postgres (Postgres required on the VPS, in-memory only for tests; SQLite is the fallback option). Depends on Q1. | open | 2026-11-19 |
| 3–17 | See `gap-analysis.md` §7 | Not yet asked one by one | open | — |
