# How to create a digest (Как создать дайджест)
- Source: https://www.junctionbot.io/ru/instructions/how-to-set-up-a-digest
- EN: https://www.junctionbot.io/instructions/how-to-set-up-a-digest
- Fetched: 2026-11-19, method: curl+html2md

## Content
Category tag: Instruction (Инструкция)

### Steps
(Each step is a screenshot with a caption; screenshots have no alt text.)

1. Open the chat with Junction Bot and tap **Menu** (Меню).
2. On the app's main page open the side menu.
3. In the side menu open the section "My digests" (Мои дайджесты).
4. A window opens where you need to specify the digest's sources. On the Econom (Эконом) and Express (Экспресс) packages, paste a link to a public channel or group.
5. On the Direct (Директ) and Expert (Эксперт) packages with a connected account, all source types are available, including private and protected ones. Select a source from your chat list and tap "Add" (Добавить).
6. You can include additional channels or groups in the digest by tapping "Add source" (Добавить источник). In free mode 3 sources are available; this limit can be increased with a package [payment-related content omitted].
7. The digest is ready! The name and other settings are set by default. To save, tap "Create digest" (Создать дайджест). Below we describe additional options.

### Additional settings
We'll go through the settings Digest type, Publication time and Publication place in turn.

(1) **Digest type** (Тип дайджеста) determines how the AI formats and presents the information. You can keep the default template (e.g. "News overview" (Новостной обзор) or "Group discussions" (Обсуждения в группе)) or create your own format. To do this tap "Edit" (Редактировать) (an existing template) or "Create prompt" (Создать промпт), changing the instruction text, processing model or other settings (more: [Digest type](/documentation/digests#type)).

(2) **Publication time**: choose the mode "On schedule" (По расписанию) (the digest arrives automatically) or "Instant digest" (Мгновенный дайджест) (launched manually). In the schedule you can set the same time for all days or configure different times per day.

(3) **Publication place**: by default the digest is sent to your private chat with Junction Bot. Optionally you can publish to an external channel/group and choose on whose behalf to publish (bot or connected account). To do this choose "Publish to chat" (Публиковать в чат) and add a destination from the list. Then choose on whose behalf the digest will be published in the chat — your account or our bot.

### Preview
You can evaluate the result right away by tapping "Preview" (Предпросмотр). Choose a period (e.g. "For a week" (За неделю)) and tap "Generate" (Сгенерировать). Previews also consume generations (see below).

### Generations
After saving, the digest appears in the "My digests" list. There are 3 modes for generations:
1. **Free mode**: 30 generations per month are available; the base amount can be increased with a package [payment-related content omitted]. This limit resets monthly. In free mode one default model is used for processing.
2. [payment-related content omitted] (paying from the internal in-bot balance; number of generations limited only by available balance).
3. **Use your own OpenRouter (or OpenAI) API key** to pay generations directly to the provider. Junction Bot does not charge for AI processing in this case. Generation limits must be checked with your provider.

### Digest actions
In the digest list you can tap (...) to open a list of useful actions:
- Enable or pause generation with the "Disable" (Отключить) option,
- Copy with settings preserved,
- Generate now,
- Move to a project (for organization convenience).

## Features mentioned
- Digests (Мои дайджесты) — AI-generated summaries of one or more source chats, separate entity from forwardings [doc]
- Source types by plan — public links only on Econom/Express; private/protected via connected account on Direct/Expert [doc]
- Source limit — 3 sources in free mode, plan-dependent [doc]
- Digest type templates — "News overview", "Group discussions", custom prompts with model choice [doc]
- Schedule modes — "On schedule" (same time daily or per-day times) vs "Instant digest" (manual) [doc]
- Publish target — default private chat with bot, or external channel/group as bot or connected account [doc]
- Preview with period — e.g. "For a week", consumes generations [doc]
- Generation quota — 30/month free, monthly reset, single default model; plan-dependent [doc]
- BYO API key — OpenRouter or OpenAI key for AI processing [doc]
- Digest actions — disable/pause, copy with settings, generate now, move to project [doc]
- Projects — organizing digests into projects [doc]

## Open questions / ambiguities
- Whether "Instant digest" covers a configurable period (like preview) is not stated.
- Exact per-day schedule UI only in screenshots.
