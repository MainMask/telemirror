# How to forward messages from a public Telegram channel or group (Как пересылать сообщения из открытого канала или группы Telegram)
- Source: https://www.junctionbot.io/ru/instructions/how-to-forward-from-public-telegram-channel-or-group
- EN: https://www.junctionbot.io/instructions/how-to-forward-from-public-telegram-channel-or-group
- Fetched: 2026-11-19, method: curl+html2md

## Content
Category tag: Instruction (Инструкция) · Creating a new forwarding (Создание новой пересылки)

### Steps
(Each step is a screenshot with a caption; screenshots have no alt text.)

1. Open the chat with Junction Bot and tap **Menu** (Меню).
2. Tap the **Create forwarding** (Создать пересылку) button.
3. Specify the source — where messages will be sent from. To do this, enter a public link or an invite link to the channel or group into the search field. Tap **Find channel in Telegram** (Найти канал в Telegram). If the source has no link, you will need to connect an account ([docs](/documentation/getting-started#direct-connection)).
4. The bot shows the search result — the name of the channel (group). Click it.
5. Specify the destination — where messages will be sent to: just like the source, enter the link or name of the destination channel/group. In the example above we enter the channel's @username. Tap **Find channel in Telegram**.
6. The bot shows the search result — the name of the channel (group). Click it.
7. (optional) If you don't have a destination chat yet, tap **Create new chat** (Создать новый чат). Enter its name and type: channel or group, and tap **OK**.
8. On the **Main settings** (Основные настройки) screen choose forwarding type **New messages** (Новые сообщения).
9. Next choose on whose behalf messages will arrive (on behalf of the bot or of the connected account) by specifying the delivery mode ([docs](/documentation/publishing-and-moderation#publishing-mode)) — copy or forward.
10. Option **Replace links to the source** (Заменять ссылки на источник) — the automatic link replacement system ([docs](/documentation/message-processing#links-auto-replacement)) (available only on the **Expert** (Эксперт) plan).
11. Tap the **Create** (Создать) button.

## Features mentioned
- Source lookup by link — public link, invite link or @username, button "Find channel in Telegram" [doc]
- Linkless sources require connected account — otherwise only linkable sources work [doc]
- Create new destination chat from the wizard — name + type (channel/group) [doc]
- Forwarding type "New messages" [doc]
- Delivery mode — copy vs forward, bot or connected account [doc]
- Replace links to the source — Expert-plan only [doc]

## Open questions / ambiguities
- Without a connected account, how the bot reads a public source (bot membership vs. service account) is not explained.
