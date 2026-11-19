# Junction Bot — Feature Catalog

Knowledge base for agents without site access. Derived only from `pages/*.md` (51 crawled pages, EN translations of junctionbot.io RU docs, fetched 2026-11-19). RU UI labels in parentheses. Payment features (plans pricing, subscriptions, billing, promo codes, balance top-up, auto-renewal, affiliate, channel monetization) are deliberately excluded; tier names appear only as capability gates.

Tags: **[doc]** = stated on a page; **[inferred]** = deduction by the KB author; **[doc-matrix]** = stated only in the plan comparison matrix on `features__ai-digests.md` (marketing table; may disagree with docs — see "Contradictions" at the end).

## Product summary

Junction Bot (@junction_bot) is a Telegram bot + mini-app (also openable as a browser "Web app") that automates moving content between Telegram chats. The core entity is a **forwarding** (пересылка) = one source→destination rule. For each forwarding the bot watches the source (channel, group, forum topic, folder, bot, private chat), runs a pipeline — filters → text replacements → AI processing (order configurable) → attribution (source name / author / link) → buttons / watermarks / media-caption handling — and publishes into the destination either as the bot or as the user's **connected account** (a userbot session the bot logs into), by copy or by native forward, with optional delay, Telegram-native scheduling, rate limiting, pinning, silent mode, and manual moderation via @Junction_Review_Bot. Other product areas: history copying (incl. "script" replay with original pacing), AI **digests** (scheduled LLM summaries of many chats), **projects** (grouping forwardings/digests), Google Drive archiving, settings export/import via commands (`/dump`, `/batch`), and diagnostics (`/track` delivery reports, processing report, message source code).

Architecture facts [doc]: without a connected account, delivery uses Junction's **service user-bot** that joins the source (basic tiers); with a connected account, the bot acts as a separate Telegram client of the user's account and sees whatever that account sees. Regex engine = Java 8 flavor. Telegram limits referenced: bot captions ≤1024 chars (Premium accounts 4× larger), bots cannot delete messages >48h old, ~20–30 posts/min per destination before a flood ban.

## Capability gates (no prices)

| Gate | What it unlocks [doc unless noted] |
|---|---|
| Any tier | Public channels/groups as sources; copy via bot; filters, replacements, header/footer, source info, AI processing, polls, link preview, silent mode, flood reaction, `/track`, processing report |
| Not Economy (Express and up) | Private channels/groups via working invite link; protected open sources; Google Drive file saving (text saving on all) |
| Connected account (Direct, Expert) | Closed sources (no invite link), bots, personal chats, folders, history copying, publishing as account (all account delivery modes), forward edits/deletions, comments, notification ("hidden continuation") buttons, scheduling via Telegram scheduler & delivery frequency (need account mode), own-messages filter, change connected number, multiple connected accounts |
| Expert only | Stories; topic auto-sync; "Copy via account, on flood — via bot"; Replace cross-links with source; Max messenger destination; unlimited folders |
| Add-on "Advanced filters" (Продвинутые фильтры) or "Business" (Бизнес) package | Word-form filter; delayed (engagement) filter |
| Plan-dependent (unspecified tier) | Number of forwardings; moderation mode; watermarks; projects ("higher plans"); digest slots, sources per digest, generations |

Tier speed claims: Economy delivery "usually up to an hour" (docs) vs "1 min" (matrix); Express 5–10 s after connecting to source; Direct ~2 s; Expert ~1 s [doc-matrix].

## Forwarding settings map (where each setting lives)

`Menu → My forwardings (Мои пересылки) → <forwarding> →` [doc]
- **From / To (Откуда / Куда)** gear icons → clone, Change source (Изменить источник) → UI-10, UI-11, ACC-04
- **Copying new (Копирование новых)** → Pause (Приостановить) → UI-12
- **Copy old messages (Скопировать старые сообщения)** → HIST-08
- **Topic mapping (Сопоставление тем)** → TOP-01…06
- **Delivery mode (Режим доставки)** → PUB-01
- **Source info (Информация об источнике)**: Source name, Author, Link to original post, Replace cross-links with source → PROC-10…13
- **Text processing (Обработка текста)**: Add header, Add text after message, Text trimming, Replace links and words in text, AI text processing → PROC-02…07, AI-01
- **Filtering (Фильтрация)**: Keywords and stop words (Ключевые и стоп-слова; also labelled "Filters"/Фильтры), Reactions filter, Filtering order, Filter my messages, Filter forwarded messages, Duplicate filter → FLT-*
- **Scheduling and publishing (Планирование и публикация)**: Forward edits, Forward deletions, Delay, Schedule ("deferred"), Pin posts, Delivery frequency, Silent mode, Save to Google Drive → FWD-09/10, PUB-04…08, INT-01
- **Images and video (Изображения и видео)** (an instruction calls it "Content"/Контент): Media caption, Watermarks → PROC-16/17
- **Buttons (Кнопки)**: Copy buttons, Notification buttons (Кнопки с уведомлениями), Add your own buttons, Feedback buttons → FWD-12/13, PROC-14/15
- **Other content (Прочий контент)**: Polls, Stories, Comments, Link preview → FWD-14…16, PUB-09
- **Moderation (Модерация)** → MOD-*
- **Debug settings (Отладочные настройки)**: Flood reaction, Processing report → PUB-10, DIAG-03
- **Delete (Удалить)** → UI-13

Pipeline order [doc]: receive → (filters, if order = after reception) → replacements (top-to-bottom, then auto cross-link replacement) → (filters, if after replacements) → AI processing → (filters, if after ai) → moderation (if on; filters/replacements already applied) → delay/schedule/frequency → publish. Source name, author and link-to-original are "service text" and are NOT touched by replacements [doc]. Media-type tokens (`<photo>` etc.) and a trailing space may be appended to text for filtering [doc].

## Summary table

| ID | Name | Area | One-liner |
|---|---|---|---|
| JB-ACC-01 | Account connection | ACC | Bot logs into user's Telegram account as a client to read any chat it is in |
| JB-ACC-02 | Connection login flow | ACC | Phone number + 5-digit code from Telegram app |
| JB-ACC-03 | Managing vs connected account | ACC | Account that owns/controls the bot ≠ account(s) that read/publish |
| JB-ACC-04 | Multiple connected accounts / split load | ACC | Several connected numbers; each forwarding bound to one reader account |
| JB-ACC-05 | Change connected number | ACC | Swap the phone number on a connection |
| JB-ACC-06 | Reconnect | ACC | Re-authorize a dead/deleted session |
| JB-ACC-07 | Junction Bot Service Channel | ACC | Auto-created channel for service messages; never delete |
| JB-ACC-08 | Service user-bot (no-account tiers) | ACC | Junction's own userbot joins sources for Economy/Express |
| JB-ACC-09 | Account/settings transfer | ACC | Move number or all settings to another managing account |
| JB-ACC-10 | Security & login warnings | ACC | Official protocol; "unknown device" warning is expected |
| JB-FWD-01 | Forwarding rule | FWD | One source→destination pair; unlimited messages per rule |
| JB-FWD-02 | Source classes | FWD | Open public / open private / protected / closed, tier-gated |
| JB-FWD-03 | Source & destination lookup | FWD | Search by link/@username/invite or pick from chat list |
| JB-FWD-04 | Destinations | FWD | Bot chat feed, channels, groups, users, bots, Max |
| JB-FWD-05 | Forwarding to users/bots | FWD | Account-mode delivery into DMs and third-party bots |
| JB-FWD-06 | Max messenger destination | FWD | Publish into a Max chat/channel (Expert) |
| JB-FWD-07 | Copy vs native forward | FWD | Clone message (editable) vs Telegram forward (immutable, keeps origin) |
| JB-FWD-08 | Delivery latency | FWD | Tier-dependent speed; protected media adds time |
| JB-FWD-09 | Forward edits | FWD | edit / new / ignore propagation of source edits |
| JB-FWD-10 | Forward deletions | FWD | yes / no deletion sync |
| JB-FWD-11 | Media forwarding | FWD | All media types passed by default |
| JB-FWD-12 | Copy original buttons | FWD | none / url / special / all |
| JB-FWD-13 | Notification ("hidden continuation") buttons | FWD | Bot presses callback buttons and transfers pop-up text |
| JB-FWD-14 | Polls | FWD | none / copy / link-under-custom-text |
| JB-FWD-15 | Stories | FWD | message / ignore |
| JB-FWD-16 | Comments | FWD | Copy discussion-group comments as posts or as comments |
| JB-FWD-17 | Premium long captions | FWD | >1024-char captions need account mode + Premium |
| JB-FWD-18 | Premium emoji | FWD | Passed automatically in account mode with Premium |
| JB-FWD-19 | Protected sources | FWD | Copy from copy/forward-restricted chats |
| JB-FWD-20 | Chaining via intermediate channels | FWD | Compose rules A→C→B to split, dedup, AND sources |
| JB-TOP-01 | Topic mapping | TOP | Source topic → destination topic table |
| JB-TOP-02 | Catch-all topic rules | TOP | "All topics" / "All other topics" → Main/General |
| JB-TOP-03 | Copy topic structure | TOP | Bot creates same-named topics in destination |
| JB-TOP-04 | Create topic in mapping | TOP | Create destination topic inline |
| JB-TOP-05 | Many sources → topics | TOP | One forwarding per source, each mapped to a topic |
| JB-TOP-06 | Topic auto-sync | TOP | Auto-create/rename destination topics (Expert) |
| JB-TOP-07 | Folder as source | TOP | Telegram chat folder = live set of sources |
| JB-TOP-08 | Folder vs direct dedup | TOP | Message from A sent once; explicit rule's settings win |
| JB-TOP-09 | Own feed in bot chat | TOP | Send @name/invite link to bot to read in bot chat |
| JB-TOP-10 | Feed channels | TOP | Aggregated channel/group; private, shared or public |
| JB-HIST-01 | History copying | HIST | Copy already-published messages |
| JB-HIST-02 | Interval type | HIST | All / message-number range / publication-time range |
| JB-HIST-03 | History delivery mode & sender | HIST | Bot / account / account-with-bot-fallback |
| JB-HIST-04 | Remove safe pause | HIST | Disable throttling (flood-ban risk) |
| JB-HIST-05 | Error handling policy | HIST | Ask / Skip message / Wait and retry |
| JB-HIST-06 | Start & progress | HIST | "Let's go"; progress message in bot chat |
| JB-HIST-07 | Copy by script | HIST | Replay chat with original authors' accounts and pauses |
| JB-HIST-08 | History with forwarding settings | HIST | "Copy old messages" on configured forwarding |
| JB-HIST-09 | Topic-specific history | HIST | Copy only certain topics' history |
| JB-HIST-10 | History limits & recovery | HIST | Dates reset; download limits; single-message retry |
| JB-FLT-01 | Filtering overview | FLT | Per-forwarding/per-folder, unlimited rules |
| JB-FLT-02 | mustHave / mustNotHave logic | FLT | OR within type, AND across types, any type vetoes |
| JB-FLT-03 | Text-match filter | FLT | Exact, case-sensitive substring |
| JB-FLT-04 | Regex filter | FLT | Java-8 regex over text+media tokens |
| JB-FLT-05 | Word-form filter | FLT | Morphological match RU/EN/UK/DE (add-on) |
| JB-FLT-06 | Date/time filter | FLT | Weekday + time window + timezone |
| JB-FLT-07 | Delayed filter | FLT | Hold post; publish if min reactions/views/forwards/replies |
| JB-FLT-08 | Engagement-ratio filter | FLT | Reactions/forwards/replies per view thresholds |
| JB-FLT-09 | Filtering order | FLT | after reception / after replacements / after ai |
| JB-FLT-10 | Author filter | FLT | By numeric author ID (or by name via workaround) |
| JB-FLT-11 | Own messages filter | FLT | pass / filter messages of the connected account |
| JB-FLT-12 | Media-type filter | FLT | Tokens `<photo>`, `<video>`, … in text filters |
| JB-FLT-13 | Forwarded-messages filter | FLT | all / direct only / forward only |
| JB-FLT-14 | Every n-th message | FLT | `/filter <src> every N` |
| JB-FLT-15 | Duplicate filter | FLT | pass / filter / only_duplicates (300-msg memory) |
| JB-FLT-16 | AI filtering | FLT | AI marks irrelevant posts, text filter drops them |
| JB-FLT-17 | Bulk import of filters | FLT | Import many filters from a table |
| JB-FLT-18 | Copy filters between sources | FLT | `/filter <dst> addAllFrom <src>` |
| JB-FLT-19 | Filters for all sources | FLT | `/filterall`, `/filterrxall`, `/filtertimeall` |
| JB-PROC-01 | Copy-only prerequisite | PROC | Any processing needs a copy delivery mode |
| JB-PROC-02 | Add header | PROC | Prepend text/HTML |
| JB-PROC-03 | Add text after message | PROC | Append footer text/HTML |
| JB-PROC-04 | Text trimming | PROC | Cut to N chars (0 = off) |
| JB-PROC-05 | Replacements | PROC | Ordered A→B rules on body + buttons |
| JB-PROC-06 | Regex replacements | PROC | RE checkbox, `$1` backrefs, `(?s)` |
| JB-PROC-07 | Formatting via HTML | PROC | Add/remove tags with replacements |
| JB-PROC-08 | Premium emoji codes | PROC | `<strong documentid=…>` in replacements/header |
| JB-PROC-09 | Link replacement recipes | PROC | `<a>` links vs plain links vs @usernames |
| JB-PROC-10 | Replace cross-links with source | PROC | Auto-rewrite all links to the source (Expert) |
| JB-PROC-11 | Link to original post | PROC | none / full / custom text |
| JB-PROC-12 | Source name | PROC | none / simple / bold / from_only / id / date / custom |
| JB-PROC-13 | Author | PROC | none / name / username / full / full_except_bot |
| JB-PROC-14 | Own URL buttons | PROC | URL + label per line |
| JB-PROC-15 | Feedback buttons | PROC | none / 1 / 2 / custom words |
| JB-PROC-16 | Media caption | PROC | separate / caption_name / text_only |
| JB-PROC-17 | Watermarks (apply) | PROC | Pick watermark; apply to image/video/animation |
| JB-PROC-18 | Watermark library | PROC | PNG, opacity, scaling, alignment |
| JB-PROC-19 | Third-party bot processing | PROC | Route through other bots and back |
| JB-PROC-20 | Manual edit / media swap | PROC | Done via moderation mode |
| JB-AI-01 | AI text processing | AI | LLM prompt rewrites message text per forwarding |
| JB-AI-02 | Prompt blocks | AI | Active prompt / My prompts / Prompt library |
| JB-AI-03 | Prompt actions & sharing | AI | Apply, Edit, Copy, Stop; one prompt across forwardings |
| JB-AI-04 | Custom prompt | AI | Name, description, text, creativity |
| JB-AI-05 | AI usage mode (global) | AI | Free / platform balance / own API key |
| JB-AI-06 | Models | AI | 1 default free model; 300+ via OpenRouter; OpenAI |
| JB-AI-07 | Free AI quota | AI | Free processings per 30 days, plan-dependent |
| JB-AI-08 | Preset "Ad check" | AI | Marks ads with a keyword for filtering |
| JB-AI-09 | Preset "Potential client detection" | AI | Marks non-leads with НЕ_ЛИД |
| JB-AI-10 | AI use cases | AI | Translate, summarize, rewrite, sentiment, moderation… |
| JB-PUB-01 | Delivery mode | PUB | 6 modes: bot/account × copy/forward + hybrids |
| JB-PUB-02 | Publish as bot vs account | PUB | Identity in destination; admin requirements |
| JB-PUB-03 | Anonymous group posting | PUB | Account admin anonymity → posts as the group |
| JB-PUB-04 | Publication delay (bot queue) | PUB | Fixed/random delay; queue not editable |
| JB-PUB-05 | Schedule (Telegram scheduler) | PUB | Put into native scheduled messages |
| JB-PUB-06 | Delivery frequency | PUB | Min interval between posts per source |
| JB-PUB-07 | Pin posts | PUB | off / pass / silent / notify |
| JB-PUB-08 | Silent mode | PUB | pass / never / always |
| JB-PUB-09 | Link preview | PUB | pass / never / always |
| JB-PUB-10 | Flood reaction | PUB | Ignore / Stop / Postpone (default) / Notify |
| JB-PUB-11 | Flood mitigation | PUB | Account mode, fallback mode, rate, split |
| JB-PUB-12 | Delayed deletion | PUB | Delete after preset time (matrix only) |
| JB-MOD-01 | Moderation mode | MOD | Hold each post for approval in @Junction_Review_Bot |
| JB-MOD-02 | Moderation in own chat | MOD | Review in chosen group/channel |
| JB-MOD-03 | Publish / Skip / edit | MOD | Edit then publish; re-publish allowed |
| JB-MOD-04 | Moderation side effects | MOD | Forces copy via account; no buttons; no edit sync |
| JB-MOD-05 | Moderation extras (claimed) | MOD | Scheduling, team collaboration |
| JB-DIG-01 | Digests | DIG | AI summary of many chats on schedule |
| JB-DIG-02 | Quick digest (3 clicks) | DIG | Paste links → auto settings |
| JB-DIG-03 | Scheduled vs instant | DIG | Slots-limited auto vs unlimited manual |
| JB-DIG-04 | Generate now | DIG | Run any digest immediately |
| JB-DIG-05 | Digest templates | DIG | Template library / My templates |
| JB-DIG-06 | Digest prompt editor | DIG | Prompt text, model, temperature 0–2, example |
| JB-DIG-07 | Consider past digests | DIG | 0–10 previous generations as context |
| JB-DIG-08 | Prompt metadata fields | DIG | text, date, author_id, views_count, … |
| JB-DIG-09 | Digest sources | DIG | Public / invite / closed, tier-gated |
| JB-DIG-10 | Topic selector | DIG | "All topics" = 1 slot |
| JB-DIG-11 | Publication time | DIG | Same time daily or per-day multiple slots |
| JB-DIG-12 | Publication place | DIG | Bot chat or external chat, as bot or account |
| JB-DIG-13 | Digest preview | DIG | Generate for a period before publishing |
| JB-DIG-14 | Digest statuses | DIG | Pending / Generating / Disabled / Suspended |
| JB-DIG-15 | Digest actions | DIG | Disable, copy, generate now, move to project |
| JB-DIG-16 | Digest limits | DIG | Generations, sources, 50 msgs (free), 1-week window |
| JB-PROJ-01 | Projects | PROJ | Group forwardings and digests |
| JB-PROJ-02 | Project switcher | PROJ | Burger menu; "All projects"; default Project #1 |
| JB-PROJ-03 | Move to project | PROJ | ⋮ → Move to project (+ create inline) |
| JB-PROJ-04 | Manage projects | PROJ | Counters, create, rename, delete-if-empty |
| JB-INT-01 | Save to Google Drive | INT | Archive text/media; links sent instead |
| JB-INT-02 | Export settings (/dump) | INT | File of bot commands |
| JB-INT-03 | Import settings (/batch) | INT | Execute multi-line command list |
| JB-INT-04 | Interface language (/language) | INT | EN / RU |
| JB-INT-05 | No webhook/API (by design) | INT | Forward into your own bot instead |
| JB-DIAG-01 | Delivery tracking (/track) | DIAG | Per-message report + auto-diagnostics |
| JB-DIAG-02 | Delivery report outcomes | DIAG | Delivered / blocked by mustHave / mustNotHave |
| JB-DIAG-03 | Processing report | DIAG | Per-message debug report (enable in advance) |
| JB-DIAG-04 | Message source code | DIAG | How the bot "sees" a message |
| JB-DIAG-05 | @junction_helper0_bot | DIAG | Returns source code of forwarded messages |
| JB-DIAG-06 | Regex debugging | DIAG | regex101, Java 8, single-line + global |
| JB-DIAG-07 | Junction Bot Alerts bot | DIAG | Separate bot for system notifications |
| JB-DIAG-08 | Forwarding statuses & auto-disable | DIAG | connecting…, (expired), disabled on errors |
| JB-DIAG-09 | Troubleshooting playbook | DIAG | Known symptoms → fixes |
| JB-DIAG-10 | Support channels | DIAG | Support bot, user group, Junction Bro AI |
| JB-CMD-01 | /track | CMD | Delivery report wizard |
| JB-CMD-02 | /disableall, /enableall | CMD | Pause/resume all forwardings |
| JB-CMD-03 | /dump | CMD | Export settings |
| JB-CMD-04 | /batch | CMD | Run many commands |
| JB-CMD-05 | /language | CMD | Switch UI language |
| JB-CMD-06 | /filter | CMD | List/toggle filters of one source; every N; addAllFrom |
| JB-CMD-07 | /filterall | CMD | Add/remove text filter on all sources; DELETE ALL |
| JB-CMD-08 | /filterrxall | CMD | Add/remove regex filter on all sources |
| JB-CMD-09 | /filtertime | CMD | Date/time filter on one source |
| JB-CMD-10 | /filtertimeall | CMD | Date/time filter on all sources |
| JB-CMD-11 | /replace | CMD | Plain replacement rule |
| JB-CMD-12 | /replacerx | CMD | Regex replacement rule |
| JB-CMD-13 | /setting | CMD | author / header / mybuttons / like |
| JB-CMD-14 | /settingchannel | CMD | Per-channel setting (e.g. duplicate filter) |
| JB-CMD-15 | Inline channel search | CMD | `@junction_bot <word>` |
| JB-CMD-16 | Subscribe by message | CMD | Send @name / invite link to bot chat |
| JB-UI-01 | Mini-app & menus | UI | Menu button, main menu, burger side menu |
| JB-UI-02 | Forwarding creation wizard | UI | Source → Destination → Topic mapping → Main settings |
| JB-UI-03 | Default configuration | UI | New forwarding works without setup |
| JB-UI-04 | Create new chat | UI | Create destination channel/group in wizard |
| JB-UI-05 | Chat picker & pin workaround | UI | Pin chat to make it appear in list |
| JB-UI-06 | Table view | UI | Columns, filter, multi-sort, tabs |
| JB-UI-07 | Mobile display modes | UI | Compact / Wide / Auto |
| JB-UI-08 | Web app | UI | Open mini-app in a browser |
| JB-UI-09 | Saved table layout | UI | Persisted; "Default settings" resets |
| JB-UI-10 | Clone forwarding | UI | Copy with all settings to new source/destination |
| JB-UI-11 | Change source | UI | Rebind source (incl. reader account) |
| JB-UI-12 | Pause forwarding | UI | Keep settings, stop copying new |
| JB-UI-13 | Delete forwarding | UI | Irreversible, settings lost |
| JB-UI-14 | Personal account screen | UI | Connections, reconnect, number change |

