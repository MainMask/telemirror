# Getting Started (Начало работы)
- Source: https://www.junctionbot.io/ru/documentation/getting-started
- EN: https://www.junctionbot.io/documentation/getting-started
- Fetched: 2026-11-19, method: curl+html2md

## Content

**Junction Bot is a complete solution for managing messages and content in Telegram. This step-by-step guide helps you set up your first forwarding in 10 minutes.**

### Video overview (Видеообзор)

The video below covers: how to set up **copying messages from a private (closed) channel**, what **filters** and **replacements** are, how to copy from a whole **folder** and save messages and media to **Google Drive**, plus several other useful bot features.

[video]

### What Junction Bot can do (Что умеет Junction Bot)

**The system automates a whole range of processes:**

- **monitoring** channels and chats, **forwarding** new posts
- **filtering** and **sorting** the message stream
- creative **reworking** of content with neural networks (AI)
- **editing** and **formatting** forwarded messages, **processing** media
- **publishing** content to your channels and chats
- **backup** copying of message history

Users find many applications for the bot: from collecting a news feed and saving conversations to automating trading, business processes and running a network of channels.

Ready to start? Below are 4 steps to create a forwarding: from choosing the package you need to advanced settings.

### Step 1. Choosing a package (Шаг 1. Выбор пакета)

Junction Bot offers 5 packages that differ in capabilities. Their description and a feature comparison are on the plans page (/ru/plans). A questionnaire on the page helps pick the optimal service for your task.

[payment-related content omitted]

Package names referenced throughout the docs (functional tiers): Economy (Эконом), Express (Экспресс), Direct (Директ), Expert (Эксперт).

### Step 2. Connecting an account (Шаг 2. Подключение аккаунта)

*Only for the Direct and Expert packages.*

If you chose Economy or Express, the bot is ready to work immediately after activation and you can go to the next section.

Direct and Expert provide advanced functionality by connecting the bot to your account, so first perform the connection procedure:

- In the app's main menu choose **Personal account (Личный кабинет)**. Find your Direct or Expert package among your current packages and press **Connect account (Подключить аккаунт)** on the package card.
- You will land in a chat with the bot. Follow the bot's instructions.

**Important nuances:**

- The connected account is not necessarily the account from which you pay for and manage the bot (the *managing account*). What matters is that the connected account is a member of the sources you intend to forward messages from.
- One managing account can use many connected accounts. [payment-related content omitted]
- Do not delete the channel "Junction Bot Service Channel" created by the bot. It is needed for service messages. You can archive it so it doesn't get in the way.
- Do not block or delete the chat with @junction_bot from the connected account. This may cause the bot to malfunction.

### Step 3. Creating a forwarding (Шаг 3. Создание пересылки)

The forwarding rule is the basic element of the Junction Bot system. It defines where the bot copies from, how it transforms messages, and where it publishes them. After the subscription is activated, the bot offers to create your first forwarding rule.

- Before starting, make sure you have a publishing destination ready: invite Junction Bot into your target channel or chat and give admin rights to the bot and to your account.
- Now open the mini-app and choose **Menu → Main functions → Forward messages (Меню → Основные функции → Пересылать сообщения)**.

[img: Instruction image]

- Instruction: How to create a forwarding from a public Telegram channel or group (/ru/instructions/how-to-forward-from-public-telegram-channel-or-group)
- Instruction: How to create a forwarding from a private Telegram channel, group or chat (/ru/instructions/how-to-forward-from-private-telegram-channel-or-group)

#### Economy and Express (without a connected account)

1. Set the source. It can be a public group or channel (on Express — also private groups and channels).
   - Enter the source's **link** or **@username** into the search bar (on Express an **invite link** to a private channel also works).
   - Press "➤ Find channel in Telegram" («➤ Найти канал в Telegram»).
   - Select the found channel.
2. Set the destination. It can be any group or channel of yours where **the bot and your account are admins**.
   - Enter the destination's **link** or **@username** into the search bar.
   - Press "➤ Find channel in Telegram".
   - Select the found channel.

Done — the rule is created and the bot starts forwarding! Note that delivery on the **Economy** service is delayed (usually up to an hour). On **Express** the bot may need a little time to connect to the sources, after which messages arrive instantly.

#### Direct and Expert (with a connected account)

- Set the source. It can be a public, private or closed (restricted) group or channel, a personal chat, a bot, or a folder. Your account must be a member of it.
- Set the destination. It can be any group or channel, as well as a personal chat or a bot. It's enough that the bot or the connected account has posting rights there.
- Done — the rule is created and the bot instantly starts forwarding!

