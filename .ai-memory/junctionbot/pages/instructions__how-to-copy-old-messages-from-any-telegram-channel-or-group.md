# How to copy old messages of a Telegram chat (Как скопировать старые сообщения чата Telegram)
- Source: https://www.junctionbot.io/ru/instructions/how-to-copy-old-messages-from-any-telegram-channel-or-group
- EN: https://www.junctionbot.io/instructions/how-to-copy-old-messages-from-any-telegram-channel-or-group
- Fetched: 2026-11-19, method: curl+html2md

## Content
Category: Instruction — Copying old messages (history) (Копирование старых сообщений (истории))

(The RU page carries a banner: "This is an automatically translated version, so errors are possible".)

Below you will find a step-by-step guide on how to copy a chat in Telegram.

We also have a video guide: [video] (https://vimeo.com/1155002151?share=copy&fl=sv&fe=ci).

1. Open the chat with Junction Bot and tap **Menu** (**Меню**).
2. Tap the **Create forwarding** (**Создать пересылку**) button.
3. Select the **source** from the list — where messages will be sent from.
4. Select the **destination** from the list — where messages will be sent to.
5. In the forwarding's "Main settings" ("Основные настройки"), choose what you want to copy: old messages (history) (старые сообщения (история)).

### Interval type
- If you choose the interval type **All messages** (**Все сообщения**), copying of all messages will start.
- If you choose the interval type "Message numbers" ("Номера сообщений"), only messages whose ID numbers fall within the interval you specify will be copied.
  - To find a message's ID number, right-click the message from which you want to start copying, click "Copy message link" ("Копировать ссылку на сообщение") and paste it into any text editor (e.g. Notepad). Do the same for the message that should be copied last.
  - Look at the first message's link: `https://t.me/c/2301153917/38`, where "38" is its ID number. Look at the last message's link: `https://t.me/c/2301153917/271`, "271" is its ID number. Add both message numbers to the interval.
- You can also set the message publication time as the interval.

### Remove safe pause
Enabling the option "Remove safe pause" ("Убрать безопасную паузу") lets you forward much faster than Telegram allows, but this risks a temporary ban on posting. It is better to enable this option if you need to copy just a few messages, or when using the delivery mode "Copy via account" (Копировать через аккаунт), with fallback to the bot on flood (при флуде — через бот). (Link: https://www.junctionbot.io/ru/documentation/publishing-and-moderation#publishing-mode)

### Error handling
This option is provided for the case of problems during copying:
- "Ask" ("Спросить") — the bot will ask you what to do with the error.
- "Skip message" ("Пропустить сообщение") — skip the message with the error.
- "Wait and retry" ("Подождать и повторить попытку") — wait until the message is copied completely without an error.

### Sender
Next you need to choose on whose behalf the messages will arrive — on behalf of the bot or on behalf of your account.

### Start
- Click "Let's go" ("Поехали"), after which history copying will start.
- In the chat with the bot we see that history copying has started. `1439554476` is the ID of the source chat.

(Screenshots have no alt text.)

## Features mentioned
- History copy (old messages) — a forwarding mode in Main settings that copies existing messages instead of/alongside new ones [doc]
- Interval: All messages / Message numbers (ID range from t.me links) / publication time range [doc]
- Remove safe pause — disables throttling for speed at risk of temporary Telegram posting ban [doc]
- Delivery mode "Copy via account, on flood via bot" — fallback publishing mode [doc]
- Error handling policy during history copy — Ask / Skip message / Wait and retry [doc]
- Sender choice — post as bot or as connected user account [doc]
- Progress notification in bot chat when history copy starts (shows source chat ID) [doc]

## Open questions / ambiguities
- Format for the time-based interval (dates/times input) is only in screenshots.
- The "few messages" recommendation for Remove safe pause is a translation of "несколько сообщений" — could mean "a few"; the meaning is that it's safe only for small volumes.
- Whether history copy can be combined with new-message forwarding in the same forwarding is not stated here.
