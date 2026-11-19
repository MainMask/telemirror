# Junction Bot — reference-product knowledge base

## What this is
A self-contained description of **Junction Bot**, a commercial Telegram bot that forwards and copies messages between chats. It is the reference product for upgrading this repository (telemirror). An agent with no access to the website should be able to understand the product from this folder alone.

- **Source:** https://www.junctionbot.io (RU docs, with EN twins listed in `inventory.md`)
- **Crawl date:** 2026-11-19
- **Scope:** `documentation/*` (11), `instructions` (the index plus 26 pages), `features/*` (13) = **51 pages read**. The EN site has exactly the same set of pages as RU.
- **Excluded:**
  - payment pages (how-to-purchase-a-plan, how-to-disable-auto-renewal, how-to-top-up-balance), plus every price or billing detail inside other pages, which is marked `[payment-related content omitted]`;
  - articles, solutions, the plans page, the affiliate page and other marketing pages.
- **Note:** `features__and-more.md` is an empty template on the live site.

## Crawl history
- 2026-11-19: initial crawl. 51 pages read, 3 payment pages skipped, 0 failed. Baseline in `baseline.tsv`.
- To check for updates, run `python3 -I .ai-memory/tools/check_updates.py diff`; the procedure is in `../HANDOFF.md` §5, step 0.

## Conventions
- Everything is written in English. Original Russian UI labels are kept in parentheses, e.g. `Menu → My forwardings (Мои пересылки)`.
- Claim tags: `[doc]` means the documentation states it; `[inferred]` means it is our own deduction.
- Plan tier names (Econom / Express / Direct / Expert) may appear in pages. They only signal **capability gates** (for example, "requires a connected user account"). Pricing and billing are out of scope.
- Feature IDs follow `JB-<AREA>-NN` and are defined in `features.md`. Other files reference them by ID.

## How to use
1. Start with `features.md`: the catalog plus a summary table.
2. Use `ux-flows.md` for how a user reaches and configures each feature (menus, buttons, commands, step-by-step flows).
3. Use `architecture.md` for the entities, the data model and the processing pipeline.
4. Use `glossary.md` for terminology. For exact wording or examples, open the matching `pages/*.md`.
5. To compare with this repository, see `../current-project/overview.md` and `../gap-analysis.md`.

## File index
| File | Contents |
|---|---|
| `inventory.md` | Every crawled URL, its EN twin, crawl batch, status and page file |
| `pages/*.md` | One file per site page: source URL, full translated content, features mentioned |
| `features.md` | Feature catalog (ID, description, UI location, parameters, limits, relations, sources) |
| `ux-flows.md` | Menus, commands, buttons, screens, step-by-step user flows |
| `architecture.md` | Entities, data model, processes (tagged) |
| `glossary.md` | Product terminology (EN ↔ RU UI label) |
