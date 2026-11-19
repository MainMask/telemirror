# Gap analysis: Junction Bot (reference) vs telemirror

Date: 2026-11-19. Author: architecture review agent (research only; no code changed).

## 1. Header

**Purpose.** Compare every feature of the reference product Junction Bot (a commercial Telegram forwarding bot plus mini-app) with what the owner's project **telemirror** does today: a Telethon userbot engine in `telemirror/`, an aiogram control-panel bot in `bot/`, and systemd deployment in `deploy/systemd/`. For each feature the analysis records whether telemirror has it, where it lives in the code, and what building it would take. Sections 4–7 cover the UX gap, the architecture blockers, the strengths only telemirror has, and the questions the owner needs to answer.

**Inputs**
- `.ai-memory/junctionbot/features.md`: 181 reference features `JB-<AREA>-NN`, the summary table, the settings map, the pipeline order and 19 contradictions. Most details were checked in this file; the `pages/*.md` were not needed beyond it.
- `.ai-memory/junctionbot/glossary.md`.
- `.ai-memory/current-project/overview.md`: map of the repo at `master` 67ae470 plus uncommitted work.
- **The actual code.** Every *yes* or *partial* row was checked by grep/read against the repo and cites a real path. Spot checks confirmed overview.md (for example: `config.py` builds `CHAT_MAPPING` at import, lines 222–344; `build_filters` uses `getattr(messagefilters, name)`; `bot/texts.py:221` `SAVED` tells the user to press restart; `bot/configparse.py:11` accepts only `-100…[#topic]` refs; `mirroring.py:2213` registers `NewMessage(chats=…)` without `incoming=True`; there is no `catch_up` anywhere).

**Legend**
- *In my bot*: **yes** = equivalent capability exists (it may work differently). **partial** = some of it exists, or it exists only via YAML/CLI, or with narrower options. **no** = absent.
- *Effort* (to reach reasonable parity in telemirror): **S** ≤ 1 day, **M** 2–5 days, **L** > 1 week. "—" = nothing to build (parity or deliberately not applicable).
- *Priority*: **P0** = core to parity or blocks other features. **P1** = important. **P2** = nice-to-have, niche, or probably not wanted for a single-owner tool.
- *In Junction* tags: **[doc]** = stated in the docs. **[inferred]** = deduced by the KB author. **[matrix]** = appears only in the plan-comparison matrix.

**Scope notes**
- **Payment features are excluded**: plans, billing, balance, promo codes, affiliates. Tier gates appear in the reference only as capability gates and are ignored here.
- **Multi-tenant SaaS is a decision point, not an assumption.** Junction serves many customers: each managing account owns its own forwardings, connected accounts and quotas, and Junction also runs its own service userbot (ACC-08), a support/help bot (DIAG-10), per-user language (INT-04) and per-user AI quotas (AI-07). telemirror is a **single-operator** tool (`PANEL_ADMIN_IDS` in `.env`, every admin can do everything). Rows that only make sense for multi-tenant SaaS are marked P2 with "SaaS-only". The decision itself is open question Q1.
- A *Junction "forwarding"* (one source→destination rule with all its settings) corresponds roughly to one telemirror *direction* (`directions:` item in the mirror YAML, `DirectionConfig` in `telemirror/directions.py`). One direction can have N sources × M targets. A *Junction project* is only a grouping label. A *telemirror project* (`telemirror/projects.py`) is much heavier: one config, one account session, three systemd units and one process.

## 2. Main table

Columns: `| ID | Feature | In Junction | In my bot | Location in code | What to build/change | Effort | Priority |`

### 2.1 ACC — Accounts & connection (yes 4 / partial 4 / no 2)

| ID | Feature | In Junction | In my bot | Location in code | What to build/change | Effort | Priority |
|---|---|---|---|---|---|---|---|
| JB-ACC-01 | Account connection | Bot logs into the user's Telegram account as a client and sees every chat it is in [doc] | yes | `telemirror/live.py`, `telemirror/misc/telegram_client.py` (`build_telegram_client`), `sessions/*.jsession` via `telemirror/misc/jsession.py` | — (telemirror is account-first by design) | — | — |
| JB-ACC-02 | Login flow (phone + code) | Phone → 5-digit code in the Telegram app → done; 2FA not documented [doc] | yes | `bot/routers/accounts.py` (`acc_login`, `Login.phone→code→password`, 2FA at line ~330), `telemirror/login.py` CLI, `bot/pending.py` (`Login`) | — (also has tdata/.session import, which Junction lacks) | — | — |
| JB-ACC-03 | Managing vs connected account | The account that talks to the bot differs from the account(s) that read/publish [doc] | yes | `PANEL_ADMIN_IDS` (`bot/settings.py`, `bot/middlewares.py:AdminOnly`) vs `sessions/` accounts (`bot/sessions.py`) | — (single-operator form of the same split) | — | — |
| JB-ACC-04 | Multiple accounts / split load | Several connected numbers; each forwarding bound to one reader account [doc] | partial | `telemirror/projects.py` (`Project.session`), `bot/routers/projects.py` (account change), `bot/turns.py` (projects sharing a session run in turn) | The account is bound per **project**, not per direction, and projects on one session can't run at once. Allow a per-direction reader/sender account, or keep "one account = one project" and document it (Q6) | L | P2 |
| JB-ACC-05 | Change connected number | Swap the phone on a connection [doc] | yes | `bot/routers/projects.py` (👤 Аккаунт → `account` input), `telemirror/projects.update_project` | — | — | — |
| JB-ACC-06 | Reconnect dead session | "Reconnect" next to a broken session [doc] | partial | Ban/revoke → CRITICAL log → `NoticeLogHandler` (`mirroring.py:2063`) + `telemirror/alert.py`; re-login via 🔑 Войти по номеру (`bot/routers/accounts.py`) | Detect `AuthKeyUnregistered`/revoked and mark the account card "⛔ сессия недействительна" with a one-tap "🔑 Войти заново" that re-signs the same phone into the same `.jsession` and restarts its projects | S | P1 |
| JB-ACC-07 | Service channel | Bot auto-creates a channel on the account for service messages [doc] | no | — | Not needed: notices go through the panel bot (`telemirror/notify.py`). Keep as is | — | P2 |
| JB-ACC-08 | Service user-bot (no-account tiers) | Junction's own userbot joins public sources for customers without an account [doc] | no | — | SaaS-only. Not applicable to a single-owner tool (Q1) | L | P2 |
| JB-ACC-09 | Account / settings transfer | Move a number or all settings to another managing account [doc] | partial | 📥/📤 config file (`bot/routers/config_file.py`), session upload (`bot/routers/accounts.py`), `PANEL_ADMIN_IDS` in `.env` | Enough for one owner. Optionally add an "export whole project" ZIP (project.yml + YAML + chats.json, no session) | S | P2 |
| JB-ACC-10 | Security & login warnings | Official protocol; "unknown device" warning expected [doc] | partial | Telegram Desktop fingerprint `TDESKTOP_APP` (`telemirror/misc/jsession.py`), 0600 session files, `session_lock.py`; README warning about bans | Add a one-paragraph "what to expect after login / ban risks" text on the 🔑 login screen (`bot/texts.py`) | S | P2 |

### 2.2 FWD — Forwarding core (yes 8 / partial 7 / no 5)

| ID | Feature | In Junction | In my bot | Location in code | What to build/change | Effort | Priority |
|---|---|---|---|---|---|---|---|
| JB-FWD-01 | Forwarding rule | One source→destination pair with all settings [doc] | yes | `directions:` in YAML → `DirectionConfig` (`telemirror/directions.py`), `telemirror/config.py:296-344`; panel `bot/routers/directions.py` | Rules are YAML items, not DB entities, and changes need a restart. See §5 A1/A3 | — | — |
| JB-FWD-02 | Source classes | Public / invite-link / protected / closed; tier-gated [doc] | partial | Any channel/group/topic the account is a member of (`EventHandlers`, `mirroring.py:2213`); protected via `RestrictSavingContentBypassFilter` | Bots, private chats with users and folders can't be sources (refs must be `-100…`, `bot/configparse.py:11`). Allow user/bot ids as sources if wanted | M | P2 |
| JB-FWD-03 | Source & destination lookup | Search by link / @username / invite link, or pick from the account's chat list [doc] | partial | `-100…[#topic]` id, forwarded post, `📇 Выбрать из списка` = Bot API `request_chat` of the **admin's** chats (`bot/middlewares.py:ChatPicked`, `bot/keyboards/menu.py:chat_picker`) | Accept `@username`, `t.me/...` and `t.me/+invite` links: resolve them with the project's account (joining for invites), and add a picker over the **account's** dialogs (from `chats.json` / `get_dialogs`). This is the main friction when adding a direction | M | P0 |
| JB-FWD-04 | Destinations | Bot chat feed, channels, groups, users, bots, Max [doc] | partial | Channels, groups, forum topics (`to:` in YAML) | Users/bots as targets (FWD-05) and a feed in the panel chat (TOP-09) are missing. Max is out of scope (Q9) | M | P2 |
| JB-FWD-05 | Forwarding to users/bots | Account-mode delivery into DMs and third-party bots [doc] | no | — | Relax `_CHAT_REF_RE` to accept positive user/bot ids; check that `send_message`/reply/topic logic handles a user peer | S | P2 |
| JB-FWD-06 | Max messenger destination | Publish into a Max chat (Expert) [doc] | no | — | Out of scope unless the owner needs it (Q9) | L | P2 |
| JB-FWD-07 | Copy vs native forward | Clone (editable) vs Telegram forward (immutable) [doc] | yes | `mode: copy\|forward` (`config.py:_validate_mode`), `_do_send` in `mirroring.py:~1242`; panel ↔️ Режим (`bot/routers/params.py`) | Per-direction mode is editable only by hand in YAML. Expose it on the direction card | S | P1 |
| JB-FWD-08 | Delivery latency | Tier-dependent, ~1–2 s for account tiers [doc]/[matrix] | yes | Live updates via Telethon handlers (`mirroring.py:2213`), album wait 1.01 s (`_patch/album.py`) | — (risk: posts missed during downtime, §5 A6) | — | — |
| JB-FWD-09 | Forward edits | edit / new / ignore [doc] | partial | `disable_edit` (`DirectionConfig`), `EventProcessor.edit_message` (`mirroring.py:1662`); panel ✏️ Правки (`params.py`, project-wide) | Add the "new" mode (send the edited version as a new post) if wanted; make the setting per direction in the panel | S | P2 |
| JB-FWD-10 | Forward deletions | yes / no [doc] | yes | `disable_delete`, `EventProcessor.delete_message` (`mirroring.py:1959`); panel ✂️ Удаления | Per direction only by hand in YAML | — | P1 |
| JB-FWD-11 | Media forwarding | All media types by default [doc] | yes | `send_file`/`send_message` copy in `mirroring.py`, albums `new_album` (`mirroring.py:1348`), quiz→poll | — | — | — |
| JB-FWD-12 | Copy original buttons | none / url / special / all [doc] | no | Copy passes `message.reply_markup` verbatim (`telemirror/_patch/sending.py` ~l.267), but Telegram ignores inline markup sent by a user account | Only possible if a **bot sends** (§5 A10). Otherwise render URL buttons as text links (a filter) | M | P2 |
| JB-FWD-13 | Notification ("hidden continuation") buttons | Bot presses callback buttons and copies the pop-up text [doc] | no | — | Niche. Could press via `GetBotCallbackAnswerRequest` and append the text | M | P2 |
| JB-FWD-14 | Polls | none / copy / link under custom text [doc] | partial | Polls copied, quizzes turned into plain polls (`mirroring.py:_new_message_impl` ~l.1124) | Add a "skip polls" option (part of the media-type filter FLT-12) | S | P2 |
| JB-FWD-15 | Stories | message / ignore [doc] | no | — | Niche for channel mirroring; would need a story poller (`stories.GetPeerStories`) | M | P2 |
| JB-FWD-16 | Comments | Copy discussion-group comments as posts or as comments [doc] | partial | A discussion group can be an ordinary source group (posts mode works) | "As comments" needs mapping a channel post → its discussion thread in the target (`binding_id` lookup + `reply_to` the auto-forwarded copy). Possible on top of the existing reply chaining | M | P2 |
| JB-FWD-17 | Premium long captions | >1024-char captions need account + Premium [doc] | yes | Account sends captions as is; `MediaCaptionTooLongError` → `_send_with_caption_split` (`mirroring.py:878`) | — (tail text is untracked for edit/delete; known limitation) | — | — |
| JB-FWD-18 | Premium emoji | Passed in account mode with Premium [doc] | yes | Entities copied as is (`formatting_entities=…`, `mirroring.py:~1250`; `mixins.py:CopyEventMessage`) | — | — | — |
| JB-FWD-19 | Protected (copy-restricted) sources | Copy from noforwards chats [doc] | yes | `RestrictSavingContentBypassFilter` (`messagefilters/restrictsavingfilter.py`), `_media.py` re-upload, noforwards gate `mirroring.py:~545` | Make it automatic: when a source is `noforwards` and mode is copy, apply the bypass without a hand-added filter (or have the panel offer it in one tap) | S | P1 |
| JB-FWD-20 | Chaining via intermediate channels | Compose A→C→B rules [doc] | partial | Probably works: the `NewMessage(chats=…)` handler also gets the account's own outgoing posts (`mirroring.py:2213`), so a target that is also a source re-fires [inferred, untested] | Test it and document it; check that `already_mirrored` and `dedup_hours` don't block the second hop | S | P2 |

