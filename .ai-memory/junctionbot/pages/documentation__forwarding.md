# Automatic Forwarding (Автоматическая пересылка)
- Source: https://www.junctionbot.io/ru/documentation/forwarding
- EN: https://www.junctionbot.io/documentation/forwarding
- Fetched: 2026-11-19, method: curl+html2md

## Content

### What is a forwarding? (Что такое пересылка?)

A **forwarding (пересылка)** is the basic element of the Junction Bot system. With a forwarding you **automate the transfer of messages between different Telegram chats** (channels, groups, bots). Both **native Telegram forwarding** and **copying** of messages are supported.

In Junction Bot, a "forwarding" is a rule according to which messages are transferred from a source to a destination. Some plans limit the number of forwardings (e.g. 25 or 100) — limit depends on plan — but the number of messages transferred within one forwarding rule is **never limited**.

The number of forwardings = the number of "source–destination" pairs. E.g. if your plan limits forwardings to 25, you can create:

- 25 forwardings from one source to 25 different destinations,
- or from 25 sources to 1 destination,
- or 25 forwardings from 25 different sources to 25 different destinations,

etc., in any combination.

### Forwarding sources (Источники пересылок)

You can forward messages from open and closed sources.

Open sources are:

- **public channels and groups**
- **private channels and groups** for which you have a working invite link

Protected Telegram channels are channels where the admins have prohibited copying and forwarding content. Attempting it, Telegram shows the error "Copying and forwarding is not allowed in this channel".

Closed sources are:

- **closed private channels and groups** (without an invite link)
- **other bots**
- **personal chats with other users**

Plan support:

- **Open public** channels and groups — **any plan**.
- **Open private** channels and groups — **any plan except Economy (Эконом)**.
- **Protected open** sources — **any plan except Economy**.
- **Closed** sources — only on **Direct (Директ) or Expert (Эксперт)** plans.