### Step 4. Configuring the forwarding (Шаг 4. Настройка пересылки)

After choosing the source and destination you land in the **settings menu (меню настроек)**. The bot has already applied a default configuration to the new forwarding; messages will be delivered and no extra configuration is required. If that's not enough, this overview helps you take the first steps toward advanced configuration.

#### How to forward only important messages?

- In the Filtering (Фильтрация) section (/ru/documentation/filters) you can set message selection rules. Messages that don't meet the criteria won't be copied. A filter condition can be a keyword, a regular expression, the author, publication time, etc.
- The Duplicate filter (Фильтр дублей) setting (/ru/documentation/filters#filtering-duplicates) helps get rid of duplicate messages.
- Let a neural network select messages (/ru/documentation/filters#ai-filtering). For example, you can ask the AI to pass only positive news :)

#### How to add to, replace or delete the original text?

- To add your own text to a message, use the settings Add header (Добавлять заголовок) (/ru/documentation/message-processing#add-text-before-after) and Add text after the message (Добавлять текст после сообщения) (/ru/documentation/message-processing#add-text-before-after).
- To replace part of the text with your own or delete it, use Replace links and words in text (Замена ссылок и слов в тексте) (/ru/documentation/message-processing#replacing-text). If the source text varies within a certain range (e.g. it's a link or a contract address), a regular expression can be used for the replacement (/ru/documentation/message-processing#replacing-text-regex).

Instruction: How to replace a word or part of text when copying messages (/ru/instructions/how-to-replace-a-word-or-part-of-text-when-copying-messages)

#### How to show the author, the source name and a link to the original post?

- In the Author (Автор) section (/ru/documentation/message-processing#author) you can enable display of the author's name and username.
- In the Source name (Название источника) setting (/ru/documentation/message-processing#title) — the source name or the publication date.
- The Link to the original post (Ссылка на оригинальный пост) parameter (/ru/documentation/message-processing#source-link) defines in what form to publish a link to the source and to the messages in it.

[img: Instruction image]

- Instruction: How to specify the author when copying messages (https://www.junctionbot.io/ru/instructions/how-to-specify-the-author-when-copying-messages)
- Instruction: How to specify the source chat name (/ru/instructions/how-to-specify-the-name-of-the-source-chat-when-copying-messages)
- Instruction: How to add a link to the original message (/ru/instructions/how-to-add-a-link-to-the-original-message-when-copying-messages)

#### How to choose the message sender?

- Normally the bot publishes posts in groups under its own name, but Direct and Expert allow publishing messages on behalf of your connected account, making the bot's work in groups invisible. The method is set in the Delivery mode (Режим доставки) section (/ru/documentation/publishing-and-moderation#publishing-mode).

#### How to copy from a specific topic in a group, or into a specific topic?

- Use the **Topic mapping (Сопоставление тем)** setting.

[img: Instruction image]

- Instruction: How to forward messages between topics in Telegram groups (/ru/instructions/how-to-forward-messages-between-topics-in-telegram-groups)
- Instruction: How to forward messages from several group topics into the General topic (/ru/instructions/how-to-forward-messages-from-several-topics-to-general-topic)
- Instruction: How to copy the topic structure (/ru/instructions/how-to-copy-topic-structure)

#### How to put a watermark on images or videos?

- You can upload your own images and control how they're overlaid on forwarded media in the Watermarks (Водяные знаки) setting (/ru/documentation/message-processing#adding-watermarks).

#### How to track edits to the source post and its deletion?

- Important changes are often made to posts after publication. The Forward edits (Передавать правки) function (/ru/documentation/forwarding#fw-edits) tracks edits in the original to automatically apply corrections to the copies or send them as a new message.
- Forward deletions (Передавать удаления) (/ru/documentation/forwarding#fw-deleted) removes all copies if the original is deleted.

#### How to copy buttons and polls?

- You can configure how interactive post elements are transferred using the settings Copy buttons (Копировать кнопки) (/ru/documentation/forwarding#fw-buttons) and Polls (Опросы) (/ru/documentation/forwarding#fw-polls).

#### How to limit the frequency of new publications and forward them with a delay?

- If you want to send messages with a delay after publication in the source and publish them at a certain interval, use the settings Delay (Задержать) (/ru/documentation/publishing-and-moderation#pub-delay), Schedule (Запланировать) (/ru/documentation/publishing-and-moderation#pub-scheduling) and Delivery frequency (Частота доставки) (/ru/documentation/publishing-and-moderation#pub-frequency).

[img: Instruction image]

Instruction: Delayed filters (Отложенные фильтры) (/ru/instructions/delayed-filters)

#### How to add new posts to pinned messages?

- The bot can pin messages in the target channel with a notification, or deliver them in silent mode. Use the settings Pin posts (Закреплять посты) (/ru/documentation/publishing-and-moderation#pinned) and Silent mode (Тихий режим) (/ru/documentation/publishing-and-moderation#silent-mode).

#### How to review messages before forwarding?

- You can view posts collected by the bot in a separate chat and manually approve their publication in the target channel. This is the Moderation (Модерация) function (/ru/documentation/publishing-and-moderation#review-mode).

[img: Instruction image]

- Instruction: How to set up manual moderation via your own chat (/ru/instructions/how-to-set-up-manual-moderation-via-own-chat)
- Instruction: How to set up manual moderation via @Junction_Review_Bot (/ru/instructions/how-to-set-up-manual-moderation-via-junction-review-bot)

#### How to copy comments on posts?

- You can copy not only channel posts but also the comments on them. Enable the Comments (Комментарии) setting (/ru/documentation/forwarding#fw-comments) (group "Other content" («Прочий контент»)).

### Next steps (Дальнейшая работа)

The first forwarding is created and configured. What can you do next?

- **View the list of forwardings.** All your forwarding rules are in **Menu → My forwardings (Меню → Мои пересылки)**. The mini-app opens via the **Menu** button on the bot's page in Telegram.
- **Read** the blog (/ru/articles) — useful tips and simple Junction Bot guides.
- **Look into** the documentation (/ru/documentation/forwarding) — all bot functions and how to use them are described in detail.
- **Check the account state.** In the mini-app main menu choose **Personal account (Личный кабинет)**.
- **Subscribe** to the news channel (https://t.me/junction_bot_news_ru) to stay up to date with the latest updates.

### Troubleshooting (Решение проблем)

If something malfunctions or you can't figure out a setting, contact support, available through several channels:

- The troubleshooting page (/ru/documentation/troubleshooting) collects solutions to the most common difficulties (FAQ).
- Questions about bot setup or improvement suggestions: Telegram support (https://t.me/junction_support_bot).
- Telegram group (https://t.me/joinchat/WMIMAZkSpNZiNzYy) — answers from the team and other users.
- AI bot Junction Bro (https://t.me/junction_bro_bot), trained on the documentation, gives quick answers about bot functions.

## Features mentioned
- Forwarding rule — core entity: source → transform → destination [doc]
- Package tiers — Economy/Express (bot-only, no account) vs Direct/Expert (connected user account) define source types and speed [doc]
- Economy delivery delay — up to ~1 hour; Express near-instant after connecting to sources [doc]
- Source types with connected account — public/private/closed groups and channels, personal chats, bots, folders [doc]
- Destination types — groups/channels (bot+user admin); with connected account also personal chats and bots [doc]
- Source search by link/@username/invite link — "Find channel in Telegram" [doc]
- Default configuration on new forwarding — works without extra setup [doc]
- Filtering — keyword, regex, author, publication time [doc]
- Duplicate filter [doc]
- AI filtering — natural-language selection criteria [doc]
- Header / footer text — add text before/after message [doc]
- Text & link replacement, incl. regex [doc]
- Author display, source name / date, link to original post [doc]
- Delivery mode — publish as bot or as connected account [doc]
- Topic mapping — topic→topic, many topics→General, copy topic structure [doc]
- Watermarks on images/video [doc]
- Forward edits / forward deletions [doc]
- Copy buttons, polls [doc]
- Delay, schedule, delivery frequency [doc]
- Pin posts, silent mode [doc]
- Moderation (manual approval via own chat or @Junction_Review_Bot) [doc]
- Comments copying [doc]
- Google Drive saving, folder as source, AI content rework [doc]
- Service channel "Junction Bot Service Channel" — must not be deleted (archive OK) [doc]
- Mini-app menu: Main functions → Forward messages; My forwardings; Personal account [doc]
- Support: FAQ page, support bot, user group, AI help bot Junction Bro [doc]

## Open questions / ambiguities
- Page says 5 packages but only 4 are named (Economy, Express, Direct, Expert); the fifth is not named here.
- "Closed" vs "private" groups/channels distinction not defined on this page (likely: closed = copy-protected/restricted content).
