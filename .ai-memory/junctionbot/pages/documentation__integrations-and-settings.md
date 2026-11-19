# Integrations and settings (Интеграции и настройки)
- Source: https://www.junctionbot.io/ru/documentation/integrations-and-settings
- EN: https://www.junctionbot.io/documentation/integrations-and-settings
- Fetched: 2026-11-19, method: curl+html2md

## Content

### AI integration (Интеграция с ИИ)

`PLEASE NOTE!`

AI message processing is only possible when messages are delivered by the [copy method](/ru/documentation/publishing-and-moderation#publishing-mode)! Telegram does not allow modifying forwarded messages, so processing in forward mode is unavailable.

AI lets you describe in plain language the action you want to perform on the **text** of a Telegram message from the source. Junction Bot then sends the message and your instructions to the AI and publishes the processing result to the destination.

Popular use cases include:

- translation into another language,
- analysis and summarization of long texts,
- smart filtering,
- changing numbers in the text by given criteria,
- and much more.

**Important:** AI processing applies **only to text**; image processing is currently unavailable.

AI processing is configured per forwarding. Go to the forwarding's settings and choose the AI processing section:

**Where to find**

`Menu → My forwardings → Select a forwarding → Text processing → AI text processing` (`Меню → Мои пересылки → Выберите пересылку → Обработка текста → ИИ обработка текста`)

#### How to set up AI message processing (Как настроить ИИ обработку сообщений)

[Instruction card] Instruction: [How to set up an AI integration](/ru/instructions/how-to-setup-an-ai-integration)

The main AI processing screen is split into three logical blocks for managing your AI instructions (prompts):

- **Active prompt** (`Активный промпт`): the prompt currently working for this forwarding. If no prompt is applied, this block is hidden.
- **My prompts** (`Мои промпты`): list of all prompts you created or modified yourself.
- **Prompt library** (`Библиотека промптов`): collection of ready-made templates for popular tasks.

#### How to use prompts (Как использовать промпты)

##### Applying a prompt (Применение промпта)

To activate a prompt, tap it in the list, then tap the "**Apply**" (`Применить`) button that appears at the bottom of the screen.

The prompt then moves to the **"Active prompt" block** and starts working.

**Important:** you can use one and the same prompt for several forwardings. If you edit such a prompt, the changes apply to all forwardings where it is used.

##### Editing and other actions (Редактирование и другие действия)

Each prompt has a context menu (three-dots icon). Through it you can **Edit** (`Редактировать`), **Copy** (`Скопировать`) or **Stop** (`Остановить`) the active prompt. When stopped, the prompt is deactivated and returns to its list.

**Important:** editing a prompt from the Library and saving it always creates a copy in "My prompts". The original template stays unchanged.

#### How to create your own prompt (Как создать свой промпт)

If you need a unique AI instruction, create your own prompt.

- In the "My prompts" block tap **+ Create prompt** (`+ Создать промпт`).
- An edit screen opens. Fill in the fields. **For example, if you want hashtags to be added automatically to tech news:**
  - **Name** (`Название`): Tech hashtags
  - **Description** (`Описание`): Adds #ai, #startup, #crypto to tech posts.
  - **Prompt text** (`Текст промпта`): "Analyze the text. If it is about technology, artificial intelligence, startups or cryptocurrencies, add suitable hashtags at the end: #ai, #startup, #crypto."
  - **Creativity** (`Креативность`): 0.7
  (**Creativity** ("temperature") defines the response style: the higher, the more artistic the answer; the lower, the more "scientific"/precise. Recommended: 0.7.)
- At the end you have two options:
  - **Save and apply** (`Сохранить и применить`): the prompt is created and immediately activated for the current forwarding, landing in "Active prompt".
  - **Save** (`Сохранить`): the prompt is simply added to "My prompts" to apply later.

#### AI processing modes (Оплата ИИ обработки)

Several AI processing modes are offered. **Important:** the choice applies to all your forwardings and other AI services in the bot. To switch mode, tap the mode selector at the top of the settings page.

1. **Free mode** (`Бесплатный режим`) — **10 free processings** every 30 days; each active plan increases this limit (limit depends on plan). Free mode uses one default model.
2. **Pay from balance** (`Оплата с баланса`) — gives access to **300+ AI models**, using OpenRouter's provider-selection optimization (automatically picks the best provider by cost and speed for the chosen model). [payment-related content omitted]
3. **Use your own API key** (`Использовать свой API ключ`) — connect your own API key from a provider; Junction Bot does not charge for processing in this case.
   - **OpenAI** — request goes via OpenAI; only OpenAI models are supported. Enter your OpenAI API key in settings.
   - **OpenRouter** — request goes via the OpenRouter LLM aggregator (300+ models from various providers, including free models — so with your own OpenRouter account messages can be processed for free). Enter your OpenRouter API key in settings.

### Saving to Google Drive (Сохранение на Google Диск)

Junction Bot can save messages and media passing through a forwarding to your Google Drive. The bot creates a "Junction Bot" folder on the Drive, and inside it a folder named after the forwarding. Instead of the files themselves, links to them are sent to the destination.

**Where to find**

`Menu → My forwardings → Select a forwarding → Scheduling and publishing → Save to Google Drive` (`Планирование и публикация → Сохранять на Google Диск`)

Modes: **Text only** (`Только текст`), **Media only** (`Только медиа`), **Text and media** (`Текст и медиа`). The option **"Send nothing to destination"** (`«Не отправлять ничего в назначение»`) lets you quickly make a data copy without publishing anything in the destination.

Saving texts is available on all plans; saving files — on all except the lowest plan (depends on plan).

## Other bot settings (Другие настройки бота)

### Bot interface language (Язык интерфейса бота)

To change the bot interface language, use the command `/language`.

Available languages: English and Russian.

### Import and export of settings (Импорт и экспорт настроек)

With the `/dump` command you can export as a file all current subscriptions, redirections and related settings. The file is a list of commands for the bot.

You can execute some or all of these commands as one list with the `/batch` command. Send the bot a list of commands starting with `/batch`, where each line contains a separate command.

Note that when you send Telegram a text that is too long, it is split into several messages. In that case the bot processes only the commands in the first message (the one starting with `/batch`). To process a very long command list, send it yourself in several messages, making sure each starts with `/batch`.

## Features mentioned
- AI text processing — per-forwarding prompt applied to message text only (copy mode only; no images) [doc]
- Prompt management — Active prompt / My prompts / Prompt library; apply, edit, copy, stop; shared prompts across forwardings [doc]
- Custom prompts — name, description, prompt text, creativity (temperature, default 0.7); save or save-and-apply [doc]
- AI modes — free quota (10/30 days, plan-dependent increase, default model), balance mode (300+ models via OpenRouter), own key (OpenAI / OpenRouter); global choice [doc]
- Google Drive saving — folder per forwarding, links sent instead of files; text/media/both; "send nothing to destination" archive mode; file saving plan-dependent [doc]
- Interface language — `/language`, EN/RU [doc]
- Settings export/import — `/dump` produces command list; `/batch` executes multi-line commands (only first message of a split text) [doc]

## Open questions / ambiguities
- AI "smart filtering" is listed as a use case, but the mechanism (how AI output causes a message to be dropped) is not described.
- Whether Google Drive file links replace media in destination for every mode (e.g. text-only mode) is not specified.