See the guide on choosing the account type (/ru/documentation/getting-started#choosing-service).

### Open sources (Открытые источники)

Open sources are **public channels and groups** and **private channels and groups that have an invite link**.

[img: Instruction image] Instruction: How to create a forwarding from an open Telegram channel, group or chat (/ru/instructions/how-to-forward-from-public-telegram-channel-or-group)

How to create a forwarding from an open source:

- **Prepare the destination chat**: create it (if it doesn't exist yet) and **add @junction_bot** to the **admins** list. You can give the bot any rights.
- Open the Junction Bot Menu (blue button left of the text input field) and choose "Main functions → Forward messages" («Основные функции → Пересылать сообщения»).
- On the "**Specify source**" («Укажи источник») screen: enter the channel's @name or link into the search bar, press "Find channel in Telegram" («Найти канал в Telegram») and **select from the search results**.
- On the "**Specify destination**" («Укажи назначение») screen: do the same for the destination channel (see destination nuances below (/ru/documentation/forwarding#destinations)).
- "**Topic mapping**" («Сопоставление тем») screen — configure forwarding between topics (/ru/documentation/forwarding#topic-mapping) if your source or destination has topics, or skip this step.
- "**Main settings**" («Основные настройки») screen:
  - Choose the **forwarding type**: start forwarding from new messages, or copy chat history (/ru/documentation/copying-old-messages),
  - Choose the **delivery mode** (/ru/documentation/publishing-and-moderation#publishing-mode),
  - Choose whether automatic link replacement is required (/ru/documentation/message-processing#links-auto-replacement).

Done! The forwarding is created and you can move to advanced settings (filtering (/ru/documentation/filters), text processing (/ru/documentation/message-processing), moderation and publishing (/ru/documentation/publishing-and-moderation)).

Note: the bot can guarantee delivery only while the invite link works for it. If the bot is banned in the source, it can no longer receive messages from there and you will need account connection (Direct or Expert).

If you want to forward not to a channel but to your own chat with the bot (to read messages without forwarding them further), see Forwarding to your own feed (/ru/documentation/forwarding#own-feed).

### Closed sources (Закрытые источники)

*Direct or Expert plan.*

With account connection (Direct and Expert) you can copy messages from closed sources: **private channels and groups, bots, private chats**.

Note: in this mode the bot only works with messages available to your account. If your account is removed from the source, the bot can no longer copy from it.

[img: Instruction image] Instruction: How to create a forwarding from a private Telegram channel, group or chat (/ru/instructions/how-to-forward-from-private-telegram-channel-or-group)

How to create a forwarding from a closed source:

- Make sure account connection is set up (in the bot app: **Menu → Personal account (Меню → Личный кабинет)**).
- Open the Junction Bot Menu (blue button left of the text input) and choose "Main functions → Forward messages".
- On the "**Specify source**" screen you see a list of all chats you're in: channels, groups, chats with other bots, private chats with other users. At the top of the list are 📁 **folders** — convenient for grouping sources. **Select one of the channels or a folder.**
- On the "**Specify destination**" screen: do the same for the destination (see destinations below).
- "**Topic mapping**" screen — configure topic forwarding or skip.
- "**Main settings**" screen:
  - Choose the **forwarding type**: from new messages or copy chat history (/ru/documentation/copying-old-messages),
  - Choose the **delivery mode** (/ru/documentation/publishing-and-moderation#publishing-mode),
  - Choose whether automatic link replacement is required (/ru/documentation/message-processing#links-auto-replacement).

Done! Proceed to advanced settings (filtering, text processing, moderation and publishing).

- If the needed source is not in the list, see Troubleshooting (/ru/documentation/troubleshooting#ts_channel-not-on-list).
- To copy the history of the channel the new forwarding was created from, use Copying old messages (/ru/documentation/copying-old-messages).

### Grouping sources into folders (Группировка источников по папкам)

*Direct or Expert plan.*

A very convenient feature: group sources and keep one set of settings applying to all sources in the group. Telegram folders are used for this.

Note: **the bot only uses sources listed in the folder explicitly**. I.e. when you see the source's name in the folder settings, it will be used. If, e.g., you set the folder to include "all channels", the bot ignores that setting.

To use grouping, **create a folder in your Telegram account and add the needed sources — channels, chats, bots**. Then create a new forwarding and choose that folder as the source (if the folder isn't in the list yet, wait a couple of minutes and refresh the list). After the folder name its composition is shown — the number of channels, groups and personal chats. That's it!

The forwarding now shows the selected folder as its source. Any message arriving in any source in the folder is forwarded to the destination. If you change the folder composition, it's automatically reflected in this forwarding.

If you have one forwarding from a folder containing source A and another forwarding directly from source A, then **a message from A is transferred only once**, using **the settings of the second forwarding** (the one where A is the explicit source).

### Destinations: feeds, channels, groups, bots (Назначения: ленты, каналы, группы, боты)

You can forward messages to:

- your own chat with Junction Bot (/ru/documentation/forwarding#own-feed) — to read messages as one feed right in the bot chat
- channels (/ru/documentation/forwarding#fw-to-channels-and-groups) where you are an admin
- groups (/ru/documentation/forwarding#fw-to-channels-and-groups) where you or the bot have posting rights
- other users and bots (/ru/documentation/forwarding#fw-to-other-bots)
- a chat or channel in the Max messenger (Expert plan) — see the article "How to forward from Telegram to Max" (https://www.junctionbot.io/ru/articles/how-to-automatically-send-from-telegram-to-max-how-not-to-lose-the-leads-when-telegram-crashes-in-russia)

Publishing on behalf of your own account (/ru/documentation/publishing-and-moderation#publishing-mode) (including DMs to other users or bots) is only possible on Direct and Expert.

#### Forwarding to your own feed (Пересылка в свою ленту)

If you just want to receive messages from open sources **in the chat with the bot**, creating a news feed for your own reading, set it up as follows. **Directly in the chat with the bot** send:

- For **forwarding from a public channel or group** — send the bot the channel/group @name. You don't need to be a member of that channel!
- For **forwarding from private channels and groups** — send the bot the invite link.

You'll be subscribed to the channels and groups and can read them right in the main chat with the bot.

Note: the bot can guarantee delivery only while the invite link works for it. If the bot is banned in the source, it can't receive messages from there and you'll need account connection (Direct or Expert).

#### Forwarding to channels and groups (Пересылка в каналы и группы)

To create a new forwarding, follow the steps above — from an open (/ru/documentation/forwarding#open-sources) or a closed (/ru/documentation/forwarding#closed-sources) source.

On the "Specify destination" screen:

- **Without a connected account (Economy and Express):** enter the channel/group name or @link in the search field, press "Find channel in Telegram" and **select from the results**.
- **With a connected account (Direct and Expert):** you see a list of all chats you're in and can pick from it.

**Pay attention to delivery modes:**

Forwarding on behalf of Junction Bot = messages in the destination channel (group) are published under the bot's name. For this, the destination's admins must include:

- Junction Bot
- and the user themself, or one of their additional accounts that has account connection.

Forwarding on behalf of the user means neither the bot nor the user needs to be an admin in the destination channel (group). It's only required that the user can post messages in that channel or group.

More on delivery modes (/ru/documentation/publishing-and-moderation#publishing-mode).

#### Forwarding to other bots (Пересылка другим ботам)

*Direct or Expert plan.*

**Where to find:** `Menu → Main functions → Forward messages → Specify source → Specify destination`

On Direct and Expert you see a list of all chats you're in and can choose from it. If you don't see the needed bot, go back to the Telegram interface and send that bot any message — it will then appear in the destinations list. Return to the menu and select it.

You can use third-party Telegram bots, e.g. to process texts or media, and then use the result in Junction Bot — see (/ru/documentation/message-processing#using_other_bots).

### New! Forwarding between topics in groups (Пересылка между темами в группах)

Junction Bot supports forwarding messages between topics in Telegram groups.

**Any sources and destinations** are supported, as long as **at least one of them has topics**. For example, you can forward:

- from one group with topics to another group with topics (**preserving the topic structure** or with **a different structure**),
- **from several topics of one group** into a topic of another group or into a channel,
- from several channels into one group, **splitting channel content into different topics**,

and many other combinations.

You can also **copy already existing** messages from specific group topics only (the "History copying" function (/ru/documentation/copying-old-messages)).

Instruction: How to forward messages between topics in Telegram groups (/ru/instructions/how-to-forward-messages-between-topics-in-telegram-groups)

Step by step:

- **Create or choose a destination** — the channel or group that should receive messages.
- To publish on behalf of the bot, add @junction_bot **as admin** of the destination channel (group). To publish on behalf of your connected account, skip this.
- If you want topics in the destination group, enable the feature first: **`Group menu > Group settings > Topics: ON`** (Меню группы > Настройки группы > Темы: ВКЛ.). If the destination won't have topics, skip.
- Now create the forwarding:
  - Open the Junction Bot **menu**
  - Choose **Main functions → Forward messages**
  - Select the **source** from the list
  - Select the **destination** (your channel or group) from the list

The next screen is topic mapping.

#### Destination is a group without topics or a channel

By default you're offered to redirect messages from all topics of the group to the destination group (channel) (left picture). You can also redirect only from specific topics (right picture).

Note the **"All other topics" («Все остальные темы»)** option. It includes all topics without an explicit mapping, and also new topics that appear after you create the rule — so messages from a new topic will also be forwarded to your destination.

#### Destination is a group with topics

By default the bot offers to redirect messages **from all topics** of the source group **into the Main (General) topic («Главная тема»)** of the destination (left picture). If you add another redirect, e.g. from source **Topic 1** to destination **My topic 1**, the first row automatically changes from **"All topics" («Все темы»)** to **"All other topics"** (right picture).

To **preserve the topic structure** of the source group in the destination, press **"Copy topic structure" («Скопировать структуру тем»)**.

Instruction: How to copy the topic structure (/ru/instructions/how-to-copy-topic-structure)

The bot automatically creates as many topics in the destination as the source has at the moment, with identical names (you can rename them later).

Note: as the first row the bot creates the redirect **"All other topics" → "Main topic"**.

Instruction: How to forward messages from several group topics into the General topic (/ru/instructions/how-to-forward-messages-from-several-topics-to-general-topic)

Keep this row in case new topics are created in the source group later — messages from them will go to the destination's **Main topic**. Delete the row if you don't want that.

You can set any topic-to-topic redirect structure (see examples in the picture). You can create topics in the destination group right on this page via **"Create topic" («Создать тему»)**.

#### Source is several different groups or channels

To forward **from different groups and channels** into **different topics of one group**, create several forwardings (one per source). On the topic mapping screen choose the needed topics in the destination group.

#### Further work with topic mapping

**Where to find:** `Menu → My forwardings → Select forwarding → Topic mapping` (Меню → Мои пересылки → Выберите пересылку → Сопоставление тем)

#### Topic auto-sync (Автосинхронизация тем)

*Expert plan.*

Enable "Sync topics automatically" («Синхронизировать темы автоматически») so the bot itself creates a topic in the destination group when a new topic appears in the source, and renames the destination topic when it's renamed in the source. Only topics created after enabling the option are synced. When a topic is deleted in the source, the destination topic is not deleted. Auto-sync works only if the source is a group with topics (not a folder and not a personal chat).

**Where to find:** `Menu → My forwardings → Select forwarding → Topic mapping → "Sync topics automatically"`

### New! Viewing and managing forwardings (Просмотр и управление пересылками)

#### New table view (Новый табличный вид)

Manage all forwardings on one screen, get all needed info at once, customize the table.

**Advantages:**

- All forwardings **visible at once**
- Quick search via **filters** and **sorting**
- **Display customization** — show only info important to you.

**Main capabilities:**

- Open any forwarding's settings **with one click on the row**
- Configure column **visibility** via the table settings menu
- **Filter** data by any parameter
- **Sort** by several columns at once
- **Group** forwardings by any parameter into tabs at the top of the table; optionally place tabs vertically on the left
- **Reorder** columns by drag-and-drop
- **Resize** columns

#### Video overview

[video] The video shows the desktop app — the most convenient way to work with the forwarding list thanks to the wide screen. Open the mini-app in the bot (Menu button), then the main menu, and choose Web app (Веб-приложение). It opens in a regular browser window.

#### Working with the forwarding list

Default **columns**:

- **Source** name
- **Destination** name
- Forwarding **status**

You can add more info via ⚙️ table settings (gear icon, top right):

- Username, ID and type of the **source**
- **Phone** of the account that is in the source
- Username, ID and type of the **destination**
- **Phone** of the account publishing to the destination
- Creation date and last settings update date

Columns **can be reordered** (drag-and-drop) and **resized**.

#### Filtering and sorting

For each enabled column you can:

- **filter** — use the search field at the top of the column
- **sort** — use the arrows next to the column name (multi-parameter sorting supported)

#### Grouping into tabs

You can group forwardings by a parameter into tabs at the top of the table, e.g.:

- by "**Status**" — 2 tabs: all enabled and all disabled forwardings.
- by "**Source account phone**" (for users with several connected accounts) — tabs per connected account.

To choose the grouping parameter, open table settings (gear icon) and in the "Place on tabs" («Расположить на вкладках») field pick the parameter.

If there are too many tabs or names are too long, **place tabs vertically on the left** via the "Place tabs vertically" («Расположить вкладки вертикально») checkbox.

Other grouping details:

- The first tab "All" («Все») shows the full list
- Each tab shows the number of forwardings
- Tabs are automatically sorted by number of forwardings

#### Saving settings

**The system remembers your settings** and shows the table as configured every time. To reset, press "Default settings" («Настройки по умолчанию») in table settings.

#### Mobile vs desktop

The mobile version has 3 display modes (⚙️ icon top right):

- **Compact** (Компактный) — convenient for mobile; forwardings can be split into tabs, e.g. by "Source account phone".
- **Wide** (Широкий) — table view mirroring the wide-screen version.
- **Auto** (Авто) — adapts to window size.

**Note:** a computer or tablet is recommended for the table view.

### Deleting or disabling forwardings (Удаление или отключение пересылок)

**Disabling:** `Menu → My forwardings → Select forwarding → Copying new (Копирование новых)`

To temporarily disable a forwarding keeping all settings, press **Pause (Приостановить)**. To disable all forwardings at once, send the bot the command `/disableall`; to enable them — `/enableall`.

**Deleting:** `Menu → My forwardings → Select forwarding → Delete (Удалить)`

For full deletion press **Delete**. Warning! Deleting a forwarding loses all its settings. **Please be careful:** deleted forwardings, along with their settings and filters, cannot be restored!

### Channel search (Поиск каналов)

If you don't know the exact channel name, use **inline-mode search**: type `@junction_bot`, a space and any word (e.g. `@junction_bot котик` / "kitty"). The bot lists all channels known to it containing that word in usernames, titles or descriptions.

### Forwarding edits and deletions (Передача правок и удалений)

What if a message is edited or deleted after Junction Bot has forwarded it? Control this with the following settings.

[video] How to sync deletions and edits in messages.

#### Forward edits (Передача правок)

*Direct and Expert plans.*

**Where to find:** `Menu → My forwardings → Select forwarding → Scheduling and publishing → Forward edits` (Планирование и публикация → Передавать правки)

**Available settings:**

- `edit` — apply the edit to the destination channel
- `new` — send the edit as a new message
- `ignore` — ignore the edit

Note: if you set a delivery delay and the original was edited before the message was published to the destination, the edit is not applied.

Edit forwarding works only in message copying mode. With native forwarding (forward) the message goes to the destination as-is and doesn't change when the original is later edited.

#### Forward deletions (Передача удалений)

*Direct and Expert plans.*

**Where to find:** `Menu → My forwardings → Select forwarding → Scheduling and publishing → Forward deletions` (Передавать удаления)

**Available settings:**

- `yes` — delete transferred messages when deleted in the source
- `no` — don't delete

Note: Telegram doesn't allow bots to delete messages older than 48 hours. If you need old messages deleted, use forwarding on behalf of your account (/ru/documentation/publishing-and-moderation#publishing-mode).

### Forwarding media (Пересылка медиа)

By default Junction Bot forwards all media types: images, video, audio, voice messages, stickers, etc.

You can overlay watermarks (/ru/documentation/message-processing#adding-watermarks) on photos and videos, control which media to pass (see media type filtering (/ru/documentation/filters#media-type)) and how captions are transferred.

#### Forwarding media captions (Пересылка подписей к медиа)

Instruction: How to copy only photo/video without text (or) how to remove all media leaving only text (/ru/instructions/media-caption)

You can choose how captions of images and multimedia are transferred.

**Where to find:** `Menu → My forwardings → Select forwarding → Images and video → Media caption` (Изображения и видео → Подпись к медиа)

**Available settings:**

- `separate` — image and caption as 2 separate messages (handy for publishing long captions via the bot).
- `caption_name` — image and caption arrive as 1 message; the caption includes the channel name and a link to the original message (if the allowed length is exceeded, caption text is shortened).
- `text_only` — transfer only the caption, without the image.

### Forwarding buttons (Пересылка кнопок)

This covers buttons attached to the source message. To add your own buttons, see (/ru/documentation/message-processing#own-buttons).

#### Copying original buttons (Копирование оригинальных кнопок)

Choose which buttons from the source message to keep. Due to how Telegram works, only link (URL) buttons will actually function as a result.

**Where to find:** `Menu → My forwardings → Select forwarding → Buttons → Copy buttons` (Кнопки → Копировать кнопки)

**Available settings:**

- `none` — don't copy buttons
- `url` — only link buttons
- `special` — everything except link buttons
- `all` — copy all buttons

When sending on behalf of your account (/ru/documentation/publishing-and-moderation#publishing-mode), buttons are transferred only if the connected account has Telegram Premium: then the message is published as rich text and only link buttons work. This applies to all modes where the message is copied on behalf of the account; in "Forward via account" («Пересылать через аккаунт») mode and without Telegram Premium buttons are not transferred.

#### Copying "Hidden continuation" buttons (Копирование кнопок "Скрытое продолжение")

*Direct and Expert plans.*

Copies buttons that show a pop-up with text when pressed. Simply duplicating the post doesn't transfer Telegram's response to the button (the message would arrive without the button). The bot implements a deeper copying mechanism for this. Buttons are not supported when sending on behalf of your account.

**Where to find:** `Menu → My forwardings → Select forwarding → Buttons → Notification buttons` (Кнопки с уведомлениями)

**Parameters:**

*Which buttons to transfer:*

- `none` — don't transfer notification buttons
- `.*` — transfer all notification buttons
- custom value — transfer buttons whose text matches the regular expression

*Button press speed (range in seconds):* use the "Custom value" («Произвольное значение») field: first argument — `.*` (any button text) or a regex for the button text; second argument (space-separated) — a range in seconds.

Example: `.* 15-300` — transfer all notification buttons with a random delay of 15 to 300 seconds.

Explanation: as soon as a message with a button appears in the source, the bot presses the button to read the notification. A human wouldn't press instantly, so to make the bot look human you can set a random delay before pressing. You probably don't want the lower bound too small (unnatural), nor too large (messages reach the destination with that delay).

*Transfer message text directly:* in "Custom value", first argument — `.*` or a regex; second — range in seconds; third (space-separated) — the `body` parameter.

Example: `.* 15-300 body` — put the notification text into the message body, without a button.

Notes:

- Replacement rules (/ru/documentation/message-processing#replacing-text) apply both to the button text and to the notification content.
- All subscribers of your destination channel will see the notification that you personally see when pressing the button in the source. Transferring individual notifications (so pressing in the destination shows what that particular subscriber would see) is technically impossible.

### Forwarding polls (Пересылка опросов)

Junction Bot can forward Telegram polls.

**Where to find:** `Menu → My forwardings → Select forwarding → Other content → Polls` (Прочий контент → Опросы)

**Available settings:**

- `none` — polls are not forwarded
- `copy` — copy polls (a separate poll with the same text is created)
- custom value — a link to the original poll is placed under this string. Example: `пройдите опрос` ("take the poll")

### Forwarding stories (Пересылка сториз)

*Expert plan.*

Choose how Stories are transferred.

**Where to find:** `Menu → My forwardings → Select forwarding → Other content → Stories` (Прочий контент → Истории)

**Available settings:**

- `message` — copy, sending the story as a regular message
- `ignore` — ignore stories

### Forwarding comments (Пересылка комментариев)

*Direct and Expert plans.* Read carefully if you want to set up comment forwarding!

Telegram channels support discussions, a.k.a. comments. **This is implemented by attaching a discussion group to the channel in a special way. All comments technically live in the group but are shown as comments to specific channel posts.**

For setup you need to find the comments group, not just view comments in the channel context. **To find the group, open the channel, tap the three dots top right next to the channel name, choose "View discussion" («Посмотреть обсуждение»)** — you'll be in the group.

**Note:** to set up comment copying, you must join this group **with the connected account** and stay in it.

Two ways to copy comments: **as separate posts and as comments.**

#### Copying comments as separate posts

Create a forwarding **from the discussion group** to the destination: just choose the discussion group from the source list. It appears there only if you have **joined it with the connected account**. For this method you don't need a forwarding from the channel itself.

#### Copying comments as comments

You need two forwardings:

- First — **from the source channel to the destination channel**. No special settings needed.
- Second — **from the source discussion group to the destination discussion group**. Choose the groups from the source and destination lists. They appear only if you **joined them with the connected account**. Also check that the bot is an admin **in the destination discussion group**.

When both exist, open the second forwarding's (group→group) setting "Comments":

**Where to find:** `Menu → My forwardings → Select forwarding → Other content → Comments` (Прочий контент → Комментарии)

**Parameters:** custom value — enter the source **channel's** number (not the discussion group's, the main source channel's), e.g. `2015095027`.

Done!

Since comments technically live in the group, for a copied comment to appear on behalf of the group (as usual when a channel admin comments), enable publishing on behalf of the account (/ru/documentation/publishing-and-moderation#publishing-mode).

Correct comment copying works only for posts published **after** setup.

### Forwarding Telegram Premium content (Пересылка контента Телеграм Premium)

Premium account owners can use long media captions; regular bots can't. The only way to transfer such messages as-is is to enable sending on behalf of your account (/ru/documentation/publishing-and-moderation#publishing-mode); that account must be connected via Direct or Expert and have active Telegram Premium.

The bot can also send captions as a separate message (/ru/documentation/forwarding#fw_caption): for a captioned image in the source, two messages arrive in the destination — the image and the text — so the caption arrives in full.

### Forwarding Premium emoji (Пересылка Premium эмодзи)

To transfer premium emoji you need to:

- choose sending on behalf of your account;
- have Telegram Premium on that account.

If so, premium emoji are transferred from source to destination automatically. To replace or insert your own premium emoji in messages, see (/ru/documentation/message-processing).

## Features mentioned
- Forwarding = source–destination pair; count limited per plan (e.g. 25/100), messages per rule unlimited [doc]
- Native forward vs copy modes [doc]
- Source classes — open public / open private (invite link) / protected / closed (no invite, bots, DMs); plan-gated [doc]
- Creation wizard — Specify source → Specify destination → Topic mapping → Main settings (type: new vs history, delivery mode, link auto-replacement) [doc]
- Bot-ban risk for invite-link sources → needs connected account [doc]
- Folder as source — explicit members only; live composition updates; dedup with direct forwarding (direct one's settings win) [doc]
- Destinations — own feed (bot chat), channels, groups, other users/bots, Max messenger (Expert) [doc]
- Own feed — send @name/invite link to bot chat to subscribe [doc]
- Delivery mode admin requirements — as bot (bot + user admin) vs as user (just posting rights) [doc]
- Forwarding to bots — message the bot first to make it appear in list; third-party bots for processing [doc]
- Topic mapping — "All topics"/"All other topics" catch-all, Main topic, Copy topic structure, Create topic [doc]
- Topic auto-sync (Expert) — create/rename destination topics, no deletion, only for group sources [doc]
- Forwardings table view — columns, filter, multi-sort, tab grouping, vertical tabs, saved layout, mobile Compact/Wide/Auto, Web app [doc]
- Pause / delete forwarding; /disableall, /enableall commands [doc]
- Inline channel search `@junction_bot <word>` [doc]
- Forward edits — edit/new/ignore; not applied if edited before delayed publish; copy mode only [doc]
- Forward deletions — yes/no; bot 48h deletion limit, use account mode for older [doc]
- Media caption mode — separate / caption_name / text_only [doc]
- Copy buttons — none/url/special/all; account mode needs Premium [doc]
- Hidden-continuation (callback popup) buttons — regex, random press delay range, `body` mode [doc]
- Polls — none/copy/custom link text [doc]
- Stories (Expert) — message/ignore [doc]
- Comments — as posts (forward discussion group) or as comments (channel + group pair, source channel ID) [doc]
- Premium long captions & premium emoji — require account mode + Premium [doc]

## Open questions / ambiguities
- "Protected open" sources supported on all plans except Economy — mechanism for copy-protected channels without account not explained here.
- Disabling path labeled "Copying new" (Копирование новых) — seems to be the section holding the Pause button.
- "Hidden continuation" section says buttons unsupported in account mode, while Copy buttons section says link buttons work with Premium — likely specific to notification buttons.