---

## ACC — Accounts & connection

### JB-ACC-01 — Account connection (Подключение аккаунта)
- Description: @junction_bot connects to the user's Telegram account "as a separate Telegram client" (third-party client protocol) and then sees/forwards every message visible to that account, including personal chats, bots, closed and copy-protected chats, folders. Enables publishing on behalf of the account. Bot can act "without revealing its own presence".
- Where in UI: offered inline when creating a forwarding or digest ("You have a package that requires account connection to work" → `Connect account (Подключить аккаунт)`); also `Menu → Personal account (Личный кабинет) → package card → Connect account`.
- Parameters / options: phone number of any Telegram account (work/secondary numbers OK).
- Limits: requires a connected-account tier (Direct/Expert); number of connections = number of such packages (plan-dependent). The account must remain a member of sources; if removed, copying stops.
- Relations: prerequisite for FWD-02 (closed sources), FWD-05, FWD-09/10/13/15/16, TOP-07, HIST-*, PUB-01 account modes, PUB-05/06, FLT-11, MOD-01, DIG-09 (private). See ACC-02…07.
- Sources: pages/documentation__account-connection.md, pages/features__account-connection.md, pages/documentation__getting-started.md, pages/documentation__forwarding.md
- Tag: [doc]

### JB-ACC-02 — Connection login flow
- Description: Enter phone number; Telegram sends a 5-digit login code inside the official Telegram chat (not SMS); enter it in the bot chat. After success, the account's chats appear in source/destination lists of forwardings and digests.
- Where in UI: bot chat (mini-app hands off: "leave the app and go to the chat with Junction Bot").
- Parameters / options: phone starting with `+`; code.
- Limits: a number already used in the bot under another managing account must be transferred first (ACC-09). 2FA (cloud password) handling not documented.
- Relations: ACC-01, ACC-05, ACC-06, ACC-10.
- Sources: pages/documentation__account-connection.md, pages/documentation__troubleshooting.md, pages/instructions__how-to-split-forwardings-into-2-accounts.md, pages/instructions__how-to-change-connected-account.md
- Tag: [doc]

### JB-ACC-03 — Managing account vs connected account (управляющий аккаунт / подключенный аккаунт)
- Description: The *managing account* is the Telegram account that talks to @junction_bot, owns the subscription and configures everything. A *connected account* is a Telegram account the bot logs into to read sources/publish. They can differ (e.g. connect a work or second account). One managing account can manage many connected accounts.
- Where in UI: `Menu → Personal account`.
- Parameters / options: —
- Limits: what matters is that the connected account is a member of the sources.
- Relations: ACC-01, ACC-04, PUB-02 ("Copy via bot" requires the user — managing or one of their connected accounts — to be admin in destination).
- Sources: pages/documentation__account-connection.md, pages/documentation__getting-started.md, pages/documentation__forwarding.md
- Tag: [doc]

### JB-ACC-04 — Multiple connected accounts / splitting forwardings (Подключение нового аккаунта)
- Description: Connect several numbers and assign each forwarding's source to a specific connection, spreading load (flood/download limits) across accounts. Also used for "Copy by script" (HIST-07) where several accounts act as actors.
- Where in UI: `Menu → ☰ → My account (Мой аккаунт) → Connect a new account (Подключение нового аккаунта)`; then `Menu → <forwarding> → From (Откуда) ⚙ → Change source (Изменить источник) → expand list → select connection`.
- Parameters / options: per-forwarding reader connection.
- Limits: each extra connection needs an extra connected-account package (plan-dependent). New account must be a member of the source.
- Relations: UI-11, PUB-11 (split traffic between accounts), UI-06 (group table tabs by "Source account phone").
- Sources: pages/instructions__how-to-split-forwardings-into-2-accounts.md, pages/documentation__publishing-and-moderation.md, pages/documentation__copying-old-messages.md
- Tag: [doc]; motivation (rate limits) [inferred] partly, flood split is [doc].

### JB-ACC-05 — Change connected account number (Поменять номер подключенного аккаунта)
- Description: Replace the phone number bound to a connected-account package; bot asks for the new number and Telegram code.
- Where in UI: `Menu → app menu icon/☰ → My account (Мой аккаунт) / Personal account → edit icon 📝 on package card → Change the number of the connected account`.
- Parameters / options: new number with `+`.
- Limits: only on connected-account tiers; first change free, further changes are billed (billing details excluded). Effect on existing forwardings not documented.
- Relations: ACC-02, ACC-06.
- Sources: pages/instructions__how-to-change-connected-account.md, pages/documentation__troubleshooting.md
- Tag: [doc]

### JB-ACC-06 — Reconnect (Переподключить)
- Description: Restore a connection whose session was deleted (e.g. user terminated the session) or became inactive. Deleted session = bot can't receive or send.
- Where in UI: `Menu → Personal account → "Reconnect" next to the phone number`; also from digest status "Suspended: session broken".
- Parameters / options: —
- Limits: —
- Relations: ACC-01, DIG-14, DIAG-09.
- Sources: pages/documentation__account-connection.md, pages/documentation__troubleshooting.md, pages/documentation__digests.md
- Tag: [doc]

### JB-ACC-07 — Junction Bot Service Channel
- Description: Channel the bot creates on the connected account for service messages. Must not be deleted (archive is fine). Also: never block/delete the chat with @junction_bot from the connected account — some messages would fail to forward.
- Where in UI: appears in the connected account's Telegram chat list.
- Parameters / options: —
- Limits: exact purpose not specified.
- Relations: ACC-01, DIAG-07.
- Sources: pages/documentation__account-connection.md, pages/documentation__getting-started.md, pages/documentation__troubleshooting.md
- Tag: [doc]

### JB-ACC-08 — Service user-bot (no-account delivery)
- Description: On no-account tiers (Economy/Express) Junction's own service user account joins the source when a forwarding is created and reads it. First-time sources show status "connecting…" (one-time delay). If the service account is banned or the invite link dies, the source is lost (status "(expired)") and only connected-account tiers can use it.
- Where in UI: forwarding page status.
- Parameters / options: —
- Limits: Economy: public only, delayed (≈ up to 1 h); Express: + invite-link private/protected sources, near-instant after connection.
- Relations: FWD-02, FWD-08, DIAG-08.
- Sources: pages/documentation__troubleshooting.md, pages/documentation__forwarding.md, pages/documentation__getting-started.md
- Tag: [doc]

### JB-ACC-09 — Account / settings transfer
- Description: (a) If a phone number is already bound under another managing account, log in under that account and transfer the number in Personal account. (b) To move all settings to a new managing Telegram account, contact support with the new username/ID.
- Where in UI: `Personal account (Личный кабинет)`; support bot.
- Parameters / options: —
- Limits: full transfer is support-assisted only.
- Relations: INT-02/03 (self-service partial migration via /dump + /batch).
- Sources: pages/documentation__troubleshooting.md
- Tag: [doc]

### JB-ACC-10 — Security & login warnings
- Description: Access rights are granted only to the bot (not staff); official secure Telegram protocol; a "new device/unknown device" warning right after connecting is expected. Marketing claims no account bans in 7+ years.
- Where in UI: —
- Parameters / options: —
- Limits: —
- Relations: ACC-01.
- Sources: pages/documentation__account-connection.md, pages/documentation__troubleshooting.md, pages/features__ai-digests.md
- Tag: [doc]

---

## FWD — Forwarding core

### JB-FWD-01 — Forwarding rule (Пересылка)
- Description: Basic entity: a rule transferring messages from one source to one destination (with transformation). Count of forwardings = count of source–destination pairs (a folder source counts as one source [inferred]). Messages per rule are never limited. Native forwarding and copying both supported.
- Where in UI: create `Menu → Main functions → Forward messages (Основные функции → Пересылать сообщения)` or `Menu → Create forwarding (Создать пересылку)`; list `Menu → My forwardings`.
- Parameters / options: source, destination, topic mapping, forwarding type (New messages / Old messages (history)), delivery mode, link auto-replacement, plus all settings in the settings map.
- Limits: number of forwardings plan-dependent (docs examples 25 or 100; matrix 25/25/100/unlimited).
- Relations: UI-02, UI-03, all areas.
- Sources: pages/documentation__forwarding.md, pages/documentation__getting-started.md, pages/features__message-forwarding.md, pages/features__ai-digests.md
- Tag: [doc]

### JB-FWD-02 — Source classes (Источники пересылок)
- Description: Open sources = public channels/groups; private channels/groups with a working invite link. Protected sources = admins disabled copying/forwarding ("Copying and forwarding is not allowed in this channel"). Closed sources = private chats/channels without invite link, other bots, personal chats with users. Also: folders, forums (topic groups), discussion groups.
- Where in UI: "Specify source (Укажи источник)" screen.
- Parameters / options: —
- Limits: open public — any tier; open private & protected open — any tier except Economy; closed — Direct/Expert only. With invite-link sources, delivery is guaranteed only while the link works and the bot isn't banned.
- Relations: ACC-01, ACC-08, FWD-03, FWD-19, TOP-07.
- Sources: pages/documentation__forwarding.md, pages/documentation__getting-started.md, pages/features__message-forwarding.md
- Tag: [doc]

### JB-FWD-03 — Source & destination lookup (Найти канал в Telegram)
- Description: Without connected account: type a link, @username or (Express+) invite link and press "➤ Find channel in Telegram", then pick the result. With connected account: pick from the list of all the account's chats (folders 📁 listed on top). The same for destinations.
- Where in UI: wizard screens "Specify source" / "Specify destination (Укажи назначение)".
- Parameters / options: —
- Limits: missing chats → UI-05 workaround; a bot appears in destination list only after you message it once.
- Relations: UI-02, UI-05, CMD-15.
- Sources: pages/documentation__forwarding.md, pages/documentation__getting-started.md, pages/instructions__how-to-forward-from-public-telegram-channel-or-group.md, pages/instructions__how-to-forward-from-private-telegram-channel-or-group.md
- Tag: [doc]

