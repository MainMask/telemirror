# Code Review: MainMask/telemirror

## Language
All output must be in **Russian**.

## Context

You are reviewing a fork of `khoben/telemirror`:
- Fork: https://github.com/MainMask/telemirror
- Original: https://github.com/khoben/telemirror
- Stack: Python, Telethon, PostgreSQL / in-memory DB, Docker

The project is **fully working in production**. Primary rule: **do not break anything**.

---

## Phase 0 — Orientation (do this first, before any analysis)

1. Run `git log --oneline` to see full commit history.
2. Identify the **fork point** (the last commit that exists in `khoben/telemirror`).
   - You can do this with: `git log --oneline khoben/master..HEAD` after adding the upstream remote:
     ```bash
     git remote add upstream https://github.com/khoben/telemirror.git
     git fetch upstream
     git log --oneline upstream/master..HEAD
     ```
3. Count and list all commits to review explicitly before proceeding.
4. Read the full diff of those commits:
   ```bash
   git diff upstream/master...HEAD
   ```
5. Read all changed files in full — do not skim.
6. Check `.python-version` and confirm all new dependencies are compatible with the specified Python version.

Do not start the review until you have a clear picture of **what changed and why**.

---

## Phase 1 — Code Quality Review (your commits only)

For each changed file/module, check:

### 1.1 Correctness & Logic
- Any bugs, off-by-one errors, incorrect conditionals
- Async/await correctness (missing awaits, blocking calls in async context)
- Exception handling: are errors swallowed silently? Are wrong exception types caught?
- Edge cases that are unhandled but plausible in production

### 1.2 Code Cleanliness
- Dead code: commented-out blocks, unused variables, unreachable branches
- Debug leftovers: `print()`, hardcoded test values, `TODO`/`FIXME` without tickets
- Inconsistent naming: variables or functions that don't follow the existing project conventions
- Magic numbers/strings that should be constants or config values

### 1.3 Consistency with the codebase
- Does new code follow the patterns established in `khoben/telemirror`?
- Are new abstractions necessary, or do they duplicate existing ones?
- Is error handling consistent with how the rest of the project handles errors?
- Are imports organized consistently?

### 1.4 Style & Formatting
- Does the code match surrounding style (even if it's not ideal)?
- Are there mixed styles (e.g., mixing f-strings and `.format()`, mixing single/double quotes)?

---

## Phase 2 — Production Readiness

### 2.1 Configuration & Secrets
- Are all new config parameters present in `.env-example`?
- Are there any hardcoded secrets, tokens, or credentials?
- Are new environment variables documented with type, default value, and description?
- Does `config.py` correctly parse and validate all new parameters?

### 2.2 Docker
- Does `Dockerfile` reflect all new dependencies?
- Does `docker-compose.yaml` cover all new services or volumes introduced?
- Are there any new files that should be in `.dockerignore`?

### 2.3 Dependencies
- Are all new imports present in `requirements.txt`?
- Are any packages pinned to an exact version when they should be (or vice versa)?
- Are there any unused imports that slipped in?
- Are all new dependencies compatible with the Python version specified in `.python-version`?

### 2.4 Logging
- Are new code paths covered by appropriate logging?
- Is log level used correctly (`debug` for verbose internals, `info` for meaningful events, `error` for failures)?
- Are there any places where errors fail silently with no log?

### 2.5 Startup & Graceful Shutdown
- Does the app still start cleanly with the new changes?
- Are there any new resources (connections, threads, file handles) that need cleanup on shutdown?

---

## Phase 3 — Documentation

### 3.1 README.md
- Are new features or config options documented?
- Are new deployment steps reflected (Docker, env vars, config files)?
- Is the `.env-example` section up to date?

### 3.2 Mirror config docs
- Is `.configs/mirror.config.yml-example` updated for any new filters or options?
- Are new `messagefilters` documented with their parameters?

### 3.3 CLAUDE.md
- Does new code follow the rules in `CLAUDE.md`?
- Specifically: no speculative abstractions, surgical changes only, no parallel infrastructure

### 3.4 Inline documentation
- Are complex or non-obvious functions documented with docstrings or inline comments?
- Do new public interfaces (classes, functions) have clear signatures and type hints?

---

## Phase 4 — `skylon_scripts/` directory

This directory appears to be custom additions. For each script:
- What does it do? Is it clear from the code and/or comments?
- Is it safe to run in production? Any destructive operations without guards?
- Should it be in `.gitignore` or has it been intentionally committed?
- Is it documented anywhere?

---

## Output Format

Structure your output as follows:

### Summary
One paragraph: overall quality of the reviewed commits, the main problems, production readiness.

### Issues found
Sorted: CRITICAL first, then MAJOR, MINOR, DOCS.

For each issue:
```
**[SEVERITY]** `path/to/file.py` — line N (or function name)
Description: what's wrong
Suggested fix: concrete code or action
```
Severity levels: `CRITICAL` (can break prod) | `MAJOR` (must fix before prod) | `MINOR` (cleanup, nice-to-have) | `DOCS` (a documentation gap)

### Checked, no issues
A list of areas that were checked and raised no concerns — so it's clear they were actually looked at.

### Production-readiness checklist
Final checklist:
- [ ] No hardcoded secrets
- [ ] Every env variable documented in .env-example
- [ ] requirements.txt is complete
- [ ] Dependencies compatible with the Python version in .python-version
- [ ] Dockerfile is current
- [ ] docker-compose.yaml is current
- [ ] README reflects the new features
- [ ] No errors silently swallowed
- [ ] No debug/dead code
- [ ] skylon_scripts/ is safe and documented

### Remediation plan (only if CRITICAL or MAJOR issues were found)

If the "Issues found" section has at least one CRITICAL or MAJOR issue, write a numbered remediation plan:

```
1. [CRITICAL] `path/to/file.py` — short task name
   What to do: one concrete action
   Risk: low / medium / high (could it break something adjacent)

2. [MAJOR] `path/to/file.py` — short task name
   What to do: one concrete action
   Risk: low / medium / high
```

Order the plan by priority: CRITICAL first, then MAJOR. Don't include MINOR or DOCS in the plan.

After the plan, add one line:
> Ready to start fixing per this plan. Start with item 1?

If no CRITICAL or MAJOR issues were found, omit this section.

---

## Constraints

- **This is a READ-ONLY review. Do NOT edit, create, or delete any files. Report only.**
- **Do not touch upstream code** (khoben/telemirror commits) — only review what MainMask added.
- If you find something ambiguous, note it as a question rather than an assumption.
- If an issue is too risky to fix without clarification, flag it with `[NEEDS CLARIFICATION]`.
