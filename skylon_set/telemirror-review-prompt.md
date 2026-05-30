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

### Сводка
Один абзац: общее качество всех проверяемых коммитов, главные проблемы, готовность к продакшену.

### Найденные проблемы
Сортировка: сначала CRITICAL, затем MAJOR, MINOR, DOCS.

Для каждой проблемы:
```
**[SEVERITY]** `path/to/file.py` — строка N (или имя функции)
Описание: что не так
Предлагаемое исправление: конкретный код или действие
```
Уровни severity: `CRITICAL` (может сломать прод) | `MAJOR` (нужно исправить до прода) | `MINOR` (чистка, nice-to-have) | `DOCS` (пробел в документации)

### Проверено, проблем нет
Список областей, которые были проверены и не вызвали замечаний — чтобы было понятно, что они реально смотрелись.

### Чеклист готовности к продакшену
Финальный чеклист:
- [ ] Нет захардкоженных секретов
- [ ] Все env-переменные задокументированы в .env-example
- [ ] requirements.txt полный
- [ ] Зависимости совместимы с версией Python из .python-version
- [ ] Dockerfile актуален
- [ ] docker-compose.yaml актуален
- [ ] README отражает новые фичи
- [ ] Нет тихого проглатывания ошибок
- [ ] Нет debug/dead code
- [ ] skylon_scripts/ безопасны и задокументированы

### План исправлений (только если найдены проблемы CRITICAL или MAJOR)

Если в разделе "Найденные проблемы" есть хотя бы одна проблема уровня CRITICAL или MAJOR — составь пронумерованный план исправлений:

```
1. [CRITICAL] `path/to/file.py` — короткое название задачи
   Что делать: одно конкретное действие
   Риск: низкий / средний / высокий (сломает ли что-то смежное)

2. [MAJOR] `path/to/file.py` — короткое название задачи
   Что делать: одно конкретное действие
   Риск: низкий / средний / высокий
```

Порядок в плане — по приоритету: сначала CRITICAL, потом MAJOR. MINOR и DOCS в план не включать.

После плана добавь одну строку:
> Готов приступить к исправлениям по этому плану. Начать с пункта 1?

Если проблем уровня CRITICAL и MAJOR не найдено — этот раздел не выводить.

---

## Constraints

- **This is a READ-ONLY review. Do NOT edit, create, or delete any files. Report only.**
- **Do not touch upstream code** (khoben/telemirror commits) — only review what MainMask added.
- If you find something ambiguous, note it as a question rather than an assumption.
- If an issue is too risky to fix without clarification, flag it with `[NEEDS CLARIFICATION]`.