### JB-FWD-04 — Destinations (Назначения: ленты, каналы, группы, боты)
- Description: Allowed destinations: own chat with Junction Bot (feed, TOP-09); channels where you are admin; groups where you or the bot can post; other users and bots (account mode); a chat/channel in Max messenger (Expert).
- Where in UI: "Specify destination" screen.
- Parameters / options: —
- Limits: As bot: bot + user (or one of user's connected accounts) must be admins, bot with posting rights. As account: only posting rights for the account. Publishing as account incl. DMs — Direct/Expert.
- Relations: PUB-01, PUB-02, FWD-05, FWD-06, TOP-09.
- Sources: pages/documentation__forwarding.md, pages/documentation__getting-started.md
- Tag: [doc]

### JB-FWD-05 — Forwarding to other users and bots (Пересылка другим ботам)
- Description: Deliver into a private chat with a user or a third-party bot; automatically sent on behalf of the connected account, no need to add Junction Bot there. Used to feed external bots (processing, own API bot).
- Where in UI: `Menu → Main functions → Forward messages → Specify source → Specify destination`.
- Parameters / options: —
- Limits: Direct/Expert. Bot must be in your chat list (send it any message first).
- Relations: PROC-19, INT-05, PUB-02.
- Sources: pages/documentation__forwarding.md, pages/documentation__publishing-and-moderation.md
- Tag: [doc]

### JB-FWD-06 — Max messenger destination
- Description: Forward from Telegram into a chat or channel in the Max messenger (referenced via a blog article).
- Where in UI: destination selection [inferred].
- Parameters / options: not documented.
- Limits: Expert.
- Relations: FWD-04.
- Sources: pages/documentation__forwarding.md
- Tag: [doc] (details absent)

### JB-FWD-07 — Copy vs native forward (Копировать / Пересылать)
- Description: Copy = new message cloned from the original (views counted separately; all processing possible). Forward = Telegram's forward mechanism, keeps "Forwarded from" name and link of origin; views count toward the source; message cannot be modified at all (no header, replacements, AI, buttons, edits propagation).
- Where in UI: chosen through Delivery mode (PUB-01).
- Parameters / options: see PUB-01.
- Limits: forward requires the source to allow forwarding; forward is only available via connected account.
- Relations: PROC-01, AI-01, FWD-09, PUB-01, PROC-13 (forward keeps author).
- Sources: pages/documentation__publishing-and-moderation.md, pages/documentation__message-processing.md, pages/features__message-forwarding.md
- Tag: [doc]

### JB-FWD-08 — Delivery latency
- Description: Economy: delayed, usually up to an hour from public channels (sometimes longer). Express: some time to connect to new sources, then instant. Direct/Expert: instant. Copy-protected sources add time to fully process protected media (size-dependent). Use `/track` for unexplained delay.
- Where in UI: —
- Parameters / options: —
- Limits: matrix claims 1 min / 5–10 s / 2 s / 1 s (Economy/Express/Direct/Expert); Telegram max ≈1 s.
- Relations: ACC-08, DIAG-01, FWD-19.
- Sources: pages/documentation__getting-started.md, pages/documentation__troubleshooting.md, pages/features__ai-digests.md
- Tag: [doc] / [doc-matrix] (conflicting for Economy)

### JB-FWD-09 — Forward edits (Передавать правки)
- Description: What to do when the source message is edited after forwarding.
- Where in UI: `Menu → My forwardings → <fwd> → Scheduling and publishing → Forward edits`.
- Parameters / options: `edit` — apply edit to destination copy; `new` — send edited version as a new message (re-sends every edit, can look like duplicates); `ignore`. Default: enabled on connected-account tiers per troubleshooting [doc]; exact default value not stated (`edit` [inferred]).
- Limits: Direct/Expert. Copy mode only (forwarded messages never change). If a delay is set and the original is edited before publication, the edit is not applied. If the original didn't pass filters, the edit can't pass either; if the original passed but the edit doesn't, the copy is not changed. Not propagated in moderation mode.
- Relations: FWD-07, PUB-04, FLT-15, MOD-04, DIAG-09.
- Sources: pages/documentation__forwarding.md, pages/documentation__troubleshooting.md, pages/documentation__publishing-and-moderation.md
- Tag: [doc]

### JB-FWD-10 — Forward deletions (Передавать удаления)
- Description: Delete destination copies when the original is deleted.
- Where in UI: `… → Scheduling and publishing → Forward deletions`.
- Parameters / options: `yes` / `no`.
- Limits: Direct/Expert. Bots can't delete messages older than 48 h → use account delivery mode for older ones.
- Relations: PUB-01, DIAG-09 (fix for duplicates posted then deleted in source).
- Sources: pages/documentation__forwarding.md, pages/documentation__troubleshooting.md
- Tag: [doc]

### JB-FWD-11 — Media forwarding (Пересылка медиа)
- Description: All media types forwarded by default: images, video, audio, voice, stickers, documents, GIFs, round videos, locations, polls, etc. Control via media-type filters, media caption mode and watermarks.
- Where in UI: —
- Parameters / options: —
- Limits: caption length (FWD-17); albums supported in filters (regex example "including albums").
- Relations: FLT-12, PROC-16, PROC-17, HIST-01.
- Sources: pages/documentation__forwarding.md, pages/features__message-forwarding.md, pages/documentation__filters.md
- Tag: [doc]

### JB-FWD-12 — Copy original buttons (Копировать кнопки)
- Description: Which inline buttons of the source message to keep.
- Where in UI: `… → Buttons → Copy buttons`.
- Parameters / options: `none`; `url` — only link buttons; `special` — everything except link buttons; `all`. Only URL buttons will actually work after copying.
- Limits: In account copy modes buttons transfer only if the connected account has Telegram Premium (rich text; only link buttons). In "Forward via account" or without Premium — not transferred. Troubleshooting advice: switch to Copy via bot if buttons missing. Moderation drops original buttons. Duplicate filter ignores buttons.
- Relations: PUB-01, PROC-05 (replacements apply to button text), PROC-14, MOD-04, FLT-15.
- Sources: pages/documentation__forwarding.md, pages/documentation__troubleshooting.md
- Tag: [doc]

### JB-FWD-13 — Notification ("hidden continuation") buttons (Кнопки с уведомлениями / Скрытое продолжение)
- Description: Source posts with callback buttons that show a pop-up text. The bot presses the button itself, reads the pop-up and reproduces it (a plain duplicate would lose the response).
- Where in UI: `… → Buttons → Notification buttons`.
- Parameters / options: `none`; `.*` — all notification buttons; custom value = `<regex for button text> [<min>-<max> seconds] [body]`. Example `.* 15-300` → press each with random 15–300 s delay (human-like). `.* 15-300 body` → put pop-up text into message body instead of a button.
- Limits: Direct/Expert; not supported when sending on behalf of account. Everyone in the destination sees the pop-up text *you* saw; per-subscriber pop-ups impossible. Press delay delays delivery.
- Relations: PROC-05 (replacements apply to button text and notification content), PUB-01.
- Sources: pages/documentation__forwarding.md, pages/features__ai-digests.md
- Tag: [doc]

### JB-FWD-14 — Polls (Опросы)
- Where in UI: `… → Other content → Polls`.
- Description: How Telegram polls are transferred.
- Parameters / options: `none` — not forwarded; `copy` — new poll with same text; custom string — a link to the original poll placed under this string (e.g. `пройдите опрос`).
- Limits: `<poll>` token can filter polls.
- Relations: FLT-12.
- Sources: pages/documentation__forwarding.md
- Tag: [doc]

### JB-FWD-15 — Stories (Истории)
- Description: How source Stories are transferred.
- Where in UI: `… → Other content → Stories`.
- Parameters / options: `message` — send the story as a regular message; `ignore`.
- Limits: Expert (docs) / Direct+Expert (matrix). Marketing mentions "text from stories".
- Relations: —
- Sources: pages/documentation__forwarding.md, pages/features__message-forwarding.md, pages/features__ai-digests.md
- Tag: [doc]

### JB-FWD-16 — Comments (Комментарии)
- Description: Channel comments live in a linked discussion group (find it via channel ⋮ → "View discussion"). The connected account must join that group and stay. Two methods: (1) **as separate posts** — create a forwarding from the discussion group to any destination; (2) **as comments** — two forwardings: source channel → destination channel (no special settings) and source discussion group → destination discussion group; in the second, set Comments to the source *channel's* numeric ID (e.g. `2015095027`, not the group's). Bot must be admin in destination discussion group. For comments to appear as from the group, use account publishing (PUB-01, PUB-03).
- Where in UI: `… → Other content → Comments`.
- Parameters / options: custom value = source channel ID.
- Limits: Direct/Expert. Works only for posts published after setup.
- Relations: ACC-01, PUB-01.
- Sources: pages/documentation__forwarding.md, pages/documentation__getting-started.md
- Tag: [doc]

### JB-FWD-17 — Telegram Premium long captions
- Description: Premium users can post captions longer than the 1024-char bot limit (4×). Bot must trim them. To pass as-is: connected account with active Premium + Copy via account delivery. Alternative: Media caption `separate` sends text as a separate message so it arrives in full.
- Where in UI: Delivery mode; Media caption.
- Parameters / options: —
- Limits: Direct/Expert + Premium.
- Relations: PUB-01, PROC-16, FWD-18.
- Sources: pages/documentation__forwarding.md, pages/documentation__troubleshooting.md
- Tag: [doc]

### JB-FWD-18 — Premium emoji (Premium эмодзи)
- Description: Premium custom emoji are transferred automatically if delivery is on behalf of the account and that account has Premium. Insert/replace your own premium emoji via PROC-08.
- Where in UI: Delivery mode.
- Parameters / options: —
- Limits: Direct/Expert + Premium.
- Relations: PROC-08, PUB-01.
- Sources: pages/documentation__forwarding.md, pages/documentation__message-processing.md, pages/documentation__troubleshooting.md
- Tag: [doc]

### JB-FWD-19 — Protected (copy-restricted) sources
- Description: Copy from channels that forbid copying/forwarding; bot fully re-processes protected media (slower). Forward-type delivery modes skip or fall back (PUB-01).
- Where in UI: —
- Parameters / options: —
- Limits: protected open sources: all tiers except Economy; protected closed: Direct/Expert.
- Relations: FWD-02, FWD-08, PUB-01 ("Forward via account, on protection — copy").
- Sources: pages/documentation__forwarding.md, pages/features__message-forwarding.md, pages/documentation__troubleshooting.md, pages/features__history-copying.md
- Tag: [doc]

### JB-FWD-20 — Chaining via intermediate channels (Использование промежуточных каналов)
- Description: Documented pattern of composing several forwardings through an intermediate channel C to: apply a setting to a filtered subset (A→C filtered "pass" + A→D filtered "stop", then C→B with buttons, D→B plain); dedup after replacements (A→C with replacements, C→B with duplicate filter); strip author names after author filtering; publish only messages present in two sources (two rules into C, C→B with `only_duplicates`); per-destination rate (frequency on C→B).
- Where in UI: ordinary forwardings.
- Parameters / options: —
- Limits: each hop counts as a forwarding [inferred].
- Relations: FLT-10, FLT-15, PROC-14, PUB-06, PROC-19.
- Sources: pages/documentation__message-processing.md, pages/documentation__filters.md, pages/documentation__publishing-and-moderation.md
- Tag: [doc]

---

## TOP — Topics, folders & feeds

### JB-TOP-01 — Topic mapping (Сопоставление тем)
- Description: Table of redirects "source topic → destination topic" for forum groups. Any source/destination combination works as long as at least one side has topics: group→group (same or different structure), several topics of one group → a topic or a channel, several channels → different topics of one group. Shown as a wizard step after choosing destination (skip if no topics) and editable later.
- Where in UI: wizard "Topic mapping" screen; later `Menu → My forwardings → <fwd> → Topic mapping`.
- Parameters / options: rows of (source topic | All topics | All other topics) → (destination topic | Main/General topic); buttons "Copy topic structure", "Create topic"; checkbox "Sync topics automatically".
- Limits: destination topics require `Group menu > Group settings > Topics: ON` in Telegram. Matrix: topic mapping Direct/Expert.
- Relations: TOP-02…06, HIST-09, FLT-01 (topic mapping acts as a topic filter [inferred]), DIG-10.
- Sources: pages/documentation__forwarding.md, pages/features__topic-mapping.md, pages/instructions__how-to-forward-messages-between-topics-in-telegram-groups.md
- Tag: [doc]

### JB-TOP-02 — Catch-all topic rules (Все темы / Все остальные темы / Главная тема)
- Description: Defaults: destination without topics/channel → "All topics" redirected to it (or choose specific topics only). Destination with topics → "All topics → Main (General) topic". Adding any explicit row turns "All topics" into "All other topics", which also covers topics created later. Rows are deletable (default rule can be removed).
- Where in UI: Topic mapping screen.
- Parameters / options: All topics (Все темы), All other topics (Все остальные темы), Main topic / General (Главная тема / Общая тема).
- Limits: without a catch-all row, messages from unmapped/new topics are not forwarded [inferred].
- Relations: TOP-01, TOP-03.
- Sources: pages/documentation__forwarding.md, pages/instructions__how-to-forward-messages-from-several-topics-to-general-topic.md, pages/instructions__how-to-copy-topic-structure.md
- Tag: [doc]

### JB-TOP-03 — Copy topic structure (Скопировать структуру тем)
- Description: Bot creates in the destination as many topics as the source currently has, with identical names (renamable later) and maps them 1:1; first row created is "All other topics → Main topic" (keep it for future topics or delete). Confirm with "Let's go (Поехали)", then "Next (Далее)".
- Where in UI: Topic mapping screen.
- Parameters / options: —
- Limits: snapshot at time of copy; new source topics not auto-created unless TOP-06. Topic icons/colors not mentioned.
- Relations: TOP-01, TOP-02, TOP-06.
- Sources: pages/documentation__forwarding.md, pages/instructions__how-to-copy-topic-structure.md, pages/features__topic-mapping.md
- Tag: [doc]

### JB-TOP-04 — Create topic from mapping screen (Создать тему)
- Description: Create a new topic in the destination group directly from the mapping page.
- Where in UI: Topic mapping → "Create topic".
- Parameters / options: topic name [inferred].
- Limits: —
- Relations: TOP-01.
- Sources: pages/documentation__forwarding.md
- Tag: [doc]

### JB-TOP-05 — Many sources into different topics
- Description: To route several groups/channels into different topics of one group, create one forwarding per source and choose the destination topic in each one's mapping.
- Where in UI: Topic mapping per forwarding.
- Parameters / options: —
- Limits: each source = one forwarding.
- Relations: TOP-01, FWD-01.
- Sources: pages/documentation__forwarding.md
- Tag: [doc]

### JB-TOP-06 — Topic auto-sync (Синхронизировать темы автоматически)
- Description: When a new topic appears in the source, the bot creates it in the destination; renaming in source renames destination topic.
- Where in UI: `Menu → My forwardings → <fwd> → Topic mapping → "Sync topics automatically"`.
- Parameters / options: on/off.
- Limits: Expert. Only topics created after enabling; deletions are not synced; source must be a group with topics (not a folder or personal chat).
- Relations: TOP-03.
- Sources: pages/documentation__forwarding.md
- Tag: [doc]

### JB-TOP-07 — Folder as source (Группировка источников по папкам / Пересылка из папок)
- Description: Use a Telegram chat folder of the connected account as one source; one set of settings (filters, topic mapping, etc.) applies to all chats in it. Folder composition changes are reflected automatically. Picker shows folder composition (counts of channels, groups, personal chats).
- Where in UI: Specify source → 📁 folders at top of the list (wait a few minutes and refresh if new).
- Parameters / options: —
- Limits: Direct/Expert; only chats explicitly listed in the folder are used — "include all channels"-type rules are ignored. Matrix: Direct 5 folders, Expert unlimited. Not usable with topic auto-sync.
- Relations: TOP-08, FLT-01 (filters can apply to all folder sources), TOP-10.
- Sources: pages/documentation__forwarding.md, pages/features__folders-forwarding.md, pages/features__feed-aggregation.md, pages/features__ai-digests.md
- Tag: [doc]

### JB-TOP-08 — Folder vs direct forwarding dedup
- Description: If source A is in a folder forwarding and also has its own forwarding, a message from A is transferred only once, using the settings of the explicit (direct) forwarding.
- Where in UI: —
- Parameters / options: —
- Limits: stated for same destination? Not specified [inferred: applies generally].
- Relations: TOP-07, FLT-15.
- Sources: pages/documentation__forwarding.md
- Tag: [doc]

### JB-TOP-09 — Own feed in bot chat (Пересылка в свою ленту)
- Description: Read sources as one feed directly in the chat with @junction_bot. Send the bot a public channel/group @name (no membership needed) or a private invite link; you get subscribed.
- Where in UI: bot chat (message, not mini-app).
- Parameters / options: —
- Limits: delivery guaranteed only while the invite link works and bot not banned; otherwise connected account needed.
- Relations: CMD-16, FWD-04, INT-02 (/dump exports "subscriptions").
- Sources: pages/documentation__forwarding.md
- Tag: [doc]

### JB-TOP-10 — Feed channels (Лента / Агрегация ленты)
- Description: A feed = chat collecting messages from many sources (via multiple forwardings or a folder) with filters/editing. Any number of feeds (marketing). Feed can be private, shared with friends, or a public channel; user creates/chooses the channel and sets its name/picture.
- Where in UI: ordinary forwardings into the feed chat.
- Parameters / options: —
- Limits: number of forwardings plan-dependent.
- Relations: FWD-01, TOP-07, FLT-*.
- Sources: pages/features__feed-aggregation.md
- Tag: [doc] (marketing page)

---

## HIST — History copying

