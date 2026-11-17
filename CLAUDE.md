## System Rules: Code Generation

### 1. Think Before Coding
**Don't assume. Don't hide confusion. Surface tradeoffs.**
Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

### 2. Simplicity First
**Minimum code that solves the problem. Nothing speculative.**
- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.
Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

### 3. Surgical Changes
**Touch only what you must. Clean up only your own mess.**
When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it - don't delete it.
When your changes create orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.
The test: Every changed line should trace directly to the user's request.

### 4. Goal-Driven Execution
**Define success criteria. Loop until verified.**
Transform tasks into verifiable goals:
- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"
For multi-step tasks, state a brief plan:
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.

### 5. Project Consistency
**Map the project before touching it.**
- Find existing modules, handlers, and patterns. Use them — don't duplicate them.
- Hook into existing plugin/handler mechanisms instead of building parallel infrastructure.
- Match surrounding style: naming, module layout, abstraction level.
For any non-trivial feature: read the relevant files → propose a plan (what changes, what's added, why) → wait for approval → implement.

## Project notes: control panel (`telemirror/panel`)

- Separate process (`python -m telemirror.panel`, `deploy/systemd/telemirror-panel.service`), aiogram 3.32, Bot API only — it never opens the userbot `SESSION_STRING`. No `PANEL_BOT_TOKEN` → exits 0; `main.py` does not know about it.
- Never `import config` from the panel (heavy, raises on a partial env): it reads its keys via decouple in `panel/settings.py`, like `telemirror/alert.py`.
- Config writes only via `panel/configstore.py` (`ConfigStore.update`): ruamel round-trip → PyYAML self-check → validation by `import config` in a subprocess → `.bak` → atomic replace, refused if the file changed on disk. Never write `.env`.
- Changes apply by restarting `telemirror.service` (config is read once at import). Session-exclusive work (replay, `restrict_saving`, `sync_pins`) runs only as systemd units with `Conflicts=telemirror.service`; units/flags are whitelisted in `panel/settings.py`.
- Layout: `texts.py` (all Russian UI strings), `callbacks.py` (`Nav`/`Act`, ≤64 bytes), `keyboards.py` (markup only), `routers/{start,tasks,projects,settings,maintenance}.py`, `systemd.py`, `status.py`, `ui.py` (single edited-in-place panel message), `app.py` (`build_dispatcher`).
- Tests: `tests/test_panel_*.py`; `tests/_panel.py` has a fake Bot API session / fake systemd and feeds real updates through the Dispatcher. Routers are module singletons — build the Dispatcher once per test module.