### 2.3 TOP — Topics, folders & feeds (yes 3 / partial 3 / no 4)

| ID | Feature | In Junction | In my bot | Location in code | What to build/change | Effort | Priority |
|---|---|---|---|---|---|---|---|
| JB-TOP-01 | Topic mapping | Source topic → destination topic table [doc] | yes | `-100…#topic` refs (`config.py:_parse_chat_topic`), `EventProcessor._matches_from_topic` (`mirroring.py:524`), `misc/topics.py`, `_patch/sending.py` (`reply_to_topic_id`) | Works but is typed by hand as `#id`. A visual "topic mapping" screen listing source topics (by name) → target topics is missing (UX §4) | M | P1 |
| JB-TOP-02 | Catch-all topic rules | "All topics" / "All other topics" → General [doc] | partial | A source without `#topic` matches all topics (`_matches_from_topic`). No "all *other* topics" | Add an `others` rule: the direction matches topics no explicit direction of the same pair matches | S | P2 |
| JB-TOP-03 | Copy topic structure | Bot creates same-named topics in the destination [doc] | partial | CLI-only, hard-coded Citadel wizard: `telemirror/tasks/setup_mirrors.py` (`CreateForumTopicRequest`, l.250) | Generic task "copy topic structure" (source forum → target forum, writes the mapping into YAML), run from the panel as a `telemirror-task@` tool with dry-run | M | P1 |
| JB-TOP-04 | Create topic in mapping | Create the destination topic inline [doc] | no | — (only inside `setup_mirrors.py`) | Part of the TOP-01 screen: "➕ Создать тему" via the project's account | S | P2 |
| JB-TOP-05 | Many sources → topics | One rule per source, each to a topic [doc] | yes | Multiple directions with `to: ["-100…#N"]` | — | — | — |
| JB-TOP-06 | Topic auto-sync | Auto-create/rename destination topics [doc] | no | — | Handle `MessageActionTopicCreate/Edit` service messages in `new_message` (currently skipped as service, `mirroring.py:~1100`) → create/rename the target topic and the mapping. Needs a runtime-mutable mapping (§5 A1) | M | P2 |
| JB-TOP-07 | Folder as source | Telegram chat folder = live set of sources [doc] | no | — | Read `messages.GetDialogFilters`, expand into sources, re-read on `UpdateDialogFilter`. Needs a runtime-mutable mapping (§5 A1) | M | P2 |
| JB-TOP-08 | Folder vs direct dedup | A message is sent once; the explicit rule wins [doc] | partial | Per-target dedup `already_mirrored` via `binding_id` (`mirroring.py`), `dedup_hours` fingerprints (`telemirror/dedup.py`) | Only relevant once folders exist | S | P2 |
| JB-TOP-09 | Own feed in bot chat | Send @name to the bot and read the source in the bot chat [doc] | no | — | Would need bot-as-sender (§5 A10). Low value for a mirror tool | M | P2 |
| JB-TOP-10 | Feed channels | Aggregated channel from many sources [doc] | yes | N→1 directions (`from:` list) in YAML | — | — | — |

### 2.4 HIST — History copying (yes 5 / partial 4 / no 1)

| ID | Feature | In Junction | In my bot | Location in code | What to build/change | Effort | Priority |
|---|---|---|---|---|---|---|---|
| JB-HIST-01 | History copying | Copy already-published messages in the background [doc] | yes | `telemirror/past.py` (`telemirror-past@`), checkpoints in `past_mode_checkpoint` (`telemirror/storage.py`); panel ⏪ История (`bot/routers/replay.py`) | — | — | — |
| JB-HIST-02 | Interval type | All / message-id range / publication-time range [doc] | partial | `past_mode`: `full_history`, `last_n`, `since_date` (`telemirror/directions.py:PastModeConfig`, `past.py`); panel 📜 Что копировать | Add `until_date` and `min_id/max_id` (an id range, including a single message). `iter_messages(min_id, max_id, offset_date)` already gives this | S | P1 |
| JB-HIST-03 | History delivery mode & sender | Bot / account / account with bot fallback on flood [doc] | partial | Account only, copy or forward per direction mode | Bot fallback only if bot-as-sender is adopted (§5 A10) | M | P2 |
| JB-HIST-04 | Remove safe pause | Turn off throttling [doc] | yes | `past_mode.send_delay` (can be 0); panel ⏱ Пауза при копировании (`replay.py:rpl_delay`) | — | — | — |
| JB-HIST-05 | Error handling policy | Ask / Skip / Wait and retry [doc] | partial | Fixed policy in `past._replay_with_retry`: FloodWait → sleep and retry (give up after 20); MediaDownloadError → 5 retries then skip and notify | Make the policy selectable (skip / wait / stop and ask), and write skipped posts into `failed.json` so they can be retried (today replay has no failed list, overview §9) | S | P1 |
| JB-HIST-06 | Start & progress | "Let's go" + a progress message [doc] | yes | `replay.py` (progress line grepped from the journal), `bot/watcher.py` finish notices | — (an ETA % bar would be nice) | — | — |
| JB-HIST-07 | Copy by script | Replay a chat with each author's own account and the original pauses [doc] | no | — | Niche ("group warm-up"). Needs several sessions in one process. Skip unless wanted | L | P2 |
| JB-HIST-08 | History with forwarding settings | History copy applies the forwarding's filters [doc] | yes | `past.py` uses the same `EventProcessor` and direction filters | — | — | — |
| JB-HIST-09 | Topic-specific history | Copy only chosen topics [doc] | yes | Topic directions included in past pairs (`past.py`, `_matches_from_topic`) | — | — | — |
| JB-HIST-10 | History limits & recovery | Retry stuck/single messages by id range [doc] | partial | Checkpoint resume, FloodWait/media retry (`past.py`), `clear_channels` reset (`tasks/clear_channels.py`) | Single-message re-copy comes with the id range in HIST-02; ♻️ retry of replay skips with HIST-05 | S | P2 |

### 2.5 FLT — Filters (yes 4 / partial 5 / no 10)