### JB-HIST-01 — History copying (Копирование старых сообщений / Копирование истории)
- Description: Copy already-published messages from any source the connected account is a member of (incl. bots, closed chats, protected channels), as-is or with filters/modifications, in the background. Order preserved.
- Where in UI: `Menu → Main functions → Copy chat history (Копировать историю чата) → Specify source and destination → Main settings → Forwarding type: Old messages (history)`; or during any forwarding creation choose forwarding type "Old messages (history) (Старые сообщения (история))".
- Parameters / options: HIST-02…07.
- Limits: Direct/Expert. Copied messages get the current date — original dates cannot be preserved. Speed/max not stated.
- Relations: ACC-01, HIST-08, INT-01, DIAG-01.
- Sources: pages/documentation__copying-old-messages.md, pages/features__history-copying.md, pages/instructions__how-to-copy-old-messages-from-any-telegram-channel-or-group.md
- Tag: [doc]

### JB-HIST-02 — Interval type (Тип интервала)
- Description: Which messages to copy.
- Where in UI: Main settings of history copy (wizard step 2).
- Parameters / options: `All messages (Все сообщения)`; `Message numbers (Номера сообщений)` — from/to Telegram message IDs taken from message links (`https://t.me/c/2301153917/38` → 38; via "Copy message link"); IDs ≠ ordinal positions; `Publication time (Время публикации)` — time range (input format only in screenshots).
- Limits: —
- Relations: HIST-10 (single-message retry uses ID range).
- Sources: pages/documentation__copying-old-messages.md, pages/instructions__how-to-copy-old-messages-from-any-telegram-channel-or-group.md
- Tag: [doc]

### JB-HIST-03 — History delivery mode & sender (Режим доставки / Отправитель)
- Description: Publishing method for copied history; choose whether messages come from the bot or the account.
- Where in UI: Main settings of history copy.
- Parameters / options: copy via bot (bot + your account admins in destination); copy or forward via connected account (posting rights suffice); "Copy via account, on flood — via bot" (Expert) — switches to bot on flood, recommended for large volumes.
- Limits: see PUB-01.
- Relations: PUB-01, HIST-04.
- Sources: pages/documentation__copying-old-messages.md, pages/instructions__how-to-copy-old-messages-from-any-telegram-channel-or-group.md
- Tag: [doc]

### JB-HIST-04 — Remove safe pause (Убрать безопасную паузу)
- Description: Disables the built-in throttle so copying runs much faster than Telegram allows.
- Where in UI: history copy Main settings checkbox.
- Parameters / options: on/off (default off [inferred]).
- Limits: risk of temporary posting ban; recommended only for a few messages or with "Copy via account, on flood — via bot".
- Relations: HIST-03, PUB-10/11.
- Sources: pages/instructions__how-to-copy-old-messages-from-any-telegram-channel-or-group.md
- Tag: [doc]

### JB-HIST-05 — Error handling (Обработка ошибок)
- Description: Policy when a message fails during history copy.
- Where in UI: history copy Main settings.
- Parameters / options: `Ask (Спросить)` — bot asks what to do; `Skip message (Пропустить сообщение)`; `Wait and retry (Подождать и повторить попытку)` — wait until the message copies without error.
- Limits: default not stated.
- Relations: HIST-10.
- Sources: pages/instructions__how-to-copy-old-messages-from-any-telegram-channel-or-group.md
- Tag: [doc]

### JB-HIST-06 — Start & progress
- Description: Press "Let's go (Поехали)" (or "Start copying (Начать копирование)"); bot posts a message in the bot chat that history copying started, with the source chat ID.
- Where in UI: Main settings → Поехали.
- Parameters / options: —
- Limits: —
- Relations: HIST-01.
- Sources: pages/instructions__how-to-copy-old-messages-from-any-telegram-channel-or-group.md, pages/documentation__copying-old-messages.md
- Tag: [doc]

### JB-HIST-07 — Copy by script (Копировать по сценарию)
- Description: Replays a chat with each message posted by the same connected account that authored it in the source, preserving pauses between messages. Use case: "warming up" a group (stage a dialog among your own accounts in a script group, then replay into the target group).
- Where in UI: new forwarding: source = script group, destination = warm-up group → Main settings: Forwarding type Old messages (history), Interval type All messages, tick "Copy by script", "Start copying".
- Parameters / options: checkbox.
- Limits: several connected accounts needed; all actor accounts must be members of the destination with posting rights; authors must be connected accounts [inferred].
- Relations: ACC-04, HIST-01.
- Sources: pages/documentation__copying-old-messages.md
- Tag: [doc]

### JB-HIST-08 — History copy with forwarding settings (Скопировать старые сообщения)
- Description: Create the forwarding, configure filters/replacements/buttons/polls etc., then start history copy; all settings apply to copied messages.
- Where in UI: `Menu → My forwardings → <fwd> → Copy old messages`.
- Parameters / options: same as HIST-02…06.
- Limits: —
- Relations: FLT-*, PROC-*, AI-01.
- Sources: pages/documentation__copying-old-messages.md
- Tag: [doc]

### JB-HIST-09 — Topic-specific history
- Description: Copy existing messages only from specific group topics (via topic mapping).
- Where in UI: topic mapping + history copy.
- Parameters / options: —
- Limits: —
- Relations: TOP-01, HIST-01.
- Sources: pages/documentation__forwarding.md
- Tag: [doc]

### JB-HIST-10 — History limits & recovery
- Description: "Stuck" copy = account exceeded Telegram download/upload limits. Fixes: disable automatic media download on the account's mobile devices; pause all account activity 12 h, then copy only the problematic message (ID range at wizard step 2); Telegram Premium raises limits (no guarantee). Missing messages → `/track`.
- Where in UI: —
- Parameters / options: —
- Limits: Telegram-imposed.
- Relations: HIST-02, DIAG-01.
- Sources: pages/documentation__troubleshooting.md
- Tag: [doc]

---

## FLT — Filters

### JB-FLT-01 — Filtering overview (Фильтрация)
- Description: Rules deciding which messages are published. Apply per forwarding (a folder forwarding → to all its sources). Any number, combinable. New forwardings start with an empty filter list. Categories: text, regex, word forms, date/time, author, media type (tokens), forwarded, own messages, duplicates, every n-th, delayed/engagement, AI (via marker). Matrix also lists "topics" and an "interval filter (for messages following the last published one)" [doc-matrix, undocumented].
- Where in UI: `Menu → My forwardings → <fwd> → Filtering → Keywords and stop words` (aka "Filters"); type selector at bottom: By text match (По текстовому совпадению) / By regular expression (По регулярному выражению) / By word forms (По словоформам) / By date/time (По дате/времени) / By author (По автору); "+"; "Value (Значение)"; left checkbox = allowing vs blocking; mode labels "Pass matching messages (Пропускать подходящие сообщения)" / "Stop matching messages (Останавливать подходящие сообщения)".
- Parameters / options: see FLT-02…19.
- Limits: messages outside the filters are dropped (not queued).
- Relations: FLT-09 (order), DIAG-01/03 (debugging), MOD-01 (manual filtering).
- Sources: pages/documentation__filters.md, pages/features__content-filtering.md, pages/instructions__how-to-filter-any-media.md, pages/documentation__message-processing.md
- Tag: [doc]

### JB-FLT-02 — Allowing / blocking filters (mustHave / mustNotHave)
- Description: Allowing (mustHave, green icon, checkbox ticked) passes only matching messages; blocking (mustNotHave, red icon, unticked) stops matching ones. Within one filter type: mustHave filters OR'ed (pass if ≥1 matches; if none match → stopped); mustNotHave OR'ed (stopped if ≥1 matches). Message passes a type if it matches ≥1 allowing and no blocking filter of that type. Across types: AND — each type evaluated separately in sequence (text first, then regex, etc.); if any type stops the message it's stopped regardless of others.
- Where in UI: checkbox in filter editor; commands use literal `mustHave`/`mustNotHave`.
- Parameters / options: mustHave | mustNotHave.
- Limits: full order of type evaluation only partially stated.
- Relations: all FLT, DIAG-02.
- Sources: pages/documentation__filters.md, pages/instructions__how-to-filter-any-media.md
- Tag: [doc]

### JB-FLT-03 — Text-match filter (Фильтр по текстовому совпадению)
- Description: Fires if message text contains the exact criterion string.
- Where in UI: Filtering → Keywords and stop words → "By text match" → "+" → Value.
- Parameters / options: value string; allowing/blocking.
- Limits: case-sensitive ("Bitcoin" ≠ "bitcoin"); multi-word value must occur contiguously with same separators. Used also for media tokens (FLT-12) and AI markers (FLT-16), author names (FLT-10).
- Relations: FLT-02, FLT-04, CMD-06/07.
- Sources: pages/documentation__filters.md
- Tag: [doc]

### JB-FLT-04 — Regex filter (Фильтр по регулярному выражению)
- Description: Java-8 regex matched against the whole message text (HTML source incl. media tokens).
- Where in UI: Filtering → Keywords and stop words → "By regular expression".
- Parameters / options: regex; allowing/blocking. Documented examples: `.*word.*<photo>.*` (word in image caption); `.*bitcoin.*ethereum.*` (order); `.*(?=.*\blitecoin\b)(?=.*\bethereum\b).*` (any order); `(?i:.*BitCoin.*liTeCoin.*)` (ignore case); `.*bitcoin.*|.*litecoin.*|.*ethereum.*` (any word); `(?i:.*BitCoin.*|.*liTeCoin.*|.*EthereUm.*)`; `.*([а-яА-Я]+).*` (Russian word); `.*(http:\/\/|https:\/\/).*` (any link); `.*([0-9]+).*` (any number); `.*@([a-zA-Z0-9=&_\-]+).*` (any @username); `[^<].*<photo>\s*` (images with captions only); `(\s*<photo>)+\s*` (images without captions incl. albums); whole-word forms `\bзаявка\b`.
- Limits: bot may append a space and/or media token at end → always end with `.*`; filters usually wrap with `.*…​.*` (remove those for replacements).
- Relations: FLT-12, PROC-06, DIAG-06, CMD-08.
- Sources: pages/documentation__filters.md, pages/documentation__troubleshooting.md
- Tag: [doc]

### JB-FLT-05 — Word-form filter (Фильтрация по всем словоформам)
- Description: Morphological match — enter a word in any form; all declensions/conjugations match (e.g. "купить" matches "купил", "куплю"; "ищу" matches "искал", "искала", "ищем").
- Where in UI: Filtering → Keywords and stop words → "By word forms".
- Parameters / options: one word; allowing/blocking.
- Limits: requires "Advanced filters" add-on or "Business" package — without it these filters are silently ignored. Case-insensitive; prefixes/prepositions not accounted ("купить" ≠ "выкупить"); a phrase → only first word used; languages RU, EN, UK, DE; unknown words (slang, names) matched exactly.
- Relations: FLT-04 (manual alternative with `\b…\b` per form), FLT-17.
- Sources: pages/documentation__filters.md
- Tag: [doc]

### JB-FLT-06 — Date/time filter (Фильтр по дате/времени публикации)
- Description: Pass/stop messages by arrival time window.
- Where in UI: Filtering → Keywords and stop words → "By date/time" → "+"; or commands CMD-09/10.
- Parameters / options: `[w<digits>] [H:MM-H:MM] [TZ]`. Weekday: `w` + day digits 1–7 (Mon=1) e.g. `w135`, `w67`. Time: 24-h inclusive range e.g. `9:30-17:30`, `0:00-23:59`. TZ: IANA name (list at junction.space/timezones.html), default UTC. Examples: blocking `0:00-7:00 Europe/Berlin`; `w12345 8:00-20:00 Europe/Moscow`.
- Limits: start must be earlier than end — no cross-midnight range in one line (use blocking day-part or two allowing filters, which OR). Out-of-window messages are dropped, not deferred (use PUB-04/05 for later publication).
- Relations: FLT-02, PUB-04, PUB-05.
- Sources: pages/documentation__filters.md
- Tag: [doc]

### JB-FLT-07 — Delayed filter (Отложенный фильтр / Фильтр по реакциям / Задержка и отложенный фильтр)
- Description: Delay publication by fixed or random time and optionally publish only if the source message reaches a minimum of ❤️ reactions, 👀 views, ✈️ forwards or 🗨️ replies. Checks at start and end of window: e.g. From 3 h To 6 h, source at 14:00 → check 17:00 (publish if met), else check 20:00 (publish if met, else drop). Option "Repeat the check hourly throughout the period (Повторять проверку раз в час в течение всего периода)" adds hourly checks (18:00, 19:00). Ranges <1 h set in minutes/seconds → only 2 checks.
- Where in UI: `… → Filtering → Reactions filter`; same in `Scheduling and publishing → Delay`; instruction label "Delay and delayed filter".
- Parameters / options: From (От), To (До); condition type Min. reactions (Мин. реакций) / Min. views / Min. forwards / Min. replies and value; hourly re-check checkbox; Save.
- Limits: "Advanced filters" add-on (any package) or "Business"; matrix: Direct/Expert + add-on. Combination of multiple conditions (AND/OR) not stated.
- Relations: PUB-04 (same delay), FLT-08.
- Sources: pages/documentation__filters.md, pages/instructions__delayed-filters.md, pages/documentation__publishing-and-moderation.md, pages/features__ai-digests.md
- Tag: [doc]

### JB-FLT-08 — Engagement-ratio thresholds
- Description: Delayed-filter conditions as ratio interactions/views.
- Where in UI: Reactions filter.
- Parameters / options: ❤️/👁 Min. reactions to views (Мин. реакций к просмотрам); ➡️/👁 Min. forwards to views (Мин. пересылок к просмотрам); 💬/👁 Min. replies to views (Мин. ответов к просмотрам). Value = decimal ratio: 1/10 → 0.1; 50/1000 → 0.05; 20/100 → 0.2.
- Limits: as FLT-07.
- Relations: FLT-07.
- Sources: pages/documentation__filters.md, pages/instructions__delayed-filters.md
- Tag: [doc]

### JB-FLT-09 — Filtering order (Порядок фильтрации)
- Description: When filters run relative to replacements and AI.
- Where in UI: `… → Filtering → Filtering order`.
- Parameters / options: `after reception` — Filters → Replacements → AI (filter original text); `after replacements` — Replacements → Filters → AI; `after ai` — Replacements → AI → Filters (AI tags, filter cuts). Default not stated (`after reception` [inferred]).
- Limits: per forwarding.
- Relations: PROC-05, AI-01, FLT-16, AI-08/09.
- Sources: pages/documentation__filters.md, pages/instructions__how-to-remove-ads-from-forwarding-ai.md, pages/instructions__how-to-find-leads-clients-and-potential-orders-ai.md
- Tag: [doc]

### JB-FLT-10 — Author filter (Фильтр по автору)
- Description: Pass/stop by numeric author ID (recommended). Anonymous messages: author = the group/channel ID without `-100` prefix. Digits only, e.g. `123456789`. By name: enable Source info → Author (PROC-13), then add a text filter with the name; to drop the name afterwards, route A→C (filtered) → B with a replacement deleting `@user (Name)` (replacements on A→C won't touch the author line since it's service text).
- Where in UI: Filtering → Keywords and stop words → "By author" → "+".
- Parameters / options: numeric ID; allowing/blocking.
- Limits: name is not a valid criterion for this type.
- Relations: PROC-13, FWD-20, PROC-05.
- Sources: pages/documentation__filters.md
- Tag: [doc]

### JB-FLT-11 — Own messages filter (Фильтр моих сообщений)
- Description: Show or hide messages sent by the connected account.
- Where in UI: `… → Filtering → Filter my messages`.
- Parameters / options: `pass` (disabled; your messages shown) / `filter`.
- Limits: Direct/Expert (docs); matrix says all tiers.
- Relations: ACC-01.
- Sources: pages/documentation__filters.md, pages/features__ai-digests.md
- Tag: [doc]

### JB-FLT-12 — Media-type filter (Фильтр по типу медиа)
- Description: Text-match filters with media tokens: `<photo>` images, `<document>` files, `<audio>` audio/music, `<video>` video, `<sticker>`, `<voice>` voice messages, `<location>` geo pins, `<animation>` GIF, `<videonote>` round video, `<poll>` polls. Allowing `<photo>` → only messages containing a photo (with or without text); blocking `<video>` → no videos.
- Where in UI: Filtering → Keywords and stop words → By text match → Value = token.
- Parameters / options: token; allowing/blocking.
- Limits: tokens also usable inside regex.
- Relations: FLT-03, FLT-04, PROC-16 (media-only/text-only recipes), DIAG-02.
- Sources: pages/documentation__filters.md, pages/instructions__how-to-filter-any-media.md, pages/instructions__media-caption.md
- Tag: [doc]

### JB-FLT-13 — Forwarded-messages filter (Фильтровать пересланные сообщения / Фильтровать пересылки)
- Description: Distinguish regular posts from posts forwarded into the source from elsewhere.
- Where in UI: `… → Filtering → Filter forwarded messages`.
- Parameters / options: `all` (default) / `direct only` — only regular messages / `forward only` — only forwarded ones.
- Limits: —
- Relations: PUB-01 ("Copy regular and forward forwards"), PROC-12 (`from_only`).
- Sources: pages/documentation__filters.md, pages/instructions__how-to-filter-forwarded-messages.md
- Tag: [doc]

