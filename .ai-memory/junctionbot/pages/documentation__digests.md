# Digests (Дайджесты)
- Source: https://www.junctionbot.io/ru/documentation/digests
- EN: https://www.junctionbot.io/documentation/digests
- Fetched: 2026-11-19, method: curl+html2md

## Content

### Digests – automating the content stream (Дайджесты – Автоматизация контент-потока) [new]

Junction Bot Digests are a tool built to **save your time on manually collecting, reading and analyzing content** from Telegram.

Instead of scrolling through dozens of channels, you set up an AI analyst that will:

- **Collect** messages from selected sources (channels and groups).
- **Summarize** them, create topical overviews or extract key points according to a template you define.
- **Publish** ready, structured material to a personal chat or public channel on a schedule.

### How to create a digest? (Как создать дайджест?)

Open the bot's mini-app and choose **"Menu → My digests" («Меню → Мои дайджесты»)**.

[img: Instruction image] Instruction: How to create a digest (/ru/instructions/how-to-set-up-a-digest)

#### Option 1: Digest in 3 clicks (Дайджест в 3 клика)

- Press **"Create digest" («Создать дайджест»)** and in the modal window **paste a link to one or more sources** (public channels or groups).
- Press **"Add" («Добавить»)**, then on the **"Sources" («Источники»)** screen — **"Continue" («Продолжить»)**. You land on the settings screen with all fields auto-filled:
  - **Digest type** — the most suitable template from the library is assigned based on source types.
  - **Publication time** — "On schedule" («По расписанию»), every day at the same time.
  - **Publication place** — "Publish to Junction Bot chat" («Публиковать в чат Junction Bot») (your personal chat with the bot).
- Press **"Save digest" («Сохранить дайджест»)**. Done! The digest will arrive every day at roughly the time you created it; the time can be changed on the **"Publication time" («Время публикации»)** screen.

#### Option 2: Customization and fine-tuning (Кастомизация и тонкая настройка)

After adding sources you can configure digest parameters before pressing **"Save digest"**:

- **Digest type:** choose from the list of system prompts or create your own (see "Templates or your own prompt" (/ru/documentation/digests#presets-or-custom-prompt)).
- **Publication time:** choose "Instant digest (manual)" («Мгновенный дайджест (вручную)») or configure publication days and times (see "Scheduled and instant digest" (/ru/documentation/digests#scheduled-or-instant)).
- **Publication place:** specify an external channel or group (see "Digest settings: Publication place" (/ru/documentation/digests#destination)).

### Scheduled and instant digest (Дайджест по расписанию и мгновенный)

Digests come in two categories depending on how you want to receive them. Chosen on the **"Publication time"** screen.

|   | Scheduled (По расписанию) | Instant (Мгновенный) |
|---|---|---|
| **What task does it solve?** | Regular monitoring and delivery strictly on time | One-off generation on request |
| **Mode** | Fully automatic | Launched only manually |
| **Limits** | Limited by slots depending on your package (limit depends on plan) | **Unlimited** |

#### How to launch instant generation

Even if a digest is set "On schedule", you can run it immediately:

- Go to the **"My digests" («Мои дайджесты»)** screen.
- On the digest's card press the three dots.
- Choose **"Generate now" («Сгенерировать сейчас»)**.

#### How to configure the schedule

See Publication time (/ru/documentation/digests#time).

### Templates or your own prompt (Шаблоны или свой промпт)

**Digest type** (or **Template**, Шаблон) is a set of instructions for the AI that defines the structure, style and content of the finished digest.

#### Using templates

- **Template library (Библиотека шаблонов)** — ready formats you can apply immediately, or edit to taste by creating a copy.
  - "News overview" («Новостной обзор») is used by default if sources are mostly channels.
  - "Group discussions" («Обсуждения в группе») is used by default if sources are mostly groups.
- **My templates (Мои шаблоны)** — your personal customized templates. They can be deleted, created from scratch and edited.

#### Creating your own prompt

If you need a unique format (e.g. "Short translation + hashtags"), create your own template:

- Click a template in the **Library** and choose **"Edit" («Редактировать»)**.
- Change the **"Prompt text" («Текст промпта»)** field (the task for the AI), **"Temperature" («Температура»)** (creativity) or **"Model" («Модель»)**.
- Press **"Save and apply" («Сохранить и применить»)**. The system creates a copy of the edited template and adds it to **"My templates"**.

**More:** detailed description of "Prompt text", "Model" and "Temperature" in "Digest settings: Digest type" (/ru/documentation/digests#type).

### Public or private sources (Публичные или приватные источники)

Collect content not only from public but also from private (closed) chats. Choosing sources is the first and most important step.

| Source type | Access | Requirements |
|---|---|---|
| **Public** (Публичные) | Channels and groups findable by link or @username. | Available to all users. |
| **Open** (Открытые) | Channels and groups joinable via a working invite link | Require the **Express** package or higher. |
| **Closed (Private)** (Закрытые (Приватные)) | Chats or channels without an invite link that you're a member of. | Require **Direct** or **Expert** and **connection of your personal Telegram account**. |

**What if you need a private source?**

- Make sure Direct or Expert is activated.
- On the source selection screen you'll see the notice: **"You have a package that requires account connection to work"** («У тебя есть пакет, для работы которого необходимо подключение аккаунта»).
- Press **"Connect account" («Подключить аккаунт»)** and follow the bot's instructions.

### Digest settings (Настройки дайджеста)

Settings you can change before saving the digest.

#### Sources (Источники)

Digest sources are the chats the AI analyzes during generation. The number of sources is limited (limit depends on plan). In the free AI mode a digest processes at most the **50 latest messages per generation**; in paid AI modes the number of messages is not limited. The message age window cannot exceed **one week**.

**Adding:** paste a link, or select from the chat list of your connected account.

#### Topics inside a group (Темы (топики) внутри группы)

If the source is a group with topics enabled, an extra selector appears.

- **Default:** **"All topics" («Все темы»)** is selected. The group counts as **one source** and takes **one slot** in your limit.
- **Partial selection:** uncheck "All topics" and choose only the needed topics.

**Important for limits:** if you manually pick several topics individually, each may be treated as a separate source, quickly consuming limits. Always use **"All topics"** if you need content from most topics.

#### Digest type (Тип дайджеста)

On the template edit screen you configure how the AI processes messages:

- **Prompt text:** the main instruction the AI uses to generate text. System templates contain prompts written by the team following prompt-engineering best practices. Use as-is or edit — the full text is transparent. Use their structure as an example, take blocks for your template, or write your own from scratch. Notes: 1) the more detailed the prompt, the more "predictable" the result (their prompts are fairly long); 2) markdown format (https://ru.wikipedia.org/wiki/Markdown) works best. The prompt defines:
  - digest structure (headings, splitting by topics, length of each topic, style of source links)
  - style and tone (formal, informal, with or without humor)

  **Important:** you can change all this and immediately test the result via Preview (/ru/documentation/digests#preview) without leaving the screen.
- **Model (Модель):** in paid AI modes you can choose one of the available models. In free mode model choice is **locked**; the default model is used (currently Google: Gemini 3 Flash Preview).
- **Temperature (creativity):** dropdown from **0** (max precision, minimal "creativity") to **2** (max variability), step 0.1. Default — **0.7**.
- **Digest example:** see sample generations for templates via the **"Example" («Пример»)** button.
- New! **Consider past digests (Учитывать прошлые дайджесты):** how many previous successful generations to take into account when generating a new digest. Lets the AI avoid repeating old news or continue a topic begun in past digests. System prompts now automatically take one previous digest into account. In paid AI modes up to **10** past digests can be considered; in free mode at most **1**. Set **0** to re-enable repeats (don't consider previous digests).

#### Metadata for use in the prompt (Метаданные для использования в промпте)

In the prompt text you can use metadata of source messages such as author name, time or view count. Each message processed has these fields (only if available in the Telegram source):

- **text** — message text in HTML format
- **date** — publication date and time
- **author_id** — numeric author ID
- **original_url** — link to the original message
- **views_count** — number of views
- **comments_count** — number of comments
- **reactions_count** — total number of reactions on the post
- **engagement_score** — engagement index, computed as the ratio of reactions and comments to views. Channel-specific; no objective benchmark, so the result is relative.
  **Important:** populated only if the source shows view counts and has info on either reactions or comments. If views are unknown, or both reactions and comments are unknown, the field is empty.
- **external_link_description** — info about the web page (title and description) the first URL in the message points to. See: web preview flag (/ru/documentation/publishing-and-moderation#preview). (Screenshot shows an example of the passed info.)

The AI also knows:

- the source name,
- the topic in which the message was published,
- if the message was a reply, the original post,
- sometimes info on the most actively liking users.

#### Publication time (Время публикации)

On the **"Publication time"** screen you can choose "Instant digest (manual)" (run manually) or configure a regular "On schedule" digest.

- Day schedule — by default **"At the same time" («В одно и то же время»)** is selected for all 7 days of the week.
- Individual time — uncheck "At the same time" to set different hours per day. Use the **"+"** button to add several time slots within one day.

If the "On schedule" option is inactive, you've run out of scheduled-digest slots (limit depends on plan; extra slots are available as a "+1 digest" add-on). [payment-related content omitted]

#### Publication place (Место публикации)

The digest can also be sent to a target channel or group:

- **Publish to Junction Bot chat** (default) — published by the bot into your personal chat with @junction_bot.
- **Publish to chat** («Публиковать в чат») — published into a third-party channel or group.
- **"Publish as" («Публиковать от имени»):** when adding an external chat you choose whose name it's published under: **the bot @junction_bot** or **your connected account**.
- **Rights check:** if publishing **as @junction_bot**, the system checks that both you and the bot are **admins** of the destination chat.

If you or the bot aren't admins, the chat won't be added: a window **"Bot must be an administrator" («Бот должен быть администратором»)** opens. Grant rights and press **"I added the bot and myself as admins" («Я добавил бота и себя в админы»)** to repeat the check.

### Preview (Предпросмотр)

Preview lets you check the AI's output before the digest is regularly published on schedule, and estimate usage before activation.

- Press **"Digest preview" («Предпросмотр дайджеста»)** on the settings screen.
- Choose a **Period** (e.g. "For a week" («За неделю») or "Since last generation" («С последней генерации»)).
- Press **"Generate" («Сгенерировать»)**.

The Telegram-styled preview window shows the generation usage according to your AI payment mode (free: number of generations spent; API key: input + output tokens used). [payment-related content omitted]

### Digest statuses (Статусы дайджеста)

On the **"My digests"** screen, digest cards have several statuses:

| Status | Description | What it means |
|---|---|---|
| **Pending** (Ожидается) | Configured and waiting for the next scheduled publication (e.g. "tomorrow at 19:00"). | Working normally. |
| **Generating** (Генерируется) | Active AI content generation in progress. | Generation running. |
| **Disabled** (Выключен) | Manually disabled by the user. | Temporarily inactive; can be enabled via the context menu. |
| **Suspended** (Приостановлен) | **Critical error.** Automatically stopped due to a system or financial problem. | **Requires attention.** Press **⚠️** for diagnostics. |

Typical reasons for "Suspended":

- **"Suspended: generations ran out"** («Приостановлен: генерации закончились») → generation quota exhausted. [payment-related content omitted]
- **"Suspended: session broken"** («Приостановлен: сессия нарушена») → the connected account's session became invalid; press **"Reconnect" («Переподключить»)**.
- **"Suspended: package ended"** («Приостановлен: закончился пакет») → the "+1 digest" (schedule slot) package ended. [payment-related content omitted]
- **"Suspended: API key unavailable"** («Приостановлен: API ключ недоступен») → your API key is invalid; check the key or choose another AI mode.

### Payment (Оплата)

[payment-related content omitted]

Functional notes from this section: the AI generation mode is **single and global** across all Junction Bot features, including Digests and AI processing of messages in forwardings — changing it on the digests screen affects all AI activity. There are three AI modes: free (default; monthly generation quota that depends on plan, one default model, max 50 messages per generation; when exhausted, digests become "Suspended"), internal balance, and bring-your-own API key (OpenRouter or OpenAI).

## Features mentioned
- Digests — AI collects messages from sources, summarizes per template, publishes on schedule [doc]
- 3-click digest — paste links → auto template, daily schedule, publish to bot chat [doc]
- Scheduled vs instant digest — scheduled limited by plan slots, instant unlimited; "Generate now" from card menu [doc]
- Template library — "News overview" (channel-heavy), "Group discussions" (group-heavy); My templates (copy-on-edit) [doc]
- Prompt editor — prompt text, model selection (locked in free mode), temperature 0–2 step 0.1 default 0.7, Example button [doc]
- Consider past digests — 0–10 previous generations to avoid repeats (1 in free mode) [doc]
- Prompt metadata fields — text(HTML), date, author_id, original_url, views_count, comments_count, reactions_count, engagement_score, external_link_description; plus source name, topic, reply parent [doc]
- Source access tiers — public (all), invite-link (Express+), closed (Direct/Expert + connected account) [doc]
- Topic selector for group sources — "All topics" = 1 slot; per-topic may count separately [doc]
- Source limits — count depends on plan; max 50 msgs/generation in free mode; window ≤ 1 week [doc]
- Schedule — same time all 7 days or per-day times, multiple slots per day via "+" [doc]
- Publication place — bot chat (default) or external chat; publish as bot or connected account; admin rights check with retry [doc]
- Preview — period (week / since last generation), shows generation/token usage [doc]
- Digest statuses — Pending, Generating, Disabled, Suspended (with ⚠️ diagnostics and reasons) [doc]
- Global AI mode — shared across digests and AI processing in forwardings; BYO OpenRouter/OpenAI key [doc]

## Open questions / ambiguities
- Whether "Open" (invite-link) sources in the table differ from "Public" for digests in practice beyond plan gating.
- Exact number of sources per digest per plan not given on this page.
