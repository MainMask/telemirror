# Original task spec (verbatim from the owner, 2026-11-19)

> The owner pasted this spec at the start of the session. It is the authoritative definition of the task. Scope clarifications given later in chat are in `HANDOFF.md` §2.

---

# Task: Upgrade my bot to match Junction Bot

## Inputs
- **Reference product:** https://www.junctionbot.io/ru/documentation/getting-started (the entire documentation, every page)
- **My project:** the current working directory

## Language rules
- **Chat with me:** Russian, always.
- **All files in `.ai-memory/`:** English.
- **Bot UI texts (messages, buttons, menus):** keep the language my current bot uses. Do not inherit it from the reference docs.

## Role
You are a senior software architect and product analyst. Break the reference product (Junction Bot) down to the level of individual features and UX, compare it with my current project, and design an upgrade that brings my bot to the same level.

## Constraints
- **Exclude everything payment-related** (plans, subscriptions, billing, payments, promo codes) from analysis and planning.
- **Do not write or modify code** until I approve the plan. This task covers research, documentation and design only.
- Build on my current project's backend: reuse what works, rebuild what blocks the target architecture.
- Copy the architecture, features, logic, UX structure and overall system 1:1. Do not copy Junction's name, logo or branding. Write UI copy in your own words, keeping the same meaning and structure.
- Tag every claim about the reference product: `[doc]` if it is stated in the documentation, `[inferred]` if it is your own deduction.

## Context management
- The docs plus my codebase will not fit in one context window. **Files are the memory, not the context.** Write each step's output to `.ai-memory/` immediately instead of keeping it in context.
- Read the site with subagents, in parallel batches of 5–10 pages. Each subagent writes its own `pages/*.md` files and returns only a short summary.
- `inventory.md` is the checkpoint. If the session is interrupted, resume from the first unread page instead of starting over.

---

## Phase 0. Study my current project
1. Walk the entire codebase: structure, stack, entry points, bot commands/handlers, data models, database, integrations, configs, deployment.
2. Build a project map: modules, what each does, and which features already exist.
3. Save it to `.ai-memory/current-project/overview.md`.

## Phase 1. Study the reference site completely
1. Start from the URL in Inputs. Collect the full list of documentation pages (navigation, sidebar, internal links). Check whether the EN version has pages missing from RU.
2. Write the list to `inventory.md` before reading anything.
3. Read **every** page in full, not as a summary. If content is JS-rendered and unreadable, switch methods (curl, headless browser) and tell me.
4. Update each page's status in `inventory.md`: read / failed / skipped (payment-related).
5. Do not proceed until every page is read. List any pages that failed.

## Phase 2. Build a knowledge base on the reference product for future AI agents
Folder structure `.ai-memory/junctionbot/`:

- `README.md`: what this is, source, crawl date, how to use it, file index
- `inventory.md`: every URL and its status
- `pages/`: one site page = one `.md` file (source URL + structured content)
- `features.md`: feature catalog (ID, name, description, location in UI, parameters, limits, relations to other features)
- `ux-flows.md`: menus, commands, buttons, screens, step-by-step user flows
- `architecture.md`: entities, data model, processes (tagged `[doc]`/`[inferred]`)
- `glossary.md`: product terminology

Requirement: an agent with no access to the site must be able to fully understand the product from this folder alone.

## Phase 3. Gap analysis: reference vs. my project
Create `.ai-memory/gap-analysis.md` with this table:

| ID | Feature | In Junction | In my bot (yes / partial / no) | Location in code | What to build/change | Effort (S/M/L) | Priority (P0–P2) |

Also describe separately:
- **UX gap**: where my bot is less convenient (navigation, number of steps, clarity, user feedback, error handling).
- **Architecture gap**: what in the current backend blocks implementing the reference functionality.
- **What I have that they don't**: keep or remove.

## ⛔ STOP. Questions for me
After Phase 3, stop and ask me all accumulated questions in a single list: contested decisions, unclear priorities, conflicts with the current architecture. Continue only after I answer.

## Phase 4. Target architecture
Create `.ai-memory/target-architecture.md`:
1. **Backend**: modules and services, DB schema, queues/background jobs, integrations, error handling, logging. Mark what is reused, refactored, or written from scratch.
2. **Bot UX/UI**: full map of screens and menus, commands, inline buttons, states (FSM), flows, message templates.
3. Mermaid diagrams: architecture, data model, key user flows.

## Phase 5. The ultimate upgrade plan
Create `.ai-memory/upgrade-plan.md`. Split the work into sequential phases so the bot stays functional after each one.

For each phase specify:
- the goal and which gap-analysis features (by ID) it closes;
- tasks with order and dependencies;
- affected files and modules;
- DB migrations (reversible);
- Definition of Done;
- how to test;
- risks and mitigations.

## Final report (in Russian)
1. How many pages were studied and which failed.
2. Top 10 biggest gaps.
3. Short plan summary: phases and their order.
4. Links to all created files.
