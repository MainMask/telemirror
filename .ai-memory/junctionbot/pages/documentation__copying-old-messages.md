# Copying Chat History (Копирование истории чата)
- Source: https://www.junctionbot.io/ru/documentation/copying-old-messages
- EN: https://www.junctionbot.io/documentation/copying-old-messages
- Fetched: 2026-11-19, method: curl+html2md

## Content

### Copying old messages (Копирование старых сообщений)

*Direct and Expert (Директ и Эксперт).*

With Junction Bot you can copy already published messages from any source your connected account is a member of. You can copy all messages as-is in two clicks, or use settings to filter only the needed ones or modify them.

Note: copied messages are dated at the current moment. Copying a channel's history while preserving the original send dates is technically impossible!

The bot can also export messages not only to another Telegram chat but to Google Drive (/ru/documentation/integrations-and-settings#google-drive): enable the forwarding setting "Scheduling and publishing → Save to Google Drive" («Планирование и публикация → Сохранять на Google Диск») before starting the copy.

[img: Instruction image] Instruction: How to copy old messages from any Telegram chat (/ru/instructions/how-to-copy-old-messages-from-any-telegram-channel-or-group)

### Video lesson (Видеоурок)

[video]

### 1. Copying messages "as is" (Копирование сообщений "как есть")

To copy all old messages "as is", create a new forwarding and in the "Forwarding type" («Тип пересылки») parameter choose **Old messages (history) (Старые сообщения (история))**.

**Where to find:** `Menu → Main functions → Copy chat history → Specify source and destination → Main settings → Forwarding type: Old messages (history)` (Меню → Основные функции → Копировать историю чата → Укажите источник и назначение → Основные настройки → Тип пересылки: Старые сообщения (история))

#### Parameters

**Interval type (Тип интервала)**

- All messages (Все сообщения) — copy all messages.
- Message numbers (Номера сообщений) — specify a range of Telegram message numbers. To find a message's number, look at the link to the message: the number is the last digit(s) in the link. This number usually differs from the message's ordinal position in the source.
- Publication time (Время публикации) — specify a time interval.

**Delivery mode (Режим доставки)**

Defines the publishing method (/ru/documentation/publishing-and-moderation#publishing-mode) for delivered messages.

- If you **copy via the bot**, your account and the bot must be admins in the destination.
- If you **copy or forward via the connected account**, it's enough that the connected account has posting rights in the destination.
- The mode **"Copy via account, on flood — via bot" («Копировать через аккаунт, при флуде - через бота»)** (Expert package only) is useful for sending a large stream of messages. If Telegram's flood protection triggers, the system automatically switches to sending via the bot instead of the account.

### 2. Copying messages with settings applied (Копирование сообщений с применением настроек)

To copy a Telegram channel's history using additional settings, first create a forwarding from the source to the destination, apply the settings, then start copying:

**Step 1.** Create a forwarding from the needed source to the needed destination.

**Step 2.** Apply the settings you need to the created forwarding — filters or replacements, transfer of buttons or polls, and much more.

**Step 3.** Start history copying:

`Menu → My forwardings → Select forwarding → Copy old messages` (Меню → Мои пересылки → Выберите пересылку → Скопировать старые сообщения)

Your configured settings are automatically applied to the copied messages.

### Scripted chat history copying (Копирование истории чата по сценарию)

In this copy mode messages are published **on behalf of the same accounts as in the source chat**, and the pauses between messages are preserved.

This option is great for 🔥"warming up"🔥 groups. E.g. you run online courses professionally and launch a new cohort: you can prepare that cohort's chat in advance by staging a conversation on behalf of several users.

To create such an imitation of real conversation, first prepare a "script":

- Connect **several Telegram accounts** to the bot. 🤖
- Create a **new group** 💬 in Telegram and add your connected accounts to it.
- Create a conversation between them, **imitating natural dialogue between users. The script is ready!** Now you can replay the conversation from this group, with the dialogue already acted out "by roles", in any other chat.

**Then do the following:**

- Create or choose the group your users will join and where you want to play the script (the warm-up group).
- Add all previously connected accounts (the script's actors) to this group. Make sure they have posting rights there.
- Create a new forwarding in Junction Bot:
  - Source: the script group.
  - Destination: the warm-up group.
  - On the Main settings (Основные настройки) screen:
    - Forwarding type — Old messages (history).
    - Interval type — All messages,
    - tick "Copy by script" («Копировать по сценарию»),
    - press **"Start copying" («Начать копирование»)**.

Done! As a **result**, in the destination chat you'll see the same conversation as in the script group, with **natural pauses** between messages.

## Features mentioned
- History copying (Direct/Expert) — copy existing messages from any chat the connected account is in [doc]
- Copied messages get current date — original dates cannot be preserved [doc]
- Google Drive export — "Save to Google Drive" setting before starting copy [doc]
- Interval type — all messages / message ID range / publication time range [doc]
- Delivery mode for history — via bot (bot+user admins), via account (posting rights), "account with bot fallback on flood" (Expert) [doc]
- History copy with forwarding settings — create forwarding, configure filters/replacements/etc., then "Copy old messages" [doc]
- Topic-specific history copy (referenced from forwarding page) [doc]
- Scripted copy ("Copy by script") — replay a conversation with each message posted by the matching connected account, preserving inter-message pauses; for group warm-up [doc]

## Open questions / ambiguities
- Speed / rate of history copying and any max message count are not stated.
- Whether scripted copy requires every original author to be a connected account (implied, not stated explicitly).