### JB-FLT-14 — Every n-th message filter (Фильтр каждого n-го сообщения)
- Description: Forward only every N-th source message.
- Where in UI: command only: `/filter <source_link> every 2`.
- Parameters / options: N integer.
- Limits: —
- Relations: CMD-06.
- Sources: pages/documentation__filters.md
- Tag: [doc]

### JB-FLT-15 — Duplicate filter (Фильтр дублей / Фильтр дубликатов)
- Description: Detect identical messages.
- Where in UI: `… → Filtering → Duplicate filter`; or `/settingchannel <C> duplicate filter`.
- Parameters / options: `pass` (off) / `filter` (drop duplicates) / `only_duplicates` (publish only duplicates — e.g. two sources into intermediate channel, then publish only posts present in both).
- Limits: ignores buttons; remembers last 300 messages of the source; memory reset after 24 h without messages; compares source originals (dups created by replacements need intermediate channel); doesn't work with delivery mode `forward_client` (Forward via account). Source delete-then-edit edge case: edit of second duplicate won't pass.
- Relations: FWD-20, TOP-08, FWD-09/10, CMD-14.
- Sources: pages/documentation__filters.md, pages/documentation__troubleshooting.md
- Tag: [doc]

### JB-FLT-16 — AI filtering (Фильтрация с помощью ИИ)
- Description: Free-form criteria by meaning/sentiment (e.g. only positive news). Mechanism documented in instructions: AI prompt rewrites irrelevant messages into/with a marker word (РЕКЛАМА, ПРОПУСК, НЕ_ЛИД), a blocking text filter on the marker drops them, Filtering order = `after ai`, delivery must be a copy mode.
- Where in UI: AI text processing + Filtering + Filtering order.
- Parameters / options: prompt; marker word.
- Limits: consumes AI processings; copy mode only.
- Relations: AI-01, AI-08, AI-09, FLT-09, FLT-03.
- Sources: pages/documentation__filters.md, pages/instructions__how-to-remove-ads-from-forwarding-ai.md, pages/instructions__how-to-find-leads-clients-and-potential-orders-ai.md, pages/features__gpt-processing.md
- Tag: [doc]

### JB-FLT-17 — Bulk import of filters
- Description: Collect many filters in a table and import at once via the bulk import button.
- Where in UI: Keywords and stop words screen (button).
- Parameters / options: table format not documented.
- Limits: —
- Relations: FLT-05.
- Sources: pages/documentation__filters.md
- Tag: [doc]

### JB-FLT-18 — Copy filters between sources (Копирование фильтров)
- Description: Copy all filters from one source to another.
- Where in UI: `/filter <target_link> addAllFrom <source_link>`.
- Parameters / options: —
- Limits: —
- Relations: CMD-06, UI-10 (cloning also keeps filters).
- Sources: pages/documentation__filters.md, pages/documentation__troubleshooting.md
- Tag: [doc]

### JB-FLT-19 — Filters for all sources (Создание фильтра на все источники)
- Description: Add/remove a filter on all *current* sources at once; delete all filters everywhere. Removing one source's copy of a global filter: `/filter <src> mustHave text` (toggle).
- Where in UI: commands CMD-07, CMD-08, CMD-10.
- Parameters / options: `add|remove`, `mustHave|mustNotHave`, value; `DELETE ALL`.
- Limits: future forwardings don't inherit.
- Relations: CMD-06…10.
- Sources: pages/documentation__filters.md
- Tag: [doc]

---

## PROC — Text & message processing

### JB-PROC-01 — Copy-only prerequisite
- Description: All transformations (header/footer, trimming, replacements, AI, source info, own buttons, watermarks) work only when messages are delivered by a copy method. Native forward = no content change possible.
- Where in UI: Delivery mode (PUB-01) must be a copy mode (`copy_bot`, `copy_client`, …).
- Parameters / options: —
- Limits: —
- Relations: FWD-07, PUB-01, AI-01.
- Sources: pages/documentation__message-processing.md, pages/documentation__integrations-and-settings.md, pages/documentation__publishing-and-moderation.md
- Tag: [doc]

### JB-PROC-02 — Add header (Добавлять заголовок)
- Description: Prepend custom text (HTML allowed) before the message text. Original text continues on the same line unless you end your header with a line break. Also used to tag messages with keys (e.g. `ИСТОЧНИК1`) for routing, or insert premium emoji codes.
- Where in UI: `… → Text processing → Add header`.
- Parameters / options: free text / HTML.
- Limits: —
- Relations: PROC-03, PROC-08, PROC-19, PROC-12 (different from "Source name" header).
- Sources: pages/documentation__message-processing.md, pages/features__text-modification.md
- Tag: [doc]

### JB-PROC-03 — Add text after message / footer (Добавлять текст после сообщения)
- Description: Append text/HTML (signature) after the message, e.g. `All questions to support@mail.com`, `<a href="https://junctionbot.io/">My website</a>`, `<br>Trade at your own risk!`. Starts on the same line unless it begins with a line break.
- Where in UI: `… → Text processing → Add text after message`.
- Parameters / options: free text / HTML.
- Limits: —
- Relations: PROC-02.
- Sources: pages/documentation__message-processing.md
- Tag: [doc]

### JB-PROC-04 — Text trimming (Обрезка текста)
- Description: Shorten long messages to N characters.
- Where in UI: `… → Text processing → Text trimming`.
- Parameters / options: integer length; 0 = disabled; recommended 150 (tweet-like) – 1000 (several paragraphs).
- Limits: —
- Relations: FWD-17.
- Sources: pages/documentation__message-processing.md
- Tag: [doc]

### JB-PROC-05 — Replacements (Замена ссылок и слов в тексте / Замены)
- Description: Rules replacing text A with B (empty B = delete). Apply to message body and buttons (incl. notification-button pop-up text) only — not to source-name header, author line or link-to-original. Rules apply strictly top-to-bottom, each on already-modified text; new rules always appended at the end (no drag-reorder) → create long rules before short ones (delete & recreate to move). Automatic cross-link replacement (PROC-10) runs after all rules. Rules see the message HTML source.
- Where in UI: `… → Text processing → Replace links and words in text → "➕ Create new replacement (Создать новую замену)"`; fields Source (Источник), New value (Новое значение), RE checkbox, Edit icon.
- Parameters / options: source, new value, RE flag.
- Limits: text and buttons only — media replacement via moderation (matrix claims "text and images"). Case sensitivity of plain rules not stated (exact match [inferred]).
- Relations: PROC-06/07/09, FLT-09, FLT-15 (dups from replacements), DIAG-04, CMD-11/12.
- Sources: pages/documentation__message-processing.md, pages/instructions__how-to-replace-a-word-or-part-of-text-when-copying-messages.md, pages/documentation__filters.md
- Tag: [doc]

### JB-PROC-06 — Regex replacements (RE)
- Description: Tick RE to treat Source as Java-8 regex; New value supports numbered backreferences `$1`. Documented recipes: `<a[^<]+</a>` → '' (all HTML links); `(http:\/\/|https:\/\/)([a-zA-Z0-9.\/\?=&_]+)` → '' (plain links); `(http:\/\/|https:\/\/)(t.me)([a-zA-Z0-9.\/\?=&_]+)` → '' (t.me links); `@([a-zA-Z0-9=&_\-]+)` → '' (@usernames); `Postscriptum.*` → '' (tail from word); `кусок текста` → `<a href="https://junctionbot.io/">кусок текста</a>`; `№([0-9]+)` → ''; `.*` → '' (strip all text → only captioned pictures survive, text-only messages not forwarded); `.*\bkeyword\b.*` → '' (lines with word); `<br><br>` → `<br>` (empty lines); `keyword` → `<b>keyword</b>`; `([0-9]+)` → `<b>$1</b>`; `(.*)` → `<b>$1</b>` (whole message bold); `(?s).*(Token: 0x[a-zA-Z0-9]+).*` → `$1` (keep one line); multi-step trading-signal reformat (`Buy ` → `BUY<br>#`, `Stop-Loss at` → `SL:`, `(\d+)\nTake-Profit 1.*\n` → `$1 points<br>`, `Take-Profit 2.*\nTake-Profit 3 at (\d+)` → `TP: $1 points`).
- Where in UI: Replacements screen, RE checkbox.
- Parameters / options: —
- Limits: remove the `.*` wrappers typical for filters. Empty result message is dropped [inferred from recipe 11].
- Relations: PROC-05, DIAG-06, CMD-12.
- Sources: pages/documentation__message-processing.md
- Tag: [doc]

### JB-PROC-07 — Formatting via HTML (Добавление/Удаление форматирования)
- Description: Add formatting by replacing text with tagged text (`<b>…</b>`, Telegram Bot API HTML tags); remove formatting by replacing tagged source with plain text (inspect source code first). `<br>` = line break.
- Where in UI: Replacements; or `/replace <src> <b>needed&nbsp;piece</b> needed&nbsp;piece`.
- Parameters / options: —
- Limits: Telegram-supported tags only.
- Relations: PROC-05, DIAG-04, CMD-11.
- Sources: pages/documentation__message-processing.md
- Tag: [doc]

### JB-PROC-08 — Premium emoji codes (Замена премиум emoji)
- Description: Premium emoji appear in source as `<strong documentid="123456789">(emoji)</strong>`; use the code in replacements or header/footer to replace/insert premium emoji. Find code via Processing report, /track or @junction_helper0_bot.
- Where in UI: Replacements / Add header / Add text after message.
- Parameters / options: —
- Limits: publishing needs account delivery + Premium (FWD-18).
- Relations: FWD-18, DIAG-03/04.
- Sources: pages/documentation__message-processing.md
- Tag: [doc]

### JB-PROC-09 — Link replacement recipes (Замена ссылок в тексте)
- Description: First check link type in source code. (1) HTML `<a href=…>text</a>` — replace whole construction (exact or `<a[^<]+</a>` RE). (2) Plain URL — replace URL text (exact or `https:\/\/\S+` RE). (3) `@username` — `@([a-zA-Z0-9=&_\-]+)` RE. Bot-added link to source removed via PROC-11 = none; bot header via PROC-12 = none.
- Where in UI: Replacements.
- Parameters / options: —
- Limits: —
- Relations: PROC-05/06/10/11.
- Sources: pages/documentation__message-processing.md
- Tag: [doc]

### JB-PROC-10 — Replace cross-links with source (Заменять кросс-ссылки на источник / Заменять ссылки на источник)
- Description: Smart automatic replacement of all links/mentions of the source channel (plain links to the channel and links to other messages in it) without manual rules (presumably to the destination equivalents [inferred]). Runs after manual replacements. Offered in wizard Main settings ("automatic link replacement") with several variants (only in screenshots).
- Where in UI: wizard Main settings; `… → Source info → Replace cross-links with source`.
- Parameters / options: several variants (undocumented).
- Limits: Expert only.
- Relations: PROC-05, UI-02.
- Sources: pages/documentation__message-processing.md, pages/instructions__how-to-forward-from-public-telegram-channel-or-group.md, pages/instructions__how-to-forward-from-private-telegram-channel-or-group.md, pages/documentation__forwarding.md
- Tag: [doc]

### JB-PROC-11 — Link to original post (Ссылка на оригинальный пост / Ссылка на оригинальное сообщение)
- Description: Append link to the source message (the `@`-style link at the bottom).
- Where in UI: `… → Source info → Link to original post`.
- Parameters / options: `none` (default) / `full` — link as is / custom value (Произвольное значение) — link hidden under this text (e.g. "не ходи сюда").
- Limits: not affected by replacements. Private sources' link behavior undocumented.
- Relations: PROC-12/13, AI-09 (lead link).
- Sources: pages/documentation__message-processing.md, pages/instructions__how-to-add-a-link-to-the-original-message-when-copying-messages.md
- Tag: [doc]

### JB-PROC-12 — Source name (Название источника)
- Description: Header with source info at message start.
- Where in UI: `… → Source info → Source name`; command `/setting header none`.
- Parameters / options: `none`; `simple` — channel name as header; `bold` — name in bold; `from_only` — not the immediate source but the original source of a forwarded post (only if forwarded); `id` — source message ID instead of name; `date` — publication date in source instead of name; custom value — replaces channel name with this text (HTML allowed; broken/unsupported tags → messages stop arriving or arrive unformatted). Default `none` per instruction ("Source name: none").
- Limits: service text — replacements don't touch it.
- Relations: PROC-05, PROC-13, FLT-13.
- Sources: pages/documentation__message-processing.md, pages/instructions__how-to-specify-the-name-of-the-source-chat-when-copying-messages.md
- Tag: [doc]

### JB-PROC-13 — Author (Автор)
- Description: Show message author (for messages that have an author), hyperlinked to profile, at message start.
- Where in UI: `… → Source info → Author`; `/setting author <mode>`.
- Parameters / options: `none`; `name`; `username` (@username); `full` (name + @username); `full_except_bot` (full for everyone except Junction Bot).
- Limits: full name may be unavailable (Telegram profile-fetch rate limits, privacy) → shown as `User#123456`. Alternative to keep author: "Forward via account". Service text — replacements don't touch it.
- Relations: FLT-10, PUB-01, AI-09.
- Sources: pages/documentation__message-processing.md, pages/instructions__how-to-specify-the-author-when-copying-messages.md
- Tag: [doc]

### JB-PROC-14 — Own URL buttons (Добавить свои кнопки)
- Description: Add your own URL buttons; one per line: `<url> <label>` (e.g. `https://junction.space About the project`).
- Where in UI: `… → Buttons → Add your own buttons`; `/setting mybuttons` + lines.
- Parameters / options: `none` / custom value.
- Limits: native buttons only in "Copy via bot" (`copy_bot`); account copy modes — only with Premium (rich message, link buttons inside); "Forward via account" — not added.
- Relations: PUB-01, FWD-12, FWD-20 (buttons on subset).
- Sources: pages/documentation__message-processing.md
- Tag: [doc]

### JB-PROC-15 — Feedback buttons (Кнопки обратной связи)
- Description: Reaction-style buttons ("likes").
- Where in UI: `… → Buttons → Feedback buttons`; `/setting like Да Нет Возможно`.
- Parameters / options: `none`; `1` — 👍; `2` — 👍 👎; custom string — each word a button (`👍 👎` = 2; `Yes No Maybe`).
- Limits: `copy_bot` only (never in account modes, even with Premium).
- Relations: PUB-01.
- Sources: pages/documentation__message-processing.md
- Tag: [doc]

### JB-PROC-16 — Media caption (Подпись к медиа)
- Description: How captions of media are transferred.
- Where in UI: `… → Images and video (or "Content") → Media caption`.
- Parameters / options: `separate` — media and caption as 2 messages (full long captions via bot); `caption_name` — 1 message, caption includes channel name + link to original (truncated if too long); `text_only` — caption only, media dropped. Recipe "media only": `separate` + allowing filters `<photo>`, `<video>`. Fix for "messages arrive without pictures": set `caption_name`.
- Limits: does not block messages, only splits components.
- Relations: FLT-12, FWD-17, DIAG-09.
- Sources: pages/documentation__forwarding.md, pages/instructions__media-caption.md, pages/documentation__troubleshooting.md
- Tag: [doc]

### JB-PROC-17 — Watermarks — apply (Водяные знаки)
- Description: Overlay a previously uploaded watermark on forwarded media.
- Where in UI: `… → Images and video → Watermarks`.
- Parameters / options: choose watermark from list; checkboxes Apply to image (Накладывать на изображение), Apply to video (Накладывать на видео), Apply to animation (Накладывать на анимацию).
- Limits: plan-dependent (matrix: Direct/Expert). Copy mode.
- Relations: PROC-18, PROC-01.
- Sources: pages/documentation__message-processing.md, pages/features__watermark-overlay.md
- Tag: [doc]

### JB-PROC-18 — Watermark library (Мои водяные знаки)
- Description: Create reusable watermark presets.
- Where in UI: My watermarks → Create new watermark (Создать новый знак).
- Parameters / options: Name; Watermark file (PNG only); Opacity level (higher = more transparent; scale not stated); Scaling (Масштабирование): Fit (proportional) (Вместить), Cover (proportional) (Покрыть), Do not scale (Не масштабировать); Alignment (Выравнивание): center, a side, a corner, or Random (Случайное).
- Limits: text watermarks not supported (image only) [inferred].
- Relations: PROC-17.
- Sources: pages/documentation__message-processing.md, pages/features__watermark-overlay.md
- Tag: [doc]

### JB-PROC-19 — Third-party bot processing (Использование других Telegram ботов)
- Description: Embed an external bot: source → bot, bot → destination. Multiple sources through one bot: tag each with header key (`ИСТОЧНИК1`), bot → intermediate channel with allowing text filter on key, intermediate → destination with replacement removing key.
- Where in UI: ordinary forwardings.
- Parameters / options: —
- Limits: forwarding to/from bots needs connected account.
- Relations: FWD-05, FWD-20, PROC-02, FLT-03.
- Sources: pages/documentation__message-processing.md
- Tag: [doc]