| ID | Feature | In Junction | In my bot | Location in code | What to build/change | Effort | Priority |
|---|---|---|---|---|---|---|---|
| JB-FLT-01 | Filtering overview | Per-forwarding unlimited rules of many types [doc] | yes | `telemirror/messagefilters/*`, `CompositeMessageFilter` (`base.py:103`), project list + per-direction lists (`bot/routers/filters.py`, `bot/filtercatalog.py`) | Filters are **code classes with YAML args** (§5 A3). New filter types need code | — | — |
| JB-FLT-02 | mustHave / mustNotHave logic | OR within a type, AND across types, any type can veto [doc] | partial | `AllowWithKeywordsFilter` (pass only with ≥1 keyword) + `SkipWithKeywordsFilter`/`SkipWithUrlFilter`/`SkipUrlFilter`, chained as AND in list order (`messagefilters.py:632-684`) | Equivalent for keywords. Not generalized to the other criteria (author, media, time…). A rule engine (§5 A3) would give this uniformly | M | P1 |
| JB-FLT-03 | Text-match filter | Exact case-sensitive substring [doc] | yes | `SkipWithKeywordsFilter`/`AllowWithKeywordsFilter`: whole-word, case-insensitive literal (`messagefilters.py:19-32`) | Semantics differ (whole word, case-insensitive), which is arguably better. Add a "substring" flag only if asked | — | — |
| JB-FLT-04 | Regex filter | Java-8 regex over text + media tokens [doc] | yes | `r'…'` keywords → Python `re` (`messagefilters.py:_compile`) | No media tokens (see FLT-12) | — | — |
| JB-FLT-05 | Word-form filter | Morphological match RU/EN/UK/DE (add-on) [doc] | no | — | `pymorphy3` (RU/UK) + `snowball` stemmer (EN/DE) as a `lemmas: true` flag on the keyword filters. Footprint OK for 1 vCPU | M | P2 |
| JB-FLT-06 | Date/time filter | Weekday + time window + TZ [doc] | no | — | New `TimeWindowFilter(days, from, to, tz)` (pass/skip), with the panel editor as a new arg kind in `filtercatalog.FILTER_ARGS` | S | P1 |
| JB-FLT-07 | Delayed (engagement) filter | Hold a post; publish if it reaches min reactions/views/forwards/replies [doc] | no | — | Needs a persistent **job queue/scheduler** (§5 A7): store the pending post, re-fetch it at T1/T2 (`get_messages` → `views`, `forwards`, `reactions`, `replies`), then publish or drop | L | P1 |
| JB-FLT-08 | Engagement-ratio thresholds | Reactions/forwards/replies per view [doc] | no | — | Comes with FLT-07 (same check function) | S | P2 |
| JB-FLT-09 | Filtering order | after reception / after replacements / after AI [doc] | partial | The chain order is user-controlled (⬆️ Выше / ⬇️ Ниже, `bot/routers/filters.py`); placement rules `EARLY_FILTERS` (`bot/filtercatalog.py`) | Already more flexible than Junction's three presets. Needs an AI step to matter fully (AI-01) | — | P2 |
| JB-FLT-10 | Author filter | Pass/stop by numeric author id [doc] | no | — | `SenderFilter(ids, mode)` on `message.sender_id` / `post_author` (signatures). Important for groups as sources | S | P1 |
| JB-FLT-11 | Own messages filter | pass / filter the connected account's own messages [doc] | no | Handler gets outgoing messages too (`mirroring.py:2213`, no `incoming=True`) | `skip_own: true` flag (check `message.out`). Also prevents loops in chains (FWD-20) | S | P1 |
| JB-FLT-12 | Media-type filter | `<photo>`, `<video>`, … tokens [doc] | no | — | `MediaTypeFilter(allow\|skip: [photo, video, document, audio, voice, sticker, gif, round, poll, location, text_only])`. Cheap and very commonly needed | S | P0 |
| JB-FLT-13 | Forwarded-messages filter | all / direct only / forward only [doc] | no | — | `ForwardedFilter(mode)` on `message.fwd_from` | S | P1 |
| JB-FLT-14 | Every n-th message | Forward every N-th message [doc] | no | — | Counter per (direction, source) held in the filter instance (lost on restart, acceptable) | S | P2 |
| JB-FLT-15 | Duplicate filter | pass / filter / only_duplicates (300-message memory) [doc] | partial | `dedup_hours` cross-source fingerprints (`telemirror/dedup.py`, `post_fingerprint` in `storage.py`, `EventProcessor._is_repeat` `mirroring.py:267`); panel 🧬 Без повторов | No `only_duplicates`; re-uploaded media aren't detected (different file ids). Add `only_duplicates` if a use case appears; consider a perceptual hash for photos | S | P2 |
| JB-FLT-16 | AI filtering | AI marks irrelevant posts and a text filter drops them [doc] | no | — | `AiClassifyFilter(prompt, labels→action)` returning DISCARD directly (no marker-word trick). Depends on the AI layer (§5 A8) | M | P1 |
| JB-FLT-17 | Bulk import of filters | Import many filters from a table [doc] | partial | Many items per message, one per line (`bot/configparse.py:parse_filter_items`); whole-config 📤 upload (`bot/routers/config_file.py`) | Good enough. Optionally accept a CSV/TXT file into a keyword list | S | P2 |
| JB-FLT-18 | Copy filters between sources | `/filter <dst> addAllFrom <src>` [doc] | partial | Adding a filter to a direction copies the project list first (`bot/routers/filters.py`) | "📋 Скопировать фильтры из направления…" on the direction filter screen (`configedit` op) | S | P2 |
| JB-FLT-19 | Filters for all sources | Add/remove a filter on all sources [doc] | yes | The project-wide `filters:` list applies to every direction without its own list (`config.py:292-304`) | — | — | — |

### 2.6 PROC — Text & message processing (yes 9 / partial 6 / no 5)

| ID | Feature | In Junction | In my bot | Location in code | What to build/change | Effort | Priority |
|---|---|---|---|---|---|---|---|
| JB-PROC-01 | Copy-only prerequisite | Processing only in copy modes [doc] | yes | `_validate_forward_filters` + `_CONTENT_MUTATING_FILTERS` (`telemirror/config.py:59-86`) | — | — | — |
| JB-PROC-02 | Add header | Prepend text/HTML [doc] | yes | `ForwardFormatFilter(format="HEADER\n{message_text}")` (`messagefilters.py:239`); panel "Подпись с источником" | A dedicated "Заголовок/Подвал" pair of fields would be clearer than a format string (UX) | S | P2 |
| JB-PROC-03 | Footer | Append text/HTML [doc] | yes | Same `ForwardFormatFilter` (`{message_text}\n\nFOOTER`) | Same as PROC-02 | — | P2 |
| JB-PROC-04 | Text trimming | Cut to N characters [doc] | no | — | `TrimFilter(max_chars, ellipsis)` with entity clipping (reuse `UpdateEntitiesParams`, `mixins.py`) | S | P2 |
| JB-PROC-05 | Replacements | Ordered A→B rules on body and buttons [doc] | yes | `KeywordReplaceFilter` (`messagefilters.py:451`), entities shifted; panel map editor (`bot/routers/filters.py`) | Order follows YAML dict order. No buttons (FWD-12) | — | — |
| JB-PROC-06 | Regex replacements | RE flag, `$1` backrefs [doc] | yes | `r'…'` keys with group refs validated (`messagefilters.py:~464-480`) | — | — | — |
| JB-PROC-07 | Formatting via HTML | Add/remove tags via replacements [doc] | partial | Replacements work on plain text and keep entities (`KeywordReplaceFilter`); markdown in `ForwardFormatFilter` header/footer | Allow the replacement value to carry markdown/HTML (parse with Telethon's `html.parse` and merge the entities) | M | P2 |
| JB-PROC-08 | Premium emoji codes | Insert/replace premium emoji via `documentid` codes [doc] | partial | Custom-emoji entities survive copy (`formatting_entities`) | Support `<tg-emoji emoji-id=…>` in header/footer/replacement values (with PROC-07) | S | P2 |
| JB-PROC-09 | Link replacement recipes | Remove/replace `<a>` links, plain URLs, @usernames [doc] | yes | `UrlMessageFilter` (placeholder, black/whitelist, mentions; `messagefilters.py:101`), `SkipWithUrlFilter`, `StripFooterFilter` (`messagefilters.py:564`), `misc/urlmatcher.py` | — (richer than Junction's regex recipes) | — | — |
| JB-PROC-10 | Replace cross-links with source | Auto-rewrite links to the source [doc] | yes | `EventProcessor._rewrite_links` (`mirroring.py:461`) → own mirror via `binding_id`, else `fallback_link_url`; `past._edit_links_pass` | — (stronger: links point to the mirrored copy) | — | — |
| JB-PROC-11 | Link to original post | none / full / custom text [doc] | yes | `{message_link}` in `ForwardFormatFilter` (`mixins.py:MessageLink`) | — | — | — |
| JB-PROC-12 | Source name | none / simple / bold / from_only / id / date / custom [doc] | partial | `{channel_name}` (`mixins.py:ChannelName`), `MappedNameForwardFormat` (custom names, YAML-only) | Add `{date}`, `{message_id}`, `{origin_name}` (the original source of a forwarded post, `fwd_from`); edit `MappedNameForwardFormat` in the panel | S | P2 |
| JB-PROC-13 | Author | none / name / username / full [doc] | partial | `{sender_title}`, `{sender_username}` placeholders (`messagefilters.py:239-260`) | Add `{author}` = post signature (`post_author`) and a profile link for groups | S | P2 |
| JB-PROC-14 | Own URL buttons | URL + label per line [doc] | no | — | A user account can't send inline keyboards. Needs bot-as-sender (§5 A10), or emulate with text links in the footer (already possible) | M | P2 |
| JB-PROC-15 | Feedback buttons | 👍/👎 or custom words [doc] | no | — | Bot-only (callback buttons + counters store). Out of scope without A10 | M | P2 |
| JB-PROC-16 | Media caption mode | separate / caption_name / text_only [doc] | partial | Automatic split only when the caption is too long (`_send_with_caption_split`, `mirroring.py:878`) | `CaptionModeFilter(separate\|text_only\|media_only)`; `text_only` drops the media, `media_only` drops the text. Small | S | P2 |
| JB-PROC-17 | Watermarks (apply) | Overlay an uploaded watermark on images/video/animation [doc] | yes | `WatermarkRemovalFilter(stamp_watermark=True, …)` (`messagefilters/watermarkfilter.py:58`), `watermark/processor.py` (PIL photo, ffmpeg video overlay) | Per-type toggles (photo/video/GIF) are partly there (video max duration). Add an explicit `apply_to` list | S | P2 |
| JB-PROC-18 | Watermark library | PNG presets: opacity, scaling, alignment [doc] | partial | One PNG (`stamp_watermark_path`), `stamp_opacity`, `stamp_scale`; position is **random** (`processor.py:~378`) | Add `stamp_position` (corners/center/random) and panel upload of the PNG into `projects/<key>/` (today it is a file path) | S | P1 |
| JB-PROC-19 | Third-party bot processing | Route through an external bot and back [doc] | no | — | Needs users/bots as targets and sources (FWD-02/05). Niche | M | P2 |
| JB-PROC-20 | Manual edit / media swap | Via moderation mode [doc] | no | — | Comes with MOD-01..03 | — | P1 |

### 2.7 AI — AI processing (yes 0 / partial 0 / no 10)

| ID | Feature | In Junction | In my bot | Location in code | What to build/change | Effort | Priority |
|---|---|---|---|---|---|---|---|
| JB-AI-01 | AI text processing | An LLM prompt rewrites the message text per forwarding (translate, summarize, rewrite) [doc] | no | — | `AiRewriteFilter(prompt_id)` in the filter chain: async HTTP to the provider, entity-safe text replacement (start with plain text + markdown parse back), timeout → fall back to the original or DISCARD (configurable), per-call cost/token log. Needs the AI layer (§5 A8) | M | P1 |
| JB-AI-02, JB-AI-03, JB-AI-04 | Prompt blocks, actions, sharing, custom prompt | Active prompt / My prompts / library; apply, edit, copy, stop; one prompt shared by many forwardings; name, text, creativity, model [doc] | no | — | A `prompts:` section in the project YAML (or the DB, Q2) referenced by id from filters; panel screen "🤖 Промпты" (list, edit text, temperature, model, test on the last post) | M | P1 |
| JB-AI-05, JB-AI-06, JB-AI-07 | AI usage mode, models, free quota | Free / platform balance / own key (OpenAI, OpenRouter 300+ models); free quota per 30 days [doc] | no | — | Single-owner: **own key only** (`AI_PROVIDER`, `AI_API_KEY`, `AI_MODEL` in `.env`, an OpenAI-compatible endpoint covers OpenRouter too). No quotas, only a monthly spend counter in `stats.json`. Free tier and balance are SaaS-only | S | P1 |
| JB-AI-08, JB-AI-09 | Presets "Ad check" and "Potential client detection" | Library prompts that mark ads / non-leads for filtering [doc] | no | — | Ship 2–3 built-in prompts for `AiClassifyFilter` (ads, off-topic, leads). Overlaps the backlog idea "реклама" (memory, pass 34 top-5) | S | P1 |
| JB-AI-10 | AI use cases | Translate, summarize, smart filter, sentiment, moderation, auto-reply (marketing) [doc] | no | — | Covered by AI-01 + FLT-16. Auto-responder out of scope | — | P2 |

### 2.8 PUB — Publishing & delivery (yes 1 / partial 8 / no 3)

| ID | Feature | In Junction | In my bot | Location in code | What to build/change | Effort | Priority |
|---|---|---|---|---|---|---|---|
| JB-PUB-01 | Delivery mode | 6 modes: bot/account × copy/forward + hybrids (flood→bot, forward→copy on protection, copy regular + forward forwards) [doc] | partial | `mode: copy\|forward` as account (`config.py`, `mirroring.py:_do_send`) | Add the hybrids that need no bot: **forward, copy on protection** (auto-pick per message from `chat.noforwards`) and **copy regular, forward the forwards** (`fwd_from`). Bot modes depend on A10 | S | P1 |
| JB-PUB-02 | Publish as bot vs account | Identity in the destination [doc] | partial | Account only | Decision on bot-as-sender (Q5, §5 A10) | L | P2 |
| JB-PUB-03 | Anonymous group posting | Admin anonymity → posts as the group [doc] | yes | `telemirror/tasks/anonymize_groups.py` ("Remain Anonymous" + "Hide Members"), panel 🕶 Анонимность | — (automated, better than Junction's manual advice) | — | — |
| JB-PUB-04 | Publication delay (queue) | Fixed or random delay after the source post [doc] | no | `send_delay` is pacing **after** each send (`mirroring.py:1296`), not a delay from publication | Needs a persistent delayed-send queue (§5 A7) or PUB-05 Telegram scheduling (cheaper). Backlog idea "задержка" | M | P1 |
| JB-PUB-05 | Schedule (Telegram scheduler) | Put posts into the native scheduled messages [doc] | no | `_patch/sending.py` already accepts `schedule=` (Telethon) | `schedule_after: [from, to]` per direction → pass `schedule=now+rand` to `send_message`/`send_file`. Edits/deletes of scheduled copies need `messages.GetScheduledHistory` mapping (store a scheduled id in `binding_id`). Cheapest way to get delay **without** a job queue | M | P1 |
| JB-PUB-06 | Delivery frequency | Minimum interval between posts per source [doc] | partial | `send_delay` per direction (`DirectionConfig.send_delay`), panel ⏱ Пауза между постами (`directions.py:dir_delay`) | It is a sleep inside the fan-out, so concurrent events aren't serialized. A real per-target rate limiter (token bucket, or Telegram schedule spacing) | S | P2 |
| JB-PUB-07 | Pin posts | off / pass / silent / notify [doc] | partial | `telemirror/tasks/sync_pins.py` (batch reconcile via `binding_id`), panel 📌 Закрепы | Live pin propagation: handle `MessageActionPinMessage`/`UpdatePinnedMessages` in the live mirror (mode `pass`); `silent`/`notify` = pin every copy | S | P2 |
| JB-PUB-08 | Silent mode | pass / never / always [doc] | partial | Source silent flag passed through (`_patch/sending.py` ~l.272 `silent = message.silent`) | Add `silent: always\|never` per direction (one argument) | S | P2 |
| JB-PUB-09 | Link preview | pass / never / always [doc] | partial | Preview copied as in the source (webpage media kept) | `link_preview: never` = drop `MessageMediaWebPage` before send; `always` = `link_preview=True` | S | P2 |
| JB-PUB-10 | Flood reaction | Ignore / Stop / Postpone (default) / Notify [doc] | partial | Fixed: Telethon auto-sleeps ≤300 s (`misc/telegram_client.py`, `flood_sleep_threshold=300`); larger → post recorded in `failed.json` (`telemirror/failed.py`, `sink.py`) + one notice/min + manual ♻️ retry (`bot/routers/failed.py`) | Add **auto-retry** of `failed.json` entries after the FloodWait expires (today it waits for a manual ♻️). Optionally a per-project policy (skip / auto-retry / stop) | S | P1 |
| JB-PUB-11 | Flood mitigation | Account mode, bot fallback, frequency, split across accounts [doc] | partial | `send_delay`, video-encode serialization, projects on different accounts | Comes with PUB-06 (rate limiter); bot fallback needs A10 | — | P2 |
| JB-PUB-12 | Delayed deletion | Delete after a preset time [matrix] | no | — | A job queue (A7) entry "delete mirror X at T"; or skip (undocumented in the reference) | S | P2 |

### 2.9 MOD — Moderation (yes 0 / partial 0 / no 5)

| ID | Feature | In Junction | In my bot | Location in code | What to build/change | Effort | Priority |
|---|---|---|---|---|---|---|---|
| JB-MOD-01, JB-MOD-02, JB-MOD-03 | Moderation mode: review chat, Publish/Skip/edit | Each post is held; a copy goes to @Junction_Review_Bot or your own chat with Publish/Skip buttons; edit the review copy, then publish the current version [doc] | no | — | **Pre-moderation** (backlog idea "премодерация"). Recommended: the panel bot gets a "🛂 На проверке" flow. The live mirror posts the processed copy **as the account** into a review chat (a group where the panel bot is admin), and the panel bot attaches ✅ Опубликовать / ⏭ Пропустить / ✏️ buttons (as a reply, since the account can't add buttons). On tap, the panel writes a request file (same IPC as `failed.py` requests) → the mirror copies the **current** review message to the targets and records `binding_id`. Needs a persistent pending store (§5 A7) and faster IPC than 15 s polling (§5 A11) | L | P1 |
| JB-MOD-04, JB-MOD-05 | Moderation side effects and extras | Filters run first; edits not synced; buttons dropped; scheduling of approved posts, team review [doc] | no | — | Define in the design: filters before review; edit sync off for moderated directions; "publish at…" via PUB-05; a team = several admins in the review group (already a flat admin list) | S | P2 |

### 2.10 DIG — Digests (yes 0 / partial 0 / no 16)

| ID | Feature | In Junction | In my bot | Location in code | What to build/change | Effort | Priority |
|---|---|---|---|---|---|---|---|
| JB-DIG-01, JB-DIG-02, JB-DIG-03, JB-DIG-04 | Digests entity, quick digest, scheduled vs instant, generate now | AI summary of many chats on a schedule or on demand; 3-click creation [doc] | no | — | New `telemirror.digest` module + `telemirror-digest@.service`/`.timer` (systemd timers exist as a pattern: `deploy/systemd/telemirror-report.timer`). It reads messages since the last run with the project's account, calls the LLM and posts the result. The session lock means it must run **inside** the live process or take turns (§5 A5) | L | P2 |
| JB-DIG-05, JB-DIG-06, JB-DIG-07, JB-DIG-08 | Templates, prompt editor, past digests as context, metadata fields | Template library; prompt + model + temperature; 0–10 previous digests; fields text/date/views/reactions… [doc] | no | — | Reuse the AI-02 prompt store; keep the last N digests in `projects/<key>/digests/`; feed views/reactions/forwards from `Message` | M | P2 |
| JB-DIG-09, JB-DIG-10 | Digest sources and topic selector | Public / invite / closed sources; all topics or chosen topics [doc] | no | — | Same chat-ref + `#topic` grammar as directions | S | P2 |
| JB-DIG-11, JB-DIG-12 | Publication time and place | Daily or per-day slots; bot chat or external chat, as bot or account [doc] | no | — | systemd `OnCalendar=` per digest (or an in-process scheduler, A7); place = a channel (as account) or the panel chat (as bot) | S | P2 |
| JB-DIG-13, JB-DIG-14, JB-DIG-15, JB-DIG-16 | Preview, statuses, actions, limits | Preview for a period; Pending/Generating/Disabled/Suspended; disable/copy/generate now/move; message caps [doc] | no | — | Panel screen per digest; statuses map naturally onto systemd unit states (`bot/status.py`) | M | P2 |

### 2.11 PROJ — Projects (yes 3 / partial 0 / no 1)

| ID | Feature | In Junction | In my bot | Location in code | What to build/change | Effort | Priority |
|---|---|---|---|---|---|---|---|
| JB-PROJ-01 | Projects | Group forwardings and digests [doc] | yes | `telemirror/projects.py` (`Project`), `bot/routers/projects.py` | A telemirror project is a whole mirror (config + account + process), heavier than a label (§5 A5) | — | — |
| JB-PROJ-02 | Project switcher & default | "All projects" view, Project #1 [doc] | yes | 📁 Проекты list (`bot/registry.py` `prj`), 📊 Задачи over every project (`bot/routers/tasks.py`) | — | — | — |
| JB-PROJ-03 | Move to project | Move a forwarding/digest to another project [doc] | no | — | "↪️ Перенести в проект…" on the direction card: a cut/paste of the YAML item between two configs via `ConfigStore` (two sha-guarded writes) | S | P2 |
| JB-PROJ-04 | Manage projects | Counters, create, rename, delete-if-empty [doc] | yes | create/rename/icon/delete (moved to `projects/.deleted/`, undoable) in `bot/routers/projects.py`, `telemirror/projects.py:delete_project` | — | — | — |

### 2.12 INT — Integrations & settings (yes 3 / partial 0 / no 2)

| ID | Feature | In Junction | In my bot | Location in code | What to build/change | Effort | Priority |
|---|---|---|---|---|---|---|---|
| JB-INT-01 | Save to Google Drive | Archive text/media; links sent instead [doc] | no | — | Niche. If needed, a generic "archive to local disk/S3/Drive" sink filter. Ask the owner (Q8) | M | P2 |
| JB-INT-02 | Export settings | `/dump` → file of commands [doc] | yes | 📥 Скачать YAML (`bot/routers/config_file.py`) | — | — | — |
| JB-INT-03 | Import settings | `/batch` commands [doc] | yes | 📤 Загрузить YAML with size/shape check, diff, subprocess validation, confirm, sha guard, `.bak` + ↩️ rollback (`bot/configstore.py`) | — (safer than Junction) | — | — |
| JB-INT-04 | Interface language | EN / RU [doc] | no | All strings Russian in `bot/texts.py`, `bot/registry.py` | Not needed for a single Russian-speaking owner. SaaS-only | M | P2 |
| JB-INT-05 | No webhook/API by design | Use Telegram as the queue [doc] | yes | Same stance: no HTTP API, only the `GET /` health endpoint (`telemirror/live.py`) | — | — | — |

### 2.13 DIAG — Diagnostics (yes 1 / partial 6 / no 3)

| ID | Feature | In Junction | In my bot | Location in code | What to build/change | Effort | Priority |
|---|---|---|---|---|---|---|---|
| JB-DIAG-01 | Delivery tracking (`/track`) | Paste a source-message link → delivered or not, and why (filter, setting) + auto-diagnostics [doc] | partial | ❗ Не скопировано lists **failed** posts with reasons (`telemirror/failed.py`, `bot/routers/failed.py`); per-pair counters in `stats.json` (`telemirror/stats.py`); `binding_id` knows every delivered copy | **"🔎 Где копия?"** (backlog idea): the admin forwards a post or pastes a `t.me` link → the panel looks up `binding_id` (sent: links to each copy), `failed.json` (failed + reason), or a new per-message **trace log** (filtered by which filter / dup / no direction / mirror was down). The trace needs the live mirror to record *why* a post was filtered (§5 A9) | M | P0 |
| JB-DIAG-02 | Delivery report outcomes | Delivered / blocked by mustHave / blocked by mustNotHave, plus the responsible filter [doc] | partial | `Outcomes` states sent/filtered/dup/failed (`telemirror/outcomes.py:12`); `reason` recorded only for failures | Record the discarding filter's name (and the matched keyword) in `Outcomes.filtered(reason)`, from `CompositeMessageFilter.process` (`messagefilters/base.py:103`) | S | P0 |
| JB-DIAG-03 | Processing report | Per-message debug report sent with each message (opt-in) [doc] | partial | INFO logs per message in the journal; panel 📊 Задача shows 15 journal lines (`bot/routers/tasks.py`) | An opt-in "🐞 Отчёт по каждому посту" per project that sends the trace (DIAG-02) to the admin chat for the next N posts | S | P2 |
| JB-DIAG-04 | Message source code | How the bot sees a message (HTML, tokens) [doc] | no | — | Part of "Где копия?": show text + entities as HTML (`telethon.extensions.html.unparse`) + media type. Helps when writing replacement rules | S | P2 |
| JB-DIAG-05 | Helper bot for source code | Forward a message → source code [doc] | no | — | Same feature in the panel: forward any post to the panel → source code (no separate bot) | — | P2 |
| JB-DIAG-06 | Regex debugging | regex101 Java-8 advice [doc] | partial | Regexes compiled and validated on save (`bot/configstore.py` subprocess import of `telemirror.config`, `KeywordReplaceFilter` group-ref check) | "🧪 Проверить на посте": run the direction's filter chain on a forwarded post and show the result without sending (dry-run of `filters.process`) | S | P1 |
| JB-DIAG-07 | Alerts bot | Separate bot for system notifications [doc] | yes | Panel bot is the alert channel: `telemirror/notify.py` (`BotNotifier`), `alert.py`, `health.py`, `NoticeLogHandler` (`mirroring.py:2063`), `bot/watcher.py` | — | — | — |
| JB-DIAG-08 | Forwarding statuses & auto-disable | connecting… / expired / disabled on errors [doc] | partial | Unit state on the project card (`bot/status.py`), 🔇 silent ≥7 days per direction (`stats.quiet_days`), "last post", health timer (`telemirror/health.py`), watchdog (`misc/sdnotify.py`) | Per-direction status: "❌ нет доступа к источнику / не может публиковать" from `check_access` (`tasks/check_access.py`) shown on the direction card. Auto-disable isn't needed | S | P1 |
| JB-DIAG-09 | Troubleshooting playbook | Known symptoms → fixes [doc] | partial | README, 🧾 Проверка установки (`telemirror/selfcheck.py`), 🛂 Проверка доступа | A short "Что делать, если…" help screen in the panel linked from failure notices | S | P2 |
| JB-DIAG-10 | Support channels | Support bot, user group, AI help bot [doc] | no | — | SaaS-only | — | P2 |

### 2.14 CMD — Bot commands (yes 4 / partial 7 / no 5)

telemirror deliberately has a button panel, not a text-command language. Rows are judged on capability, not on the command syntax.

| ID | Feature | In Junction | In my bot | Location in code | What to build/change | Effort | Priority |
|---|---|---|---|---|---|---|---|
| JB-CMD-01 | `/track` | Delivery report wizard [doc] | partial | See JB-DIAG-01 | A `/track <link>` command as a shortcut into "🔎 Где копия?" | S | P0 |
| JB-CMD-02 | `/disableall`, `/enableall` | Pause/resume all forwardings [doc] | partial | Per-project ⏹/▶️ (`bot/routers/projects.py`, `bot/routers/_units.py`) | "⏸ Остановить все / ▶️ Запустить все" on ⚙️ Настройки (loop over the projects' live units, respecting session turns) | S | P2 |
| JB-CMD-03, JB-CMD-04 | `/dump`, `/batch` | Export/import settings as commands [doc] | yes | 📥/📤 YAML (`bot/routers/config_file.py`, `bot/configstore.py`) | — | — | — |
| JB-CMD-05 | `/language` | Switch UI language [doc] | no | — | See JB-INT-04 (SaaS-only) | — | P2 |
| JB-CMD-06 | `/filter` | List/toggle filters of one source; every N; addAllFrom [doc] | partial | Direction filter list `dflt` + filter card `fv` (`bot/routers/filters.py`) | every N → FLT-14; addAllFrom → FLT-18 | S | P2 |
| JB-CMD-07, JB-CMD-08 | `/filterall`, `/filterrxall` | Add/remove a text/regex filter on all sources; DELETE ALL [doc] | partial | The project filter list covers all directions without their own list. Directions **with** their own list aren't touched | "Применить ко всем направлениям, включая свои списки" option on the project filter screen | S | P2 |
| JB-CMD-09, JB-CMD-10 | `/filtertime`, `/filtertimeall` | Date/time filter on one source or on all [doc] | no | — | Comes with JB-FLT-06 | — | P1 |
| JB-CMD-11, JB-CMD-12 | `/replace`, `/replacerx` | Plain / regex replacement rule [doc] | yes | `KeywordReplaceFilter` map editor in `bot/routers/filters.py` (+ `r'…'` for regex) | — | — | — |
| JB-CMD-13, JB-CMD-14 | `/setting`, `/settingchannel` | Author/header/buttons/likes; per-channel settings such as the duplicate filter [doc] | partial | Header/author via `ForwardFormatFilter`; project-wide 🧬 Без повторов (`bot/routers/params.py`); per-direction overrides only by hand in YAML | Per-direction settings in the panel (see UX §4, U3) | M | P1 |
| JB-CMD-15, JB-CMD-16 | Inline channel search; subscribe by sending a link | `@junction_bot <word>` lists known channels; sending `@name` subscribes the bot chat [doc] | no | — | Inline search: SaaS-only. A pasted `@name`/link as **input** is covered by JB-FWD-03 | — | P2 |

### 2.15 UI — Interface & management (yes 5 / partial 5 / no 4)

| ID | Feature | In Junction | In my bot | Location in code | What to build/change | Effort | Priority |
|---|---|---|---|---|---|---|---|
| JB-UI-01 | Mini-app & menus | Menu button → mini-app; burger side menu [doc] | partial | Chat-native panel: reply keyboard `📁 Проекты / 📊 Задачи / ⚙️ Настройки` + inline screens from `bot/registry.py` (`MAIN_MENU`, `SCREENS`), `bot/screens.py` | A mini-app is not needed for one owner. Keep the chat panel (Q7) | L | P2 |
| JB-UI-02 | Forwarding creation wizard | Source → destination (create new) → topic mapping → main settings (type, delivery mode, link replacement) [doc] | partial | ➕ Добавить: `AddDirection.source → targets → choice` (📋 Копия / ↪️ Пересылка + history) in `bot/routers/directions.py:427` | Add the missing steps: topic mapping by name (TOP-01), filters preset ("как в проекте / свои"), noforwards detection → offer the bypass (FWD-19), access check of the new chats, **apply now** (A1) | M | P0 |
| JB-UI-03 | Default configuration | A new forwarding works with no setup [doc] | yes | New project template `mode: copy`, edits/deletes on, `directions: []` (`telemirror/projects.create_project`); new direction inherits project filters | — | — | — |
| JB-UI-04 | Create new chat | Create the destination channel/group from the picker [doc] | partial | Only in the CLI Citadel wizard `telemirror/tasks/setup_mirrors.py:304` (`CreateChannelRequest`) | "➕ Создать канал / группу" step in the direction wizard via the project's account (needs a request to the live process or a short task run, §5 A5/A11) | M | P1 |
| JB-UI-05 | Chat picker & pin workaround | Pick from the list; pin to make a chat appear [doc] | yes | `📇 Выбрать из списка` (`KeyboardButtonRequestChat`, `bot/keyboards/menu.py`), forwarded post, `-100…` id; names in `chats.json` | Picker lists the **admin's** chats, not the account's (see FWD-03) | — | — |
| JB-UI-06 | Table view | All forwardings in one sortable/filterable table with columns and tabs [doc] | partial | Paged list «N. Источник → Канал» with marks 🧹 ✳️ 🔇 and 🔎 Найти (`bot/routers/directions.py:163`) | Sort/filter chips: "🔇 молчат", "❗ с ошибками", "✳️ свои настройки", by target. A table is beyond a chat UI | S | P2 |
| JB-UI-07 | Mobile display modes | Compact / Wide / Auto [doc] | no | — | N/A for a chat UI | — | P2 |
| JB-UI-08 | Web app | Open in a browser [doc] | no | — | N/A unless a mini-app is built (Q7) | — | P2 |
| JB-UI-09 | Saved table layout | Persisted table config [doc] | no | — | N/A | — | P2 |
| JB-UI-10 | Clone forwarding | Copy with all settings to a new source/destination [doc] | no | — | "📑 Клонировать" on the direction card: duplicate the YAML item (`bot/configedit.py`), then go to the 📨/🎯 editor | S | P1 |
| JB-UI-11 | Change source | Rebind the source (and reader account) [doc] | yes | 📨 Откуда / 🎯 Куда channel-list editor (`bot/routers/directions.py:320`, `dir_src/dir_dst`) | — | — | — |
| JB-UI-12 | Pause forwarding | Keep settings, stop copying new posts [doc] | partial | Per direction only via the "Пауза: не копировать ничего" filter (`SkipAllFilter`, `bot/filtercatalog.py:62`); per project ⏹ | A first-class "⏸ Пауза" toggle on the direction card (`paused: true` in YAML, skipped in `config.py`), which doesn't replace the filter list | S | P1 |
| JB-UI-13 | Delete forwarding | Irreversible delete [doc] | yes | 🗑 Удалить with confirmation (`directions.py:239-255`); config `.bak` + ↩️ Откатить (`bot/routers/config_file.py`) | — (recoverable, better than Junction) | — | — |
| JB-UI-14 | Personal account screen | Connections, reconnect, change number [doc] | yes | 👤 Аккаунты list/card/delete, 🔑 login, 📤 session upload (`bot/routers/accounts.py`, `bot/sessions.py`) | Reconnect → JB-ACC-06 | — | — |

## 3. Summary stats and top gaps

### 3.1 Counts (per reference ID, 181 total)

| Area | IDs | yes | partial | no |
|---|---|---|---|---|
| ACC | 10 | 4 | 4 | 2 |
| FWD | 20 | 8 | 7 | 5 |
| TOP | 10 | 3 | 3 | 4 |
| HIST | 10 | 5 | 4 | 1 |
| FLT | 19 | 4 | 5 | 10 |
| PROC | 20 | 9 | 6 | 5 |
| AI | 10 | 0 | 0 | 10 |
| PUB | 12 | 1 | 8 | 3 |
| MOD | 5 | 0 | 0 | 5 |
| DIG | 16 | 0 | 0 | 16 |
| PROJ | 4 | 3 | 0 | 1 |
| INT | 5 | 3 | 0 | 2 |
| DIAG | 10 | 1 | 6 | 3 |
| CMD | 16 | 4 | 7 | 5 |
| UI | 14 | 5 | 5 | 4 |
| **Total** | **181** | **50 (28%)** | **55 (30%)** | **76 (42%)** |

How to read it:
- The core mirroring engine (FWD, HIST, PROC) is at or above parity. Link rewriting, reply chaining, edit/delete sync, albums, protected sources, caption split and checkpointed history are all present and often more robust than the reference.
- Most "no" rows sit in three areas: **AI (10), digests (16) and moderation (5)**, 31 IDs together. Another ~20 are SaaS-only or mini-app items (ACC-07/08, INT-04, DIAG-10, CMD-05/15, UI-07/08/09) that a single-owner tool doesn't need.
- The **real parity gaps** for a mirroring tool are the cheap rule types (media type, author, forwarded, own messages, time window), delayed publishing/scheduling, moderation, per-message diagnostics, and applying changes without a restart.

### 3.2 Top 15 biggest gaps (ranked by value × centrality)

| # | Gap (IDs) | Why it ranks here |
|---|---|---|
| 1 | **Config changes need a restart** (FWD-01, UI-02; enabler for TOP-06/07, MOD, PUB-04) | Every panel save ends with "press 🔁 Перезапустить" (`bot/texts.py:221`), and a restart loses live posts (no catch-up, gap 2). This is the biggest everyday UX and reliability cost, and the dynamic features depend on a reloadable mapping |
| 2 | **No catch-up of posts missed while the mirror is down** (FWD-08, HIST-10, DIAG-01) | Restarts, crash loops, replay/task turns and session-mates silently lose posts. Junction's product promise is "nothing is missed". Cheap to fix with persisted update state or a per-source last-id backfill on start (§5 A6) |
| 3 | **"Where is the copy?" / per-message trace** (DIAG-01, DIAG-02, CMD-01, DIAG-04) | It is Junction's first-line support tool. telemirror already has `binding_id` + `failed.json` + `Outcomes`, so only the "filtered by X" reason and a lookup screen are missing. High value, M effort |
| 4 | **Media-type filter** (FLT-12, FWD-14, PROC-16) | The most common real-world rule ("photos only", "no voice/stickers"). S effort, P0 |
| 5 | **Pre-moderation** (MOD-01..05, PROC-20) | Already the owner's backlog idea #1. Unlocks manual editing, and needs the job store and IPC work that delayed posting also uses |
| 6 | **Source/target entry by @username / link / account's own chats** (FWD-03, UI-02, UI-04) | Today only `-100…` ids, a forwarded post, or the admin's (not the account's) chat list. It's the main friction in adding directions |
| 7 | **Delay / Telegram scheduling of publication** (PUB-04, PUB-05, PUB-06) | Backlog idea "задержка". PUB-05 is cheap via Telethon `schedule=` and needs no queue |
| 8 | **AI layer: rewrite + classify** (AI-01..09, FLT-16) | Junction's headline differentiator, and the owner's "реклама" idea is a classify use case. M effort once one provider wrapper exists |
| 9 | **Per-direction settings in the panel** (FWD-07/09/10, CMD-13/14, PUB-08/09) | Mode/edits/deletes/dedup/link are project-wide in the panel; per-direction values are "✳️ in the file". Junction's whole model is per-forwarding settings |
| 10 | **Author / forwarded / own-message / time-window filters** (FLT-10, FLT-11, FLT-13, FLT-06, CMD-09/10) | Four small filters (S each) that cover most of Junction's non-text rules. Own-message also guards against chain loops |
| 11 | **Delayed engagement filter** (FLT-07, FLT-08) | A distinctive Junction feature (publish only "hot" posts) and good for curated feeds, but it needs a persistent scheduler (L) |
| 12 | **Topic tooling: mapping by name, copy structure, auto-sync** (TOP-01..04, TOP-06) | Forums are central to the owner's Citadel setup, but this exists only as a hard-coded CLI wizard (`tasks/setup_mirrors.py`) |
| 13 | **Flood: auto-retry of failed posts** (PUB-10, PUB-11) | Failures after a long FloodWait wait for a manual ♻️. Auto-retry after the wait is S effort |
| 14 | **Clone / pause / move direction** (UI-10, UI-12, PROJ-03) | Small panel conveniences that Junction users rely on. Today "pause" = adding a `SkipAllFilter`, which replaces the inherited filter list |
| 15 | **Digests** (DIG-01..16) | A big feature family (L), but separate from mirroring and only valuable if the owner wants summaries. Ranked last among real gaps because it depends on the AI layer and fits the product poorly |

## 4. UX gap (panel `bot/` vs Junction's mini-app)

Junction's model is one forwarding = one settings screen, where every option sits on that screen and takes effect immediately. telemirror's panel is a well-engineered safe editor of a YAML file plus a systemd console. The friction comes from that difference.

**U1. Changes don't apply until a restart.** Every `writes.save()` ends with `texts.SAVED` = "✅ Сохранено. Чтобы изменения заработали, нажмите «🔁 Перезапустить» в карточке проекта" (`bot/texts.py:221`), and the card shows "⚠️ Изменения ещё не применены" (mtime vs `ActiveEnterTimestamp`, `bot/routers/projects.py`). So every edit takes two steps (save, then go to the card and restart), a 120 s restart cooldown applies (`bot/settings.py`, `bot/routers/_units.py`), and the restart drops posts (U9). Junction applies settings live. *Fix:* hot reload (§5 A1), or at least a "🔁 Применить сейчас" button right in the save toast.

**U2. Chat entry is id-centric.** Inputs accept `-100…[#topic]` only (`bot/configparse.py:11` `_CHAT_REF_RE`), a forwarded post, or the Bot API `request_chat` picker. The picker lists the **admin's** chats, not the mirroring account's, so a channel the account is in but the admin isn't can't be picked. Pasting `@name` or `t.me/...` (the natural way) fails with `bad_ref`. Topics need a numeric `#id` the user must look up. *Fix:* resolve usernames/links with the project's account, and add a picker over the account's dialogs from `chats.json` with topic names.

**U3. Settings are project-wide in the panel and per-direction only in the file.** `bot/routers/params.py` toggles edits/deletes/mode/link/dedup for **all** directions. A direction's own values are only displayed (✳️ "свои настройки в файле", `bot/routers/directions.py:58,150`), and some filters are file-only (`texts.CONFIG_ERRORS["bad_filter"]`, `MappedNameForwardFormat`). So "this one source in forward mode, no edits" means downloading the YAML, editing it and uploading it back. *Fix:* a direction-card "⚙️ Свои настройки" group reusing the `params.py` toggles with a direction scope (`configedit` already has direction value ops).

**U4. Filters read like code.** Filter names are class concepts ("Подпись с источником" = `ForwardFormatFilter` with a `{message_text}` format string; "Водяной знак" with 18 advanced args, `bot/filtercatalog.py`). Header/footer require writing a format template. Junction shows plain fields ("Add header", "Add text after message", "Link to original: none/full/custom"). *Fix:* friendlier presets on top of the same classes (header field, footer field, toggles for source name/link/author) that generate the format string.

**U5. The direction wizard is short and has no confirmations.** `AddDirection.source → targets → choice` (`bot/routers/directions.py:427`) doesn't check access (the account can see the source and post in the target; `check_access` exists only as a separate 🛂 tool run that pauses the mirror), doesn't detect `noforwards` sources (they then fail silently with a log warning, `mirroring.py:~545`), offers no topic mapping by name, and ends without an "apply now". *Fix:* run the access/noforwards probe inside the wizard (via the live process, §5 A11) and offer the bypass filter in one tap.

**U6. Feedback when something isn't copied is aggregate, not per post.** You get "❗ Не скопировано постов: N" and a list of failures, plus a weekly report, but there is no answer to "why didn't post X arrive?" when it was **filtered** or **missed during downtime**. Those cases are invisible. Junction's `/track` answers exactly this. *Fix:* "🔎 Где копия?" (DIAG-01/02) plus logging the filter that discarded a post.

**U7. Testing a filter means waiting for real posts.** There is no "try this filter on this post". `ConfigStore` validates syntax only (subprocess import, `bot/configstore.py:82-102`). *Fix:* "🧪 Проверить на посте": forward a post and see the processed result plus which filter did what (DIAG-06).

**U8. Saves are slow.** Each save spawns `python -c "import telemirror.config"` (`bot/configstore.py:101`), which loads cv2/numpy and takes seconds on a 1 vCPU host. The cause is that `telemirror.config` imports the watermark stack. *Fix:* lazy-import heavy filter modules, or validate with a lighter parser.

**U9. Running a tool or replay stops the mirror.** `telemirror-task@`/`past@` `Conflicts=telemirror@%i` and `bot/turns.py` pause the live mirror (and any project on the same session). Posts published meanwhile are lost (no catch-up). Junction runs history copies alongside live forwarding. *Fix:* §5 A5/A6. At minimum, a catch-up pass on resume.

**U10. Onboarding is good but linear.** `next_step()` (`bot/routers/projects.py:107`) and the "Как начать" welcome (`bot/routers/menu.py:54`) guide account → direction → start, which is clearer than Junction's tier gating. Missing pieces: a quick test ("🔔 Отправить тестовый пост") and a post-start confirmation that the first post came through ("first post mirrored ✅" notice).

**U11. Navigation depth is fine, but filters need many taps.** Common paths are 3–4 taps (📁 → project → 🔀 → direction), comparable to Junction. Filter editing is deeper (card → 🧹 → filter → arg → item), and every arg change is a separate save that needs a restart (see U1).

**U12. Error handling is strong in places Junction doesn't cover.** Confirmations with TTL, sha-guarded writes, a "stale" refusal when the file changed, `.bak` rollback, and a refusal to start with registry/handler mismatches (`bot/app.py`). The UX debt is about missing features and the restart, not fragility.

**U13. Diagnostics: the operator side is better, the user side is weaker.** 🧾 self-check, 🛂 access check, 📊 journals, health/flapping alerts and the weekly report have no Junction equivalent. What is missing is the message-level view (U6) and per-direction health ("❌ нет доступа" on the direction card from `access.json`, which is only shown on the 🛂 screen today).

**U14. Language and multi-user.** Russian only and admin-only (`AdminOnly` drops strangers silently). That fits the single owner. It becomes a gap only if Q1 = SaaS.

## 5. Architecture gap (what in the backend blocks the reference functionality)

Each item lists: **what it is**, its **impact**, the **IDs it blocks**, and a **direction** (reuse / refactor / rewrite).

**A1. Config is read once at import, and `CHAT_MAPPING` is a module global.**
- *What:* `telemirror/config.py:222-389` builds `CHAT_MAPPING`, filters and broadcast routes at import time. `EventHandlers` registers `NewMessage(chats=list(CHAT_MAPPING))` once (`mirroring.py:2213`). Validation fails the import.
- *Impact:* every change needs a process restart (U1), and restarts lose posts (A6). Anything that changes the mapping at runtime is impossible: folders, topic auto-sync, add-direction-and-go, pause one direction.
- *Blocks:* FWD-01 (live apply), UI-02, UI-12, TOP-06, TOP-07, MOD-01 (dynamic moderated directions), PROJ-03.
- *Direction:* **refactor.** Move the parse into a pure function `load_mapping(path) -> Mapping` (config.py already separates env from YAML parsing). Hold the mapping in an object on `EventProcessor` (it already overrides `chat_mapping` for past mode, overview §6). Register one handler without `chats=` and filter by `chat_id in mapping` in the callback. Reload on SIGHUP or on a panel request file, and swap atomically after validation. The `ConfigStore` validation stays the gate. M effort, and it unlocks a lot.

**A2. YAML file as the source of truth (vs DB-backed entities).**
- *What:* directions are list items without stable ids. The panel addresses them by index plus content fingerprints (`bot/configedit.py`, `ConfigError("stale")`).
- *Impact:* there is no stable "forwarding id" for per-rule state (moderation queue, delayed jobs, per-rule counters, traces, clone/move). Hand edits and panel edits can collide (handled by the sha guard).
- *Blocks:* MOD-*, FLT-07, PUB-04, DIAG-01 (per-rule trace), UI-10, PROJ-03, DIG-* (as entities).
- *Direction:* **reuse + small refactor (recommended).** Keep YAML (it's diffable, hand-editable and versioned in git, which are real strengths) but add an optional stable `id:` per direction, auto-assigned by the panel (`configedit` add op) and used as the key for state in Postgres. A full move to DB-backed config would be a **rewrite** of `config.py`, `configedit/configstore` and the README contract, and only pays off with multi-user SaaS (Q1/Q2).

**A3. Filters are code classes with YAML params, not user-editable rule rows.**
- *What:* `build_filters` does `getattr(messagefilters, name)(**args)` (`config.py:259-278`). The panel catalog `bot/filtercatalog.py` describes arg kinds per class.
- *Impact:* every new criterion (media type, author, time, forwarded, engagement, AI) is a new class plus catalog entry plus tests. There is no uniform mustHave/mustNotHave across criteria. That is acceptable: it's how the project is built, and the catalog pattern scales.
- *Blocks:* FLT-02 (uniform logic), FLT-05/06/10..14/16 (each needs a class), DIAG-02 (needs each filter to report a reason).
- *Direction:* **reuse.** Add classes in the existing pattern. Optionally add one generic `RuleFilter(rules: [{type, value, mode}])` that evaluates Junction-style rows (text/regex/media/author/forwarded/time) with OR-within/AND-across semantics, so one panel editor serves all simple criteria. Extend `FilterResult`/`CompositeMessageFilter` with a `reason` for DISCARD.

**A4. No forwarding/rule entity or per-rule state in the DB.**
- *What:* the DB holds only message bindings, checkpoints, broadcast sync and fingerprints (`telemirror/storage.py`). There are no tables for pending posts, jobs, traces or AI usage.
- *Impact:* delayed/moderated posts can't survive a restart, and per-message "why" can't be answered after the fact.
- *Blocks:* FLT-07/08, PUB-04, PUB-12, MOD-*, DIAG-01/02/03, DIG-* (generations, statuses), AI-07 (spend tracking).
- *Direction:* **reuse `PostgresDatabase`** (auto-creates tables and columns). Add `pending_post(direction_id, source_chat, source_ids[], kind: delay\|engagement\|moderation, due_at, payload, review_msg)` and `post_trace(source_chat, source_id, target, state, reason, at)` with a TTL prune, as was done for `post_fingerprint`. `InMemoryDatabase` gets no-op or LRU versions.

**A5. One process per project, and one process per session.**
- *What:* `session_lock.py` (flock) plus `bot/turns.py`. Replays and tasks `Conflicts=` the live unit (`deploy/systemd/telemirror@.service:10`). Each project is its own ~RAM-heavy process.
- *Impact:* history copies, tools, digests or "create channel/topic" pause live mirroring, and projects sharing an account can't run together. Junction runs everything concurrently on one connection per account.
- *Blocks:* HIST-01 (concurrent with live), UI-04, TOP-03/04 (from the panel), DIG-* (reading sources needs the session), ACC-04 (per-direction accounts), FWD-03 (resolving usernames needs the session).
- *Direction:* **refactor toward "the live process owns the session and accepts jobs"**: run replay pairs and short account operations (resolve username, create topic, check access, digest fetch) **inside** the live mirror as asyncio tasks fed by A11 requests. Keep `telemirror-past@`/`task@` as the fallback when the mirror is stopped. A multi-session single process is a later, optional **rewrite**.

**A6. Missed updates during downtime (no catch-up).**
- *What:* clients use an in-memory `StringSession` (`misc/telegram_client.py:201`) and `catch_up` is never enabled (no hits in the repo). Only the broadcast channel is re-synced at start (`_sync_broadcast_channel`, `mirroring.py:2402`).
- *Impact:* posts, edits and deletes made while the mirror is restarting or paused (U1, U9, crashes, 04:00 restart) are silently lost.
- *Blocks:* reliability of everything; FWD-08 parity; DIAG-01 (can't explain "missed").
- *Direction:* **reuse.** On start, for each source, fetch messages newer than the last `binding_id.original_id` (or a persisted per-source "last seen id") through the existing `new_message`/`new_album` path. `already_mirrored` already makes this idempotent, and `iter_message_groups` exists. Alternatively persist Telethon update state (`SQLiteSession`/custom session + `catch_up=True`), but the backfill pass is simpler and source-scoped. S–M effort, P0.

**A7. No job queue or scheduler.**
- *What:* there is no durable "do X at time T". The only time-based work is systemd timers (health, restart, report) and in-process sleeps (`send_delay`).
- *Impact:* delayed publication, engagement checks, moderation timeouts, delayed deletion and scheduled digests have nowhere to live.
- *Blocks:* FLT-07/08, PUB-04/06/12, MOD-05, DIG-03/11.
- *Direction:* **reuse + new small component.** A `Scheduler` task in the live process that polls the `pending_post` table (A4) every N seconds and runs due jobs through the normal send path. PUB-05 (Telegram native scheduling) covers "delay" with no scheduler at all and is the cheaper first step. Digests can use systemd timers like `telemirror-report.timer`.

**A8. No AI layer.**
- *What:* no LLM client, keys, prompt store or cost tracking.
- *Blocks:* AI-01..10, FLT-16, DIG-*.
- *Direction:* **new module** `telemirror/ai.py`: one OpenAI-compatible async client (aiohttp is already a dependency), so OpenAI, OpenRouter and local models work through one interface. Env `AI_BASE_URL`, `AI_API_KEY`, `AI_MODEL`. Prompts live in YAML (`prompts:`) referenced by filters. There must be a strict timeout and fallback so that an AI outage never blocks mirroring, and usage is counted into `stats.json`. Filters `AiRewriteFilter`, `AiClassifyFilter` follow the A3 pattern. M effort.

**A9. No message-level trace for delivery reports.**
- *What:* `Outcomes` (`telemirror/outcomes.py`) knows sent/filtered/dup/failed per target, but only failures keep a reason, and only failures are persisted (`failed.json`, ≤300 entries/14 days). "Filtered" and "not matched by any direction" leave no trace.
- *Blocks:* DIAG-01/02/03, CMD-01, U6.
- *Direction:* **reuse.** Add `reason` to `filtered()`/`duplicate()`, have `CompositeMessageFilter` return the discarding filter's name, and have `LiveSink` write a compact trace row (A4 `post_trace`, or a rolling `projects/<key>/trace.jsonl` capped by size) for every fan-out. The panel "🔎 Где копия?" joins `binding_id` + trace + `failed.json`. S–M effort.

**A10. Account-as-sender only (no bot-as-sender).**
- *What:* all sends go through the userbot (`_patch/sending.py`). The panel bot only sends notices.
- *Impact:* a user account can't send inline keyboards or callback buttons, so original URL buttons, own buttons, feedback buttons and the bot chat feed are impossible. There is also no bot fallback on flood.
- *Blocks:* FWD-12, FWD-13 (partly), PROC-14, PROC-15, TOP-09, PUB-01 (bot modes), PUB-02, HIST-03 (bot fallback), PUB-11.
- *Direction:* **decision first (Q5).** If wanted: an optional per-direction `sender: bot` that re-sends the already-processed message through the Bot API (the panel bot token or a per-project bot), using `aiogram`/`aiohttp` and media re-upload (`_media.py` download already exists). It also needs `binding_id` rows for bot-sent ids so edits and deletes work. L effort; most value is buttons.

**A11. File-based IPC between panel and mirror.**
- *What:* panel → mirror requests are empty files in `projects/<key>/requests/`, polled every 15 s (`Mirroring._handle_requests`, `mirroring.py:2544`, `SINK_TICK_SEC = 15` at l.2341). Mirror → panel goes through JSON files plus the Bot API.
- *Impact:* fine for retries, but too slow and too narrow for interactive flows (moderation taps, "resolve @username", "test filter on post", "create topic", "reload config"). There is no request/response.
- *Blocks:* MOD-01..03, FWD-03 (resolve via account), DIAG-06 (test on post), UI-04, A1 reload trigger, A5 jobs.
- *Direction:* **refactor.** A local Unix socket per project (`/run/telemirror/<key>.sock`, aiohttp already serves the health endpoint and can listen on a socket) with a few JSON RPCs: `reload`, `resolve`, `probe_access`, `test_filters`, `retry`, `moderation_decision`, `create_topic`. Keep the request files as a fallback. Systemd `RuntimeDirectory=` is already used for the panel.

**A12. Single-operator admin model.**
- *What:* `PANEL_ADMIN_IDS` in `.env`, `AdminOnly` middleware, no roles, ownership or audit. The panel runs as root. FSM, cooldowns and dry-run gating are in memory (`bot/states.py:PanelStorage`, `bot/runtime.py`).
- *Impact:* correct for one owner. Blocks only the SaaS shape: per-user forwardings, per-user accounts and quotas, language, support.
- *Blocks:* ACC-08, ACC-09 (self-service transfer), INT-04, DIAG-10, CMD-05/15, AI-07 (quotas).
- *Direction:* **keep (recommended)** unless Q1 = SaaS. Going SaaS would be a **rewrite**: tenancy in every table, per-tenant configs and sessions, a non-root process model, billing (excluded here), abuse handling and legal exposure of running customers' userbots.

**A13. Resource ceiling (1 vCPU / 2 GB, a process per project).**
- *What:* `MemoryMax=1400M` per mirror (`deploy/systemd/telemirror@.service:46`), serialized video encodes and LaMa inpainting.
- *Impact:* AI calls are cheap (network-bound), but digests over many sources, folder expansion and many projects multiply RAM. Watermark work already competes for the CPU.
- *Blocks:* scale of DIG-*, TOP-07, many projects.
- *Direction:* **reuse.** Keep heavy media behind the existing serialization, and make heavy imports lazy (it also fixes U8).

**Dependency order (suggested):** A6 catch-up and A9 trace (cheap, reliability first) → A1 hot reload + A11 socket → A3 simple filters → A4 + A7 store and scheduler → MOD / delay / engagement → A8 AI → digests. A10 and A12 only after the owner decides.

## 6. What telemirror has that Junction doesn't

| # | telemirror feature | Where | Junction equivalent | Recommendation |
|---|---|---|---|---|
| 1 | **Watermark removal** (CLAHE+Sobel template detection, LaMa inpainting for photos, ffmpeg `delogo` for video) | `telemirror/watermark/processor.py`, `messagefilters/watermarkfilter.py` | None (Junction only *adds* watermarks) | **Keep**, but finish it: it's untested on the VPS, `reference_watermark.png` is missing from the repo, and torch is Linux-only. It's unique, but heavy for 1 vCPU and legally sensitive (removing others' marks). Keep it off by default and document the template workflow |
| 2 | **Restrict-saving bypass with re-upload, plus enabling `noforwards` on own targets** | `messagefilters/restrictsavingfilter.py`, `_media.py` (`ReuploadCache`, single-flight), `tasks/restrict_saving.py` | Partial (Junction copies protected sources; it has no "protect my mirrors" tool) | **Keep.** Make the bypass auto-offered (FWD-19). Fix the hard-coded `.configs/citadel_courses.config.yml` read in `restrict_saving` (overview §9) |
| 3 | **Cross-source dedup with `dedup_hours` fingerprints** (text + media ids, time window, per target) | `telemirror/dedup.py`, `post_fingerprint` table, `mirroring.py:267-300` | Duplicate filter with a 300-message memory per source and no time window | **Keep** (it covers several sources into one target, which Junction's doesn't). Consider adding `only_duplicates` and a photo perceptual hash |
| 4 | **Failed-posts queue with replay** (`failed.json`, ♻️ one/all, auto-removed on success) | `telemirror/failed.py`, `sink.py`, `outcomes.py`, `bot/routers/failed.py` | None (Junction only "postpones" on flood) | **Keep.** Add auto-retry after a FloodWait (PUB-10) and include replay skips (HIST-05) |
| 5 | **Link rewriting to the mirrored copy** (t.me/c, usernames, topic links; fallback URL; second pass after replay) | `mirroring.py:_rewrite_links` (l.461), `past._edit_links_pass` | "Replace cross-links with source" (Expert, undocumented variants) | **Keep.** A core differentiator for mirroring whole channel networks |
| 6 | **Reply chaining, edit/delete fan-out race safety, file-reference refresh, caption-split fallback** | `mirroring.py` (`_resolve_reply_target`, `_fanout_inflight`, `fetch_fresh_media`, `_send_with_caption_split`) | Not documented | **Keep** (engine quality) |
| 7 | **Broadcast channel** (one channel → all or whitelisted targets, with startup re-sync of edits/deletes) | `config.py:349-389`, `mirroring.py:_sync_broadcast_channel` | Would need N forwardings by hand | **Keep.** Fix "targets added later not backfilled" (overview §9) |
| 8 | **Self-check** of the installation | `telemirror/selfcheck.py`, panel 🧾 | None (SaaS hides ops) | **Keep** (essential for self-hosting) |
| 9 | **Weekly report** (copied/filtered/dups/errors, silent directions, top failing, over-filtering filters) | `telemirror/report.py`, `telemirror-report.timer` | None | **Keep.** It's also the seed of DIAG insight. "Filters dropping ≥90%" is a nice /track-like hint |
| 10 | **Health/flapping timer, daily restart timer, OnFailure alerts with journal tail, systemd watchdog** | `telemirror/health.py`, `alert.py`, `misc/sdnotify.py`, `deploy/systemd/*` | Junction runs ops internally | **Keep.** Revisit the **04:00 daily restart** once hot reload and catch-up exist (A1/A6): today it is both the "apply config" mechanism and a source of lost posts |
| 11 | **systemd ops from the panel** (start/stop/restart, journals, unit list, session turn-taking with auto-resume) | `bot/systemd.py`, `bot/routers/tasks.py`, `bot/turns.py`, `bot/watcher.py` | N/A | **Keep.** Simplify turn-taking once A5 (jobs inside the live process) lands |
| 12 | **Dry-run-gated maintenance tasks** (real run only after an identical successful dry-run on the same config sha) | `bot/routers/maintenance.py:can_run_real`, `telemirror/tasks/*` | None | **Keep** (a good safety pattern; reuse it for "copy topic structure", "create channels") |
| 13 | **Pin sync** (reconcile donor pins onto mirrors via `binding_id`) | `tasks/sync_pins.py` | Live "Pin posts" option (PUB-07) | **Keep**, and add live pin propagation as the PUB-07 equivalent |
| 14 | **Anonymize groups / hide members** | `tasks/anonymize_groups.py` | Manual advice only (PUB-03) | **Keep** |
| 15 | **Clear channels + DB reset** for a full re-copy | `tasks/clear_channels.py` | None | **Keep** (DANGER-styled, confirmed) |
| 16 | **Access check report** (can the account see the sources and post in the targets; noforwards notes) | `tasks/check_access.py`, `access.json`, panel 🛂 | Only implicit statuses (DIAG-08) | **Keep**, and surface it per direction (DIAG-08) |
| 17 | **Document filename filter** (rename files, strip tags) | `messagefilters/documentfilenamefilter.py` | None | **Keep** (cheap, niche) |
| 18 | **StripFooterFilter** (heuristic removal of the source's trailing promo lines) and **UrlMessageFilter** black/whitelists | `messagefilters/messagefilters.py:101,564`, `misc/urlmatcher.py` | Only by writing regex replacements | **Keep** (higher-level than Junction's recipes) |
| 19 | **Multi-project per VPS** with separate configs, accounts, ports and units; undoable project deletion | `telemirror/projects.py`, `projects/.deleted/` | Projects are labels only | **Keep** |
| 20 | **Session import** (tdata / .session+.json / .jsession, Telegram Desktop fingerprint, `.bak` on overwrite, flock) | `misc/session_import.py`, `misc/jsession.py`, `misc/session_lock.py` | Phone login only | **Keep** |
| 21 | **Safe config editing** (round-trip preserving comments, semantic check, subprocess validation, sha guard, `.bak`, ↩️ rollback, diff on upload) | `bot/configstore.py`, `bot/configedit.py` | `/dump` + `/batch` without validation or diff | **Keep.** It is also the gate for hot reload (A1) |
| 22 | **Notices for account DMs and WARNING+ logs** (debounced, rate-limited) | `mirroring.py:on_private_message` (l.2231), `NoticeLogHandler` (l.2063) | Alerts bot | **Keep** |
| 23 | **Silent-direction marks / last post** | `stats.quiet_days`, `bot/routers/directions.py` | None | **Keep** |
| 24 | **Citadel setup wizard** (creates recipient channels/topics, avatars) | `tasks/setup_mirrors.py` (CLI, hard-coded) | Create chat / copy topic structure | **Refactor or retire.** Extract its generic parts (create channel, copy topic structure) into panel tools (TOP-03, UI-04), then drop the hard-coded wizard or keep it as a one-off script outside the package |
| 25 | **Open-source / self-hosted, no per-message limits, own data** | whole repo | SaaS with plan limits | **Keep** (it's the reason to exist) |

## 7. Open questions for the owner

Each question has a short recommended default. Answering "default" is fine.

1. **Product shape: a single-owner tool or a multi-user SaaS like Junction?** This decides A12, A2 and every SaaS-only row (ACC-08, INT-04, DIAG-10, quotas). *Default: single-owner (plus a few trusted admins). No tenancy.*
2. **Config storage: keep YAML as the source of truth, or move directions/rules to Postgres?** *Default: keep YAML, add stable `id:` per direction, keep runtime state (queues, traces) in Postgres (A2/A4).*
3. **Hot reload: OK to replace "save → 🔁 restart" with live reload on save (and drop the 04:00 restart's "apply config" role)?** *Default: yes. Reload on save via the A11 socket, and keep the daily restart only as hygiene (or remove it).*
4. **Catch-up after downtime: backfill missed posts on every start (could post a burst of old posts after a long outage), and with what maximum age?** *Default: yes, for posts ≤ 6 h old; older gaps → a notice suggesting a history replay.*
5. **Bot-as-sender: should some directions publish through a bot (for buttons, likes, bot fallback on flood)?** *Default: no for now. Revisit only if inline buttons become a real need.*
6. **Accounts: keep "one account per project", or allow per-direction reader/sender accounts and several accounts in one process?** *Default: keep one account per project. Fix the "replay/task pauses live" issue by running jobs inside the live process (A5) instead.*
7. **UI: stay with the chat panel, or build a Telegram mini-app / web UI (table view, drag-and-drop)?** *Default: stay in chat. Add filters/sorting chips and per-direction screens.*
8. **AI: which provider, whose key, what budget?** (OpenAI, OpenRouter, local; a monthly spend cap; behaviour on timeout: send the original or skip.) *Default: one OpenAI-compatible endpoint + key in `.env`, model configurable, 15 s timeout → send the original unchanged (rewrite) / let it pass (classify), monthly spend counter in the weekly report.*
9. **Moderation: review in a group with the panel bot's buttons (recommended), in the panel's private chat, or a separate review bot?** And what happens to posts nobody reviews (expire after N hours)? *Default: a per-project review group where the account posts the copy and the panel bot adds ✅/⏭/✏️ replies; unreviewed posts expire after 24 h.*
10. **Delay: is Telegram's native scheduler (PUB-05: visible and editable in Telegram, no queue needed) enough, or is a hidden bot-side queue (PUB-04) also required?** *Default: native scheduler first. A queue only together with the engagement filter (FLT-07).*
11. **Digests: wanted at all? If yes, which sources, how often, where to publish?** *Default: not now (P2). Revisit after the AI layer exists.*
12. **Scope exclusions: Google Drive archive (INT-01), Max messenger (FWD-06), Stories (FWD-15), copy-by-script (HIST-07), feedback buttons (PROC-15), inline channel search (CMD-15). Any of these needed?** *Default: none.*
13. **Watermark removal: keep investing (it's unique, but untested on the VPS, heavy, and legally sensitive), or freeze it as an optional extra?** *Default: freeze as an optional, off-by-default feature. Prioritize the stamping presets (PROC-18) instead.*
14. **Filter model: keep adding one class per criterion, or introduce one generic Junction-style `RuleFilter` (rows of type/value/allow-block with OR-within/AND-across)?** *Default: add the generic `RuleFilter` for simple criteria (text, regex, media, author, forwarded, time). Keep specialized classes for transformations.*
15. **Contradictions in the reference: which to follow?** *Defaults:* filters on the **original** text by default, with the order user-controlled (telemirror already does this); regex `.` does **not** match newlines unless `(?s)` (Python default, matching Junction example 16, not the troubleshooting page); replacements apply to text only (not images); duplicate memory = time window (`dedup_hours`), not "300 messages"; ignore matrix-only features (delayed deletion, interval filter) until a need appears.
16. **Priority order: agree with the sequence in §5?** That is: catch-up + trace → hot reload + socket → simple filters → store/scheduler → moderation / delay → AI → digests. Or should moderation (your backlog #1) jump ahead of hot reload? *Default: catch-up and "Где копия?" first (small, protects data), then hot reload, then moderation.*
17. **Commits:** this analysis changed no code. When implementation starts, should each step go to `master` with your explicit permission per commit (as per your standing rule)? *Default: yes, per your memory rule: no commits without an explicit "да".*