### JB-PROC-20 — Manual editing & media replacement
- Description: Replacing pictures, adding media to text, or manual editing is done in moderation mode (edit the post before Publish).
- Where in UI: MOD-01.
- Parameters / options: —
- Limits: —
- Relations: MOD-01, MOD-03.
- Sources: pages/documentation__message-processing.md
- Tag: [doc]

---

## AI — AI processing

### JB-AI-01 — AI text processing (ИИ обработка текста / ИИ обработка (ChatGPT и другие))
- Description: Describe in plain language what to do with message text; bot sends text + prompt to the LLM and publishes the result. Uses: translation, summarization, smart filtering, changing numbers, rewriting style/length.
- Where in UI: `… → Text processing → AI text processing`.
- Parameters / options: one active prompt per forwarding.
- Limits: text only (no images); copy mode only; consumes AI quota/usage per message. Behavior when quota exhausted undocumented.
- Relations: AI-02…10, FLT-09, FLT-16, PROC-01.
- Sources: pages/documentation__integrations-and-settings.md, pages/instructions__how-to-setup-an-ai-integration.md, pages/documentation__message-processing.md, pages/features__gpt-processing.md
- Tag: [doc]

### JB-AI-02 — Prompt blocks (Активный промпт / Мои промпты / Библиотека промптов)
- Description: Screen has: Active prompt (hidden if none), My prompts (created/modified by you), Prompt library (ready templates, e.g. "Ad check", "Potential client detection").
- Where in UI: AI text processing screen.
- Parameters / options: —
- Limits: —
- Relations: AI-03, AI-04.
- Sources: pages/documentation__integrations-and-settings.md, pages/instructions__how-to-setup-an-ai-integration.md
- Tag: [doc]

### JB-AI-03 — Prompt actions & sharing
- Description: Tap prompt → Apply (Применить) → moves to Active. ⋮ menu: Edit (Редактировать), Copy (Скопировать), Stop (Остановить; deactivates, returns to list). Editing a library prompt and saving always creates a copy in My prompts. One prompt can be used by several forwardings; editing it changes all of them.
- Where in UI: AI text processing screen.
- Parameters / options: —
- Limits: —
- Relations: AI-02.
- Sources: pages/documentation__integrations-and-settings.md, pages/instructions__how-to-setup-an-ai-integration.md
- Tag: [doc]

### JB-AI-04 — Custom prompt (+ Создать промпт)
- Description: Create own prompt.
- Where in UI: My prompts → + Create prompt.
- Parameters / options: Name (Название), Description (Описание), Prompt text (Текст промпта), Creativity (Креативность, = temperature; recommended 0.7; higher = more artistic), model (in paid/own-key modes). Buttons: Save and apply (Сохранить и применить) / Save (Сохранить).
- Limits: —
- Relations: AI-06.
- Sources: pages/documentation__integrations-and-settings.md, pages/instructions__how-to-setup-an-ai-integration.md
- Tag: [doc]

### JB-AI-05 — AI usage mode (global)
- Description: Single global choice for all forwardings, digests and AI services: (1) Free mode (Бесплатный режим) — quota, one default model; (2) Pay from balance (Оплата с баланса) — platform-billed, 300+ models via OpenRouter with automatic provider selection by cost/speed (billing details excluded); (3) Use your own API key (Использовать свой API ключ) — OpenAI (OpenAI models only) or OpenRouter (300+ models incl. free ones); Junction Bot doesn't charge.
- Where in UI: mode selector at top of AI settings / digests screen.
- Parameters / options: mode; API key.
- Limits: invalid key → digests "Suspended: API key unavailable".
- Relations: AI-06, AI-07, DIG-16, DIG-14.
- Sources: pages/documentation__integrations-and-settings.md, pages/instructions__how-to-setup-an-ai-integration.md, pages/documentation__digests.md
- Tag: [doc]

### JB-AI-06 — Models
- Description: Free mode: 1 locked default model (digests doc: currently Google Gemini 3 Flash Preview). Paid/own-key: choose among 300+ models (OpenRouter) or OpenAI models.
- Where in UI: prompt editor "Model (Модель)".
- Parameters / options: model id.
- Limits: —
- Relations: AI-04, DIG-06.
- Sources: pages/documentation__digests.md, pages/instructions__how-to-setup-an-ai-integration.md
- Tag: [doc]

### JB-AI-07 — Free AI quota
- Description: Free processings for message AI: 10 per 30 days (renews monthly), increased by active plans (plan-dependent). Digests: free generations per month (30 on free tier; plan-dependent).
- Where in UI: —
- Parameters / options: —
- Limits: see Contradictions (10 vs 30; possibly separate counters).
- Relations: AI-05, DIG-16.
- Sources: pages/documentation__integrations-and-settings.md, pages/instructions__how-to-setup-an-ai-integration.md, pages/instructions__how-to-set-up-a-digest.md
- Tag: [doc]

### JB-AI-08 — Preset "Ad check" (Проверка на рекламу)
- Description: Library prompt that marks ad posts with the marker word РЕКЛАМА (filters doc example edits it to output ПРОПУСК for irrelevant posts). Recipe: apply prompt → blocking text filter on marker → Filtering order `after ai` → delivery `copy_client` or `copy_bot`.
- Where in UI: AI processing → Prompt library.
- Parameters / options: editable.
- Limits: prompt text only in screenshots.
- Relations: FLT-16, FLT-09, FLT-03.
- Sources: pages/instructions__how-to-remove-ads-from-forwarding-ai.md, pages/documentation__filters.md
- Tag: [doc]

### JB-AI-09 — Preset "Potential client detection" (Определение потенциального клиента)
- Description: Lead-detection prompt; writes НЕ_ЛИД into non-lead messages. Same recipe as AI-08 with blocking filter `НЕ_ЛИД`, `after ai`, copy mode. Optional: Link to original = full, Author = username/full so the lead is clickable.
- Where in UI: AI processing → Prompt library → Edit (adapt to business) → Apply.
- Parameters / options: editable.
- Limits: —
- Relations: FLT-16, PROC-11, PROC-13.
- Sources: pages/instructions__how-to-find-leads-clients-and-potential-orders-ai.md
- Tag: [doc]

### JB-AI-10 — AI use cases (marketing)
- Description: Translation, summary, smart filter (meaning/tone/key phrases), content generation (headlines/descriptions), sentiment analysis, moderation (prohibited topics, insults, spam), auto-responder (replies to chat questions — mechanism undocumented).
- Where in UI: via AI-01 prompts.
- Parameters / options: —
- Limits: —
- Relations: AI-01, FLT-16.
- Sources: pages/features__gpt-processing.md
- Tag: [doc] (marketing; auto-responder unverified)

---

## PUB — Publishing & delivery

### JB-PUB-01 — Delivery mode (Режим доставки)
- Description: Who publishes and how.
- Where in UI: wizard Main settings; `… → Delivery mode`.
- Parameters / options:
  - **Copy via bot (Копировать через бота, `copy_bot`)** — bot publishes copies; bot AND your account must be admins, bot with posting rights. Only mode for native own/feedback buttons.
  - **Copy via account (Копировать через аккаунт, `copy_client`)** — connected account publishes copies; needs posting rights only.
  - **Copy via account, on flood — via bot (… при флуде - через бота)** — account, falls back to bot on Telegram rate limit (bot must be admin); 40–60 msgs/min; top tier (Expert).
  - **Forward via account (Пересылать через аккаунт, `forward_client`)** — native forward via account, keeps link to original; source must allow forwarding; no modification; incompatible with duplicate filter.
  - **Copy regular and forward forwards via account (Копировать обычные и пересылать форварды через аккаунт; "copy or forward client")** — regular posts copied, posts forwarded into source appear as "Forwarded from …"; if source forbids forwarding, those are skipped.
  - **Forward via account, on protection — copy (Пересылать через аккаунт, при защите - копировать)** — forward; if source forbids forwarding, copy as account.
- Limits: account modes Direct/Expert; DMs/bots destinations always via account. Moderation forces Copy via account. Account modes: no native buttons (Premium → rich text link buttons in copy; none in forward).
- Relations: FWD-07, PROC-01, PROC-14/15, FWD-12/17/18, PUB-02, PUB-05/06, MOD-04, HIST-03, FLT-15.
- Sources: pages/documentation__publishing-and-moderation.md, pages/documentation__message-processing.md, pages/documentation__filters.md, pages/instructions__how-to-remove-ads-from-forwarding-ai.md
- Tag: [doc] (internal ids `copy_bot`, `copy_client`, `forward_client` [doc]; mapping of `forward_client` to "Forward via account" [inferred])

### JB-PUB-02 — Publish as bot vs account
- Description: As bot — posts show @junction_bot. As account — posts show your connected account's name/avatar (bot invisible in groups); no need to keep the bot in destination.
- Where in UI: Delivery mode; digests "Publish as (Публиковать от имени)".
- Parameters / options: —
- Limits: admin requirements as in PUB-01; views of copies counted separately.
- Relations: PUB-01, PUB-03, DIG-12.
- Sources: pages/documentation__publishing-and-moderation.md, pages/documentation__forwarding.md, pages/documentation__getting-started.md
- Tag: [doc]

### JB-PUB-03 — Anonymous group posting (Анонимность)
- Description: If the connected account is an admin with Anonymity on, account-mode posts appear on behalf of the group. Used for "messages come from the bot but I want from the group" and for comments as group.
- Where in UI: Telegram: `Group settings - Administrators - <account> - Anonymity: On`.
- Parameters / options: —
- Limits: groups only.
- Relations: PUB-01, FWD-16.
- Sources: pages/documentation__publishing-and-moderation.md, pages/documentation__troubleshooting.md
- Tag: [doc]

### JB-PUB-04 — Publication delay — bot queue (Задержать / Публикация с задержкой (Очередь бота))
- Description: Publish after an extra delay from source publication. Queued messages cannot be viewed, edited or cancelled.
- Where in UI: `… → Scheduling and publishing → Delay` (also `Filtering → Reactions filter`).
- Parameters / options: From (От) only = fixed delay; From + To (До) = random delay in range.
- Limits: units/max not stated (hours/minutes/seconds used in examples). Edits before publication not applied.
- Relations: FLT-07, FWD-09, PUB-05.
- Sources: pages/documentation__publishing-and-moderation.md, pages/documentation__filters.md
- Tag: [doc]

### JB-PUB-05 — Schedule — Telegram scheduler (Запланировать ("отложка") / Планирование (Планировщик Telegram))
- Description: Bot adds the message to Telegram's native scheduled messages ("Send later") on your behalf; you can view (calendar icon in destination), edit text/media/time, delete before publication.
- Where in UI: `… → Scheduling and publishing → Schedule ("deferred")`.
- Parameters / options: From = fixed offset ahead; From + To = random offset.
- Limits: requires account delivery mode (copy or forward).
- Relations: PUB-01, PUB-04, PUB-06.
- Sources: pages/documentation__publishing-and-moderation.md
- Tag: [doc]

### JB-PUB-06 — Delivery frequency (Частота доставки)
- Description: Minimum period between deliveries from a source. Example 60 s: 3 posts at 16:30 → 16:30, 16:31, 16:32; a 4th at 16:31 → 16:33.
- Where in UI: `… → Scheduling and publishing → Delivery frequency`.
- Parameters / options: period (seconds); 0 resets timer.
- Limits: counted per source (not per destination → use intermediate channel); works via Telegram scheduler → needs account delivery mode.
- Relations: PUB-05, FWD-20, PUB-11.
- Sources: pages/documentation__publishing-and-moderation.md
- Tag: [doc]

### JB-PUB-07 — Pin posts (Закреплять посты)
- Where in UI: `… → Scheduling and publishing → Pin posts`.
- Description: Pin delivered posts in destination.
- Parameters / options: `off`; `pass` — pin if original pinned; `silent` — pin all without notification; `notify` — pin all with notification (groups only, not channels).
- Limits: matrix: Direct/Expert.
- Relations: PUB-08.
- Sources: pages/documentation__publishing-and-moderation.md, pages/features__ai-digests.md
- Tag: [doc]

### JB-PUB-08 — Silent mode (Тихий режим)
- Description: Deliver without notification sound.
- Where in UI: `… → Scheduling and publishing → Silent mode`.
- Parameters / options: `pass` (keep source's silent flag) / `never` / `always`.
- Limits: —
- Relations: PUB-07.
- Sources: pages/documentation__publishing-and-moderation.md
- Tag: [doc]

### JB-PUB-09 — Link preview (Предпросмотр ссылок)
- Description: Web page preview under message text.
- Where in UI: `… → Other content → Link preview`.
- Parameters / options: `pass` (as in source) / `never` / `always` (if there is a link).
- Limits: —
- Relations: DIG-08 (`external_link_description`).
- Sources: pages/documentation__publishing-and-moderation.md
- Tag: [doc]

### JB-PUB-10 — Flood reaction (Реакция на флуд)
- Description: Behavior when Telegram temporarily blocks posting into destination (~20–30 msgs/min).
- Where in UI: `… → Debug settings → Flood reaction`.
- Parameters / options: Ignore message (Игнорировать сообщение); Stop forwarding completely (Полностью остановить пересылку) — paused until re-enabled; Postpone and deliver when possible (Отложить и доставить, когда получится) — **default**, may snowball and eventually drop under huge flow; Notify on flood ban (Уведомлять при флуд запрете) — notification in bot chat.
- Limits: no known bans for flood; only temporary posting block.
- Relations: PUB-11, DIAG-08.
- Sources: pages/documentation__publishing-and-moderation.md, pages/documentation__troubleshooting.md
- Tag: [doc]; whether Notify is combinable with others [inferred: separate toggle] unknown.

### JB-PUB-11 — Flood mitigation
- Description: Use account delivery (softer limits); "Copy via account, on flood — via bot" (40–60 msgs/min); delivery frequency; split traffic across connected accounts; split destination into several channels; for history, keep safe pause.
- Where in UI: —
- Parameters / options: —
- Limits: —
- Relations: PUB-01, PUB-06, ACC-04, HIST-04.
- Sources: pages/documentation__publishing-and-moderation.md, pages/documentation__troubleshooting.md
- Tag: [doc]

### JB-PUB-12 — Delayed deletion
- Description: "Delete after preset time" listed in the plan matrix (all tiers). No docs page describes it.
- Where in UI: unknown.
- Parameters / options: unknown.
- Limits: —
- Relations: FWD-10.
- Sources: pages/features__ai-digests.md
- Tag: [doc-matrix]

---

## MOD — Moderation

### JB-MOD-01 — Moderation mode (Режим модерации / режим одобрения / Модерировать сообщения)
- Description: Pre-moderation: for each new source post, the connected account sends a copy to @Junction_Review_Bot (chat appears as "Reviews" after first message) with source/destination info and buttons Publish (Опубликовать) / Skip (Пропустить).
- Where in UI: `… → Moderation → Moderation → "Moderate messages" → ON` (same place to disable).
- Parameters / options: on/off; target: @Junction_Review_Bot (default) or own chat (MOD-02).
- Limits: plan-dependent (docs) / all tiers (matrix); needs connected account [inferred from mechanism].
- Relations: MOD-02…05, PROC-20, FLT-01.
- Sources: pages/documentation__publishing-and-moderation.md, pages/instructions__how-to-set-up-manual-moderation-via-junction-review-bot.md, pages/features__manual-moderation.md
- Tag: [doc]

### JB-MOD-02 — Moderation in own chat/group (Выбрать чат)
- Description: Send posts for approval to a chosen group (or channel per instruction) or create a new one; "Send to @Junction_Review_Bot (Слать в @Junction_Review_Bot)" returns to default.
- Where in UI: Moderation → Moderate messages ON → Select chat → Save.
- Parameters / options: chat.
- Limits: @Junction_Review_Bot and the connected account must be admins there, else error `NO_ACCESS` (instruction also says "the bot must be admin").
- Relations: MOD-01.
- Sources: pages/documentation__publishing-and-moderation.md, pages/instructions__how-to-set-up-manual-moderation-via-own-chat.md
- Tag: [doc]

### JB-MOD-03 — Publish / Skip / edit
- Description: Since the review copy is posted by your account, you can edit it in the review chat; Publish posts the current version; Publish can be pressed repeatedly (each publishes current version again). Skip discards.
- Where in UI: review chat buttons.
- Parameters / options: —
- Limits: timeouts for unreviewed posts not documented.
- Relations: PROC-20.
- Sources: pages/documentation__publishing-and-moderation.md, pages/instructions__how-to-set-up-manual-moderation-via-own-chat.md
- Tag: [doc]

### JB-MOD-04 — Moderation side effects
- Description: Filters and replacements apply before the post goes to review. Enabling moderation auto-switches to account copy delivery → account needs posting rights in destination; original buttons not passed; source edits not propagated.
- Where in UI: —
- Parameters / options: —
- Limits: —
- Relations: PUB-01, FWD-09, FWD-12.
- Sources: pages/documentation__publishing-and-moderation.md
- Tag: [doc]

### JB-MOD-05 — Moderation extras (marketing claims)
- Description: Edit text and media, schedule release time of approved posts, team collaboration on selection/approval (via shared review group [inferred]).
- Where in UI: —
- Parameters / options: —
- Limits: not described in docs.
- Relations: MOD-02, PUB-05.
- Sources: pages/features__manual-moderation.md
- Tag: [doc] (marketing)

---

## DIG — Digests

### JB-DIG-01 — Digests (Дайджесты)
- Description: Separate entity from forwardings: an AI analyst collects messages from selected channels/groups, summarizes/extracts per a template (prompt), and publishes structured material to the bot chat or a channel/group, on schedule or on demand.
- Where in UI: `Menu → My digests (Мои дайджесты)` (side menu) → Create digest (Создать дайджест).
- Parameters / options: sources, digest type (template), publication time, publication place.
- Limits: DIG-16.
- Relations: DIG-02…16, AI-05, PROJ-03.
- Sources: pages/documentation__digests.md, pages/features__ai-digests.md, pages/instructions__how-to-set-up-a-digest.md
- Tag: [doc]

### JB-DIG-02 — Quick digest ("Digest in 3 clicks")
- Description: Create digest → paste link(s) to public sources → Add (Добавить) → Sources screen Continue (Продолжить) → auto-filled: digest type = best library template by source types; time = On schedule daily at ≈creation time; place = Publish to Junction Bot chat → Save digest (Сохранить дайджест).
- Where in UI: My digests.
- Parameters / options: —
- Limits: —
- Relations: DIG-05, DIG-11, DIG-12.
- Sources: pages/documentation__digests.md, pages/instructions__how-to-set-up-a-digest.md
- Tag: [doc]

### JB-DIG-03 — Scheduled vs instant digest (По расписанию / Мгновенный дайджест (вручную))
- Description: Scheduled = fully automatic, limited by plan slots. Instant = manual one-off generation, unlimited count.
- Where in UI: Publication time screen.
- Parameters / options: On schedule | Instant digest (manual).
- Limits: "On schedule" inactive when slots exhausted (extra "+1 digest" add-on exists).
- Relations: DIG-04, DIG-11, DIG-16.
- Sources: pages/documentation__digests.md, pages/instructions__how-to-set-up-a-digest.md
- Tag: [doc]

### JB-DIG-04 — Generate now (Сгенерировать сейчас)
- Description: Run any digest (even scheduled) immediately.
- Where in UI: My digests → card ⋮ → Generate now.
- Parameters / options: —
- Limits: consumes a generation.
- Relations: DIG-03, DIG-15.
- Sources: pages/documentation__digests.md
- Tag: [doc]

### JB-DIG-05 — Digest templates (Шаблон / Библиотека шаблонов / Мои шаблоны)
- Description: Digest type = AI instruction set defining structure, style, content. Library: "News overview (Новостной обзор)" — default when sources mostly channels; "Group discussions (Обсуждения в группе)" — default when mostly groups (marketing names: "News digest", "Group digest"). My templates — personal; create, edit, delete. Editing a library template + Save and apply creates a copy in My templates.
- Where in UI: digest settings → Digest type → Edit / Create prompt.
- Parameters / options: —
- Limits: —
- Relations: DIG-06.
- Sources: pages/documentation__digests.md, pages/instructions__how-to-set-up-a-digest.md, pages/features__ai-digests.md
- Tag: [doc]

### JB-DIG-06 — Digest prompt editor
- Description: Fields: Prompt text (Текст промпта) — defines structure (headings, topic split, length, link style) and tone; markdown recommended; more detail = more predictable. Model (Модель) — choosable in paid modes, locked in free (default Gemini 3 Flash Preview). Temperature (Температура) — 0 to 2 step 0.1, default 0.7. Example (Пример) button — sample outputs. Preview available in place.
- Where in UI: template edit screen.
- Parameters / options: as listed + DIG-07.
- Limits: —
- Relations: AI-06, DIG-07, DIG-08, DIG-13.
- Sources: pages/documentation__digests.md
- Tag: [doc]

### JB-DIG-07 — Consider past digests (Учитывать прошлые дайджесты)
- Description: Number of previous successful generations fed to the AI to avoid repeats / continue topics. System prompts consider 1 by default. 0 = allow repeats.
- Where in UI: template edit screen.
- Parameters / options: 0–10 (paid modes), max 1 in free mode (matrix: up to 10 on top tiers, 1 otherwise).
- Limits: as stated.
- Relations: DIG-06.
- Sources: pages/documentation__digests.md, pages/features__ai-digests.md
- Tag: [doc]

### JB-DIG-08 — Prompt metadata fields
- Description: Per-message fields usable in prompt (if available): `text` (HTML), `date`, `author_id`, `original_url`, `views_count`, `comments_count`, `reactions_count`, `engagement_score` (reactions+comments relative to views; channel-relative; empty if views unknown or both reactions and comments unknown), `external_link_description` (title/description of first URL's page). AI also knows source name, topic, replied-to post, sometimes most active likers.
- Where in UI: referenced inside prompt text.
- Parameters / options: —
- Limits: —
- Relations: DIG-06, PUB-09.
- Sources: pages/documentation__digests.md
- Tag: [doc]

### JB-DIG-09 — Digest sources (Источники)
- Description: Add by pasting link or selecting from connected account's chats ("Add source (Добавить источник)"). Access: Public (link/@username) — all users; Open (invite link) — Express+; Closed/private — Direct/Expert + connected account (Connect account prompt). Membership suffices; you need not own the chat.
- Where in UI: Sources screen.
- Parameters / options: —
- Limits: count plan-dependent (free 3; matrix 3/…/1000).
- Relations: ACC-01, DIG-10, DIG-16.
- Sources: pages/documentation__digests.md, pages/instructions__how-to-set-up-a-digest.md, pages/features__ai-digests.md
- Tag: [doc]

### JB-DIG-10 — Topic selector (Темы (топики) внутри группы)
- Description: For forum groups: default "All topics (Все темы)" = 1 source/slot; uncheck to choose specific topics — each may count as a separate source.
- Where in UI: Sources screen.
- Parameters / options: All topics | individual topics.
- Limits: per-topic selection consumes source limit.
- Relations: DIG-09, TOP-01.
- Sources: pages/documentation__digests.md
- Tag: [doc]

### JB-DIG-11 — Publication time (Время публикации)
- Description: Default "At the same time (В одно и то же время)" for all 7 days; uncheck for per-day hours; "+" adds several time slots per day.
- Where in UI: Publication time screen.
- Parameters / options: days, times, slots.
- Limits: scheduled slots plan-dependent.
- Relations: DIG-03.
- Sources: pages/documentation__digests.md, pages/instructions__how-to-set-up-a-digest.md
- Tag: [doc]

### JB-DIG-12 — Publication place (Место публикации)
- Description: "Publish to Junction Bot chat (Публиковать в чат Junction Bot)" (default) or "Publish to chat (Публиковать в чат)" — external channel/group; "Publish as (Публиковать от имени)" bot or connected account. Rights check for bot mode: you and bot must be admins, else dialog "Bot must be an administrator" → "I added the bot and myself as admins (Я добавил бота и себя в админы)" re-check. Marketing: one or more target chats.
- Where in UI: Publication place screen.
- Parameters / options: target; identity.
- Limits: —
- Relations: PUB-02.
- Sources: pages/documentation__digests.md, pages/instructions__how-to-set-up-a-digest.md, pages/features__ai-digests.md
- Tag: [doc]

### JB-DIG-13 — Preview (Предпросмотр дайджеста)
- Description: Generate before scheduling: choose Period ("For a week (За неделю)", "Since last generation (С последней генерации)") → Generate (Сгенерировать). Telegram-styled window shows usage (free: generations spent; API key: input/output tokens).
- Where in UI: settings screen → Digest preview.
- Parameters / options: period.
- Limits: consumes generations.
- Relations: DIG-06.
- Sources: pages/documentation__digests.md, pages/instructions__how-to-set-up-a-digest.md
- Tag: [doc]

### JB-DIG-14 — Digest statuses
- Description: Pending (Ожидается) — waiting for next run; Generating (Генерируется); Disabled (Выключен) — manually off; Suspended (Приостановлен) — auto-stopped on critical error, ⚠️ for diagnostics. Suspended reasons: generations ran out; session broken (Reconnect); package ended ("+1 digest" slot); API key unavailable.
- Where in UI: My digests cards.
- Parameters / options: —
- Limits: —
- Relations: ACC-06, AI-05, DIG-15.
- Sources: pages/documentation__digests.md
- Tag: [doc]

### JB-DIG-15 — Digest actions
- Description: Card (...) menu: Disable/enable (Отключить), Copy with settings, Generate now, Move to project.
- Where in UI: My digests → ⋮.
- Parameters / options: —
- Limits: —
- Relations: DIG-04, PROJ-03.
- Sources: pages/instructions__how-to-set-up-a-digest.md, pages/documentation__digests.md
- Tag: [doc]

### JB-DIG-16 — Digest limits
- Description: Free mode: ≤50 latest messages per generation (unlimited in paid modes); message window ≤1 week; generations per month plan-dependent (free 30); scheduled digests and sources per digest plan-dependent; instant unlimited; forum topics unlimited.
- Where in UI: —
- Parameters / options: —
- Limits: as listed.
- Relations: AI-05, AI-07, DIG-09.
- Sources: pages/documentation__digests.md, pages/features__ai-digests.md, pages/instructions__how-to-set-up-a-digest.md
- Tag: [doc]

---

## PROJ — Projects

### JB-PROJ-01 — Projects (Проекты)
- Description: Group forwardings and digests by topic (e.g. work vs personal vs crypto); filtered views per project.
- Where in UI: mini-app side (burger) menu.
- Parameters / options: name.
- Limits: higher plans (plan-dependent). One item per project [inferred from move semantics]. No commands.
- Relations: PROJ-02…04, DIG-15.
- Sources: pages/documentation__projects.md
- Tag: [doc]

### JB-PROJ-02 — Project switcher & default project
- Description: Switch between "All projects (Все проекты)" and individual projects; "Project #1 (Проект #1)" pre-created, renamable.
- Where in UI: burger menu.
- Parameters / options: —
- Limits: —
- Relations: PROJ-01.
- Sources: pages/documentation__projects.md
- Tag: [doc]

### JB-PROJ-03 — Move to project (Переместить в проект)
- Description: ⋮ next to a forwarding/digest → Move to project → choose → Select (Выбрать); "+ Create new project" inline.
- Where in UI: My forwardings / My digests lists.
- Parameters / options: —
- Limits: —
- Relations: PROJ-04.
- Sources: pages/documentation__projects.md, pages/instructions__how-to-set-up-a-digest.md
- Tag: [doc]

### JB-PROJ-04 — Manage projects (Управление проектами)
- Description: List with counters of forwardings and digests; Create new project; ⋮ → Edit (rename); ⋮ → Edit → Delete project (Удалить проект).
- Where in UI: burger → Manage projects.
- Parameters / options: —
- Limits: only empty projects can be deleted.
- Relations: PROJ-03.
- Sources: pages/documentation__projects.md
- Tag: [doc]

---

## INT — Integrations & settings

### JB-INT-01 — Save to Google Drive (Сохранять на Google Диск)
- Description: Save messages/media passing through a forwarding (incl. history copy) to Google Drive in folder "Junction Bot"/<forwarding name>; destination receives links instead of files.
- Where in UI: `… → Scheduling and publishing → Save to Google Drive`.
- Parameters / options: Text only (Только текст) / Media only (Только медиа) / Text and media (Текст и медиа); "Send nothing to destination (Не отправлять ничего в назначение)" — archive-only.
- Limits: text saving all tiers; file saving all except lowest tier. Enable before starting history copy.
- Relations: HIST-01.
- Sources: pages/documentation__integrations-and-settings.md, pages/documentation__copying-old-messages.md
- Tag: [doc]

### JB-INT-02 — Export settings (/dump)
- Description: Exports all subscriptions, forwardings/redirections and settings as a file containing bot commands (editable, re-importable).
- Where in UI: `/dump`.
- Parameters / options: —
- Limits: —
- Relations: INT-03, ACC-09.
- Sources: pages/documentation__integrations-and-settings.md, pages/documentation__troubleshooting.md
- Tag: [doc]

### JB-INT-03 — Import settings (/batch)
- Description: Send `/batch` followed by commands, one per line.
- Where in UI: `/batch` message.
- Parameters / options: —
- Limits: Telegram splits long texts; only the first message (starting with `/batch`) is processed → send long lists as several messages, each starting with `/batch`.
- Relations: INT-02, CMD-*.
- Sources: pages/documentation__integrations-and-settings.md, pages/documentation__troubleshooting.md
- Tag: [doc]

### JB-INT-04 — Interface language (/language)
- Description: Change bot UI language.
- Where in UI: `/language`.
- Parameters / options: English, Russian.
- Limits: —
- Relations: —
- Sources: pages/documentation__integrations-and-settings.md
- Tag: [doc]

### JB-INT-05 — No webhooks/API (by design)
- Description: Deliberately no HTTP webhook/REST output (lost/duplicate requests, replay needs). Recommended: create your own bot and forward the source into it (Telegram as message queue).
- Where in UI: —
- Parameters / options: —
- Limits: —
- Relations: FWD-05.
- Sources: pages/documentation__troubleshooting.md
- Tag: [doc]

---

## DIAG — Diagnostics

### JB-DIAG-01 — Delivery tracking (/track)
- Description: Wizard: send `/track`, paste link to the source message → delivery report: whether delivered and why not (filter hit, setting), plus message source code; also runs diagnostics and re-tunes the forwarding (may fix delays). First step for any non-delivery/delay ("99% filtered by own filter/setting").
- Where in UI: bot chat.
- Parameters / options: message link.
- Limits: report format only in screenshots.
- Relations: DIAG-02, DIAG-04, HIST-10, CMD-01.
- Sources: pages/documentation__troubleshooting.md, pages/instructions__delivery-report-message-has-been-successfully-delivered.md, pages/instructions__delivery-report-message-has-not-been-delivered-due-to-must-have-filter.md, pages/instructions__delivery-report-message-has-not-been-delivered-due-to-must-not-have-filter.md
- Tag: [doc]

### JB-DIAG-02 — Delivery report outcomes (Отчет о доставке)
- Description: Documented cases: "Message has been successfully delivered"; "not delivered because it hit a mustHave filter" (e.g. video vs allowing `<photo>`); "not delivered because it hit a mustNotHave filter" (photo vs blocking `<photo>`). Report shows message content type and the responsible filter.
- Where in UI: /track reply.
- Parameters / options: —
- Limits: —
- Relations: FLT-02, FLT-12.
- Sources: pages/instructions__delivery-report-*.md (3 pages)
- Tag: [doc]

### JB-DIAG-03 — Processing report (Отчет об обработке)
- Description: Per-message detailed report why a message did/didn't arrive, incl. source code; sent together with each new message.
- Where in UI: `… → Debug settings → Processing report → ON`.
- Parameters / options: on/off.
- Limits: must be enabled before the message arrives.
- Relations: DIAG-04, PROC-08.
- Sources: pages/documentation__troubleshooting.md, pages/documentation__message-processing.md
- Tag: [doc]

### JB-DIAG-04 — Message source code (Исходный код)
- Description: The HTML-ish text the bot sees when applying replacements/filters (tags, media tokens, premium emoji codes). Get it via /track, processing report, or @junction_helper0_bot.
- Where in UI: —
- Parameters / options: —
- Limits: —
- Relations: PROC-05/07/08/09, DIAG-05.
- Sources: pages/documentation__troubleshooting.md
- Tag: [doc]

### JB-DIAG-05 — @junction_helper0_bot
- Description: Forward any message (directly from source) to this bot; it replies with the source code.
- Where in UI: Telegram.
- Parameters / options: —
- Limits: —
- Relations: DIAG-04.
- Sources: pages/documentation__troubleshooting.md
- Tag: [doc]

### JB-DIAG-06 — Regex debugging
- Description: Use regex101.com with Flavor "Java 8", flags "Single line: Dot matches the new line" and "Global". Support doesn't compose regexes (ask ChatGPT/forums). Support requests for replacements need: native-forwarded source message, its source code, regex101 link, native-forwarded destination message.
- Where in UI: —
- Parameters / options: —
- Limits: —
- Relations: FLT-04, PROC-06.
- Sources: pages/documentation__troubleshooting.md
- Tag: [doc]

### JB-DIAG-07 — Junction Bot Alerts (@junction_ctrl_bot)
- Description: System notifications currently arrive in the main bot chat; recommended to add the Alerts bot and enable notifications so they aren't lost.
- Where in UI: Telegram.
- Parameters / options: —
- Limits: —
- Relations: PUB-10 (flood notify), ACC-07.
- Sources: pages/documentation__account-connection.md
- Tag: [doc]

### JB-DIAG-08 — Forwarding statuses & auto-disable
- Description: Status shown on forwarding page/table: enabled/disabled; "connecting… (подключение…)" (basic tiers, first-time source or lost access; >1 day → recreate forwarding, check service user-bot not blocked); "(expired)" suffix = link dead or bot blocked. Forwarding can switch itself off on lost source access or flood (Flood reaction = Stop).
- Where in UI: forwarding page; table "status" column.
- Parameters / options: —
- Limits: —
- Relations: ACC-08, PUB-10, UI-06.
- Sources: pages/documentation__troubleshooting.md, pages/documentation__forwarding.md
- Tag: [doc]

### JB-DIAG-09 — Troubleshooting playbook
- Description: Non-delivery: /track → forwarding enabled? → account connected/active? → account still in source? → edited message whose original was filtered. Duplicates: duplicate filter `filter`, forward deletions `yes`, edits not `new`, compare source code. Truncated text / missing premium: connected account + Premium + Copy via account. Missing pictures: Media caption `caption_name`. Missing buttons: Copy buttons on + Copy via bot. Content differs: disable replacements or test with a second forwarding; late edits. Channel missing from list: pin it, wait, or type username. Bot vs group sender: Copy via account + Anonymity.
- Where in UI: —
- Parameters / options: —
- Limits: —
- Relations: DIAG-01, FLT-15, FWD-09/10/12/17, PROC-16, PUB-03, UI-05.
- Sources: pages/documentation__troubleshooting.md
- Tag: [doc]

### JB-DIAG-10 — Support channels
- Description: FAQ (troubleshooting page), support bot @junction_support_bot, user Telegram group, AI help bot Junction Bro (@junction_bro_bot) trained on docs, news channel @junction_bot_news_ru, YouTube channel; feature requests welcome.
- Where in UI: —
- Parameters / options: —
- Limits: —
- Relations: —
- Sources: pages/documentation__getting-started.md, pages/documentation__troubleshooting.md, pages/instructions__index.md
- Tag: [doc]

---

## CMD — Bot commands (send in chat with @junction_bot)

`<source_link>` = link/@username of the source channel. Spaces inside an argument are written `&nbsp;` [doc].

### JB-CMD-01 — `/track`
- Description: Starts delivery-tracking wizard; then paste a source message link. See DIAG-01.
- Where in UI: bot chat. Parameters / options: message link. Limits: —. Relations: DIAG-01/02.
- Sources: pages/documentation__troubleshooting.md, pages/instructions__delivery-report-message-has-been-successfully-delivered.md
- Tag: [doc]

### JB-CMD-02 — `/disableall`, `/enableall`
- Description: Disable all forwardings at once / enable them all.
- Where in UI: bot chat. Parameters / options: —. Limits: —. Relations: UI-12.
- Sources: pages/documentation__forwarding.md
- Tag: [doc]

### JB-CMD-03 — `/dump`
- Description: Export settings as command file. See INT-02. Parameters: —. Limits: —. Relations: INT-02, CMD-04.
- Where in UI: bot chat.
- Sources: pages/documentation__integrations-and-settings.md
- Tag: [doc]

### JB-CMD-04 — `/batch`
- Description: `/batch` + newline-separated commands executes them. See INT-03.
- Where in UI: bot chat. Parameters: command lines. Limits: first Telegram message only. Relations: INT-03.
- Sources: pages/documentation__integrations-and-settings.md
- Tag: [doc]

### JB-CMD-05 — `/language`
- Description: Switch UI language EN/RU. Where: bot chat. Parameters: language. Limits: —. Relations: INT-04.
- Sources: pages/documentation__integrations-and-settings.md
- Tag: [doc]

### JB-CMD-06 — `/filter`
- Description: Per-source filter management. Forms: `/filter <source_link>` — list all filters; `/filter <source_link> mustHave|mustNotHave <text>` — add, same command again removes (toggle; also removes one source's copy of a global filter); `/filter <source_link> every <N>` — every N-th message; `/filter <target_link> addAllFrom <source_link>` — copy all filters.
- Where in UI: bot chat. Parameters: as listed. Limits: text-match type [inferred for value form]. Relations: FLT-03, FLT-14, FLT-18.
- Sources: pages/documentation__filters.md, pages/documentation__troubleshooting.md
- Tag: [doc]

### JB-CMD-07 — `/filterall`
- Description: `/filterall add|remove mustHave|mustNotHave <text>` — text filter on all current sources; `/filterall DELETE ALL` — delete all filters from all sources.
- Where in UI: bot chat. Limits: new forwardings not affected. Relations: FLT-19.
- Sources: pages/documentation__filters.md
- Tag: [doc]

### JB-CMD-08 — `/filterrxall`
- Description: `/filterrxall add|remove mustHave|mustNotHave <regex>`, e.g. `/filterrxall add mustNotHave .*(http:\/\/|https:\/\/).*` blocks links everywhere.
- Where in UI: bot chat. Relations: FLT-04, FLT-19.
- Sources: pages/documentation__filters.md
- Tag: [doc]

### JB-CMD-09 — `/filtertime`
- Description: `/filtertime <source_link> mustHave|mustNotHave <interval>`, e.g. `/filtertime <src> mustHave w12345 8:00-20:00 Europe/Moscow`.
- Where in UI: bot chat. Relations: FLT-06.
- Sources: pages/documentation__filters.md
- Tag: [doc]

### JB-CMD-10 — `/filtertimeall`
- Description: `/filtertimeall add|remove mustHave|mustNotHave <interval>`, e.g. `/filtertimeall add mustNotHave 0:00-7:00 Europe/Berlin`.
- Where in UI: bot chat. Relations: FLT-06, FLT-19.
- Sources: pages/documentation__filters.md
- Tag: [doc]

### JB-CMD-11 — `/replace`
- Description: `/replace <source_link> <from> [<to>]` plain replacement; omitted `<to>` = delete. Examples: `/replace source <b>needed&nbsp;piece&nbsp;of&nbsp;text</b> needed&nbsp;piece&nbsp;of&nbsp;text`; `/replace link_to_source <a href="https://specific-link">text&nbsp;of&nbsp;this&nbsp;link</a>`.
- Where in UI: bot chat. Relations: PROC-05, PROC-07.
- Sources: pages/documentation__message-processing.md
- Tag: [doc]; argument grammar [inferred from examples]

### JB-CMD-12 — `/replacerx`
- Description: `/replacerx <source_link> <regex> [<to>]`, e.g. `/replacerx source <a[^<]+</a>`; `/replacerx source (http:\/\/|https:\/\/)([a-zA-Z0-9.\/\?=&_]+)`.
- Where in UI: bot chat. Relations: PROC-06.
- Sources: pages/documentation__message-processing.md
- Tag: [doc]

### JB-CMD-13 — `/setting`
- Description: Change a forwarding setting by command: `/setting author none|name|username|full|full_except_bot`; `/setting header none` (source name); `/setting mybuttons` + lines `<url> <label>`; `/setting like <words>` (feedback buttons). Which forwarding it targets is not documented.
- Where in UI: bot chat. Relations: PROC-12/13/14/15.
- Sources: pages/documentation__message-processing.md
- Tag: [doc]

### JB-CMD-14 — `/settingchannel`
- Description: Per-channel setting, e.g. `/settingchannel C duplicate filter` (enable duplicate filter on forwarding from channel C).
- Where in UI: bot chat. Relations: FLT-15.
- Sources: pages/documentation__filters.md
- Tag: [doc]

### JB-CMD-15 — Inline channel search
- Description: In any chat type `@junction_bot <word>` (e.g. `@junction_bot котик`) → list of channels known to the bot whose username/title/description contain the word.
- Where in UI: Telegram inline mode. Relations: FWD-03.
- Sources: pages/documentation__forwarding.md
- Tag: [doc]

### JB-CMD-16 — Subscribe by sending a link
- Description: Send `@channelname` (public) or invite link (private) to the bot chat to receive that source in the bot chat feed.
- Where in UI: bot chat. Relations: TOP-09.
- Sources: pages/documentation__forwarding.md
- Tag: [doc]

---

## UI — Interface & management

### JB-UI-01 — Mini-app & menus
- Description: Mini-app opened by the Menu button (blue button left of input). Main menu items: Main functions (Основные функции) → Forward messages (Пересылать сообщения), Copy chat history (Копировать историю чата); Create forwarding (Создать пересылку); My forwardings (Мои пересылки); My digests (Мои дайджесты); Personal account (Личный кабинет) / My account (Мой аккаунт); Web app (Веб-приложение). Side/burger menu (☰): projects, Manage projects, My digests, My account.
- Where in UI: —
- Parameters / options: —
- Limits: —
- Relations: UI-02, UI-08, PROJ-02, UI-14.
- Sources: pages/documentation__getting-started.md, pages/documentation__forwarding.md, pages/documentation__projects.md, pages/instructions__how-to-set-up-a-digest.md
- Tag: [doc]

### JB-UI-02 — Forwarding creation wizard
- Description: Specify source → Specify destination (optionally Create new chat) → Topic mapping (if topics; else skip) → Main settings: Forwarding type (New messages (Новые сообщения) / Old messages (history)), Delivery mode, automatic link replacement (Expert) → Create (Создать). Warns if bot isn't admin in a new destination.
- Where in UI: Menu → Create forwarding / Main functions → Forward messages.
- Parameters / options: as listed.
- Limits: —
- Relations: FWD-03, TOP-01, HIST-01, PUB-01, PROC-10, UI-04.
- Sources: pages/documentation__forwarding.md, pages/instructions__how-to-forward-from-public-telegram-channel-or-group.md, pages/instructions__how-to-forward-from-private-telegram-channel-or-group.md
- Tag: [doc]

### JB-UI-03 — Default configuration
- Description: New forwarding gets a default config that delivers immediately; no extra setup required. Empty filter list.
- Where in UI: settings menu after creation.
- Parameters / options: defaults documented: Link to original `none`, Source name `none`, Filter forwards `all`, Flood reaction Postpone [doc]; others not stated.
- Limits: —
- Relations: FLT-01.
- Sources: pages/documentation__getting-started.md, pages/documentation__filters.md
- Tag: [doc]

### JB-UI-04 — Create new chat (Создать новый чат)
- Description: Create destination channel or group from the destination picker (name + type → OK); then bot must be made admin (wizard prompts).
- Where in UI: Specify destination.
- Parameters / options: name; channel|group.
- Limits: connected account flows [inferred].
- Relations: UI-02.
- Sources: pages/instructions__how-to-forward-from-private-telegram-channel-or-group.md, pages/instructions__how-to-forward-from-public-telegram-channel-or-group.md
- Tag: [doc]

### JB-UI-05 — Chat picker & pin workaround
- Description: If a chat isn't in the source/destination list: close mini-app, pin the chat in Telegram, wait a few minutes, reopen; else type username manually. For bots — message them first.
- Where in UI: pickers.
- Relations: FWD-03.
- Sources: pages/documentation__troubleshooting.md, pages/documentation__forwarding.md
- Tag: [doc]

### JB-UI-06 — Table view (Табличный вид)
- Description: All forwardings on one screen; click row to open settings. Default columns: Source name, Destination name, Status. Optional (⚙️): source username/ID/type, phone of account in source, destination username/ID/type, phone of publishing account, creation date, last settings update. Per-column search filter, multi-column sorting, drag-and-drop reorder, resize. Grouping into tabs via "Place on tabs (Расположить на вкладках)" (e.g. Status → enabled/disabled; Source account phone → per connection); "Place tabs vertically (Расположить вкладки вертикально)"; first tab "All (Все)"; tab counts; tabs sorted by count.
- Where in UI: Menu → My forwardings.
- Relations: UI-07, UI-09, ACC-04.
- Sources: pages/documentation__forwarding.md
- Tag: [doc]

### JB-UI-07 — Mobile display modes
- Description: ⚙️ top right: Compact (Компактный; tabs possible), Wide (Широкий; table), Auto (Авто; adapts). Desktop/tablet recommended.
- Where in UI: My forwardings.
- Relations: UI-06.
- Sources: pages/documentation__forwarding.md
- Tag: [doc]

### JB-UI-08 — Web app (Веб-приложение)
- Description: Open the mini-app in a regular browser window (main menu → Web app).
- Relations: UI-06.
- Sources: pages/documentation__forwarding.md
- Tag: [doc]

### JB-UI-09 — Saved table layout
- Description: Table configuration persists; "Default settings (Настройки по умолчанию)" resets.
- Relations: UI-06.
- Sources: pages/documentation__forwarding.md
- Tag: [doc]

### JB-UI-10 — Clone forwarding (Клонировать)
- Description: Gear icons next to From (Откуда) / To (Куда) → "Clone to another source (Клонировать на другой источник)" / clone to another destination → pick new chat → copy with all settings.
- Where in UI: forwarding settings header.
- Limits: counts as new forwarding [inferred].
- Relations: UI-11, FLT-18.
- Sources: pages/instructions__how-to-clone-a-forwarding.md
- Tag: [doc]

### JB-UI-11 — Change source (Изменить источник)
- Description: From ⚙ → Change source → expand list → choose chat (and reader connection).
- Relations: ACC-04.
- Sources: pages/instructions__how-to-split-forwardings-into-2-accounts.md
- Tag: [doc]

### JB-UI-12 — Pause forwarding (Приостановить)
- Description: Temporarily disable keeping all settings.
- Where in UI: `… → Copying new (Копирование новых) → Pause`; all at once `/disableall`.
- Relations: CMD-02, PUB-10.
- Sources: pages/documentation__forwarding.md
- Tag: [doc]

### JB-UI-13 — Delete forwarding (Удалить)
- Description: Full deletion; settings and filters cannot be restored.
- Where in UI: `… → Delete`.
- Relations: INT-02 (backup via /dump first [inferred]).
- Sources: pages/documentation__forwarding.md
- Tag: [doc]

### JB-UI-14 — Personal account screen (Личный кабинет / Мой аккаунт) — functional parts
- Description: Shows packages and connected numbers; Connect account, Reconnect, edit 📝 → change connected number, Connect a new account, number transfer; check account active. (Billing parts excluded.)
- Where in UI: Menu → Personal account.
- Relations: ACC-01/04/05/06/09.
- Sources: pages/documentation__account-connection.md, pages/documentation__troubleshooting.md, pages/instructions__how-to-change-connected-account.md
- Tag: [doc]

---

## Contradictions & ambiguities across pages

1. **Economy delivery speed**: "usually up to an hour" (getting-started, troubleshooting) vs "1 min" (plan matrix, ai-digests).
2. **Free AI quota**: 10 free processings / 30 days (integrations, setup-ai) vs 30 free generations / month (digest instruction, matrix). Possibly separate counters for messages vs digests; AI mode is said to be global.
3. **Free digest sources**: 3 public sources (instruction, FAQ, table) vs 1 public source chat (pricing card).
4. **Stories gate**: Expert only (forwarding docs) vs Direct+Expert (matrix).
5. **Own messages filter**: Direct/Expert (filters doc) vs all tiers (matrix).
6. **Schedule & Delivery frequency**: docs require account delivery (Direct/Expert) vs matrix "all".
7. **Moderation**: "depends on plan" and works via connected account (docs) vs "all" tiers (matrix).
8. **Replacements scope**: "text and buttons only; images via moderation" (docs) vs "Replacements (text and images)" (matrix).
9. **Buttons in account mode**: Premium rich text shows link buttons (forwarding, message-processing) vs "Telegram allows buttons only to bots" (troubleshooting); notification buttons unsupported in account mode.
10. **Regex `.` and newlines**: troubleshooting says Junction behaves like regex101 with "Single line (dot matches newline)" vs message-processing example 16 says `.*` covers one line and needs `(?s)`.
11. **Menu labels drift**: "Keywords and stop words" vs "Filters (Фильтры)"; delayed filter at "Filtering → Reactions filter" / "Scheduling and publishing → Delay" vs "Delay and delayed filter"; media caption under "Images and video" vs "Content (Контент)"; "Filter forwarded messages" vs "Filter forwards"; "Replace cross-links with source" vs "Replace links to the source".
12. **Clone instruction**: says tap the gear next to **To** to clone to another source (likely should be From).
13. **Digest template names**: "News overview"/"Group discussions" (docs) vs "News digest"/"Group digest" (features page); digest destination single (docs) vs "one or more chats" (features).
14. **Ad check marker**: РЕКЛАМА (instruction) vs ПРОПУСК (filters doc example after editing the prompt).
15. **Source name options**: docs list `simple` and custom value; instruction lists only bold/from_only/id/date/none.
16. **Moderation own chat admins**: doc says @Junction_Review_Bot + connected account must be admins; instruction also says "the bot must be an administrator".
17. **Account connection marketing** claims "any number of sources" while forwarding/folder counts are plan-limited (folders: Direct 5, Expert unlimited).
18. **Getting started** says 5 packages but names 4 (Economy, Express, Direct, Expert); "Business" appears elsewhere.
19. **Matrix-only features** with no documentation: Delayed deletion (PUB-12), "Interval filter (for messages following the last published one)", "topics" filter.
