# How to forward messages from a private Telegram channel or group (Как пересылать сообщения из закрытого канала или группы Telegram)
- Source: https://www.junctionbot.io/ru/instructions/how-to-forward-from-private-telegram-channel-or-group
- EN: https://www.junctionbot.io/instructions/how-to-forward-from-private-telegram-channel-or-group
- Fetched: 2026-11-19, method: curl+html2md

## Content
Category tag: Instruction (Инструкция) · Creating a new forwarding (Создание новой пересылки)

This instruction is for users with a connected account ([docs](/documentation/getting-started#direct-connection)) (plans **Direct** (Директ) and **Expert** (Эксперт) — i.e. account connection is plan-dependent).

If you work without a connected account, see:
- Instruction "[How to create a forwarding from a public channel or group](/ru/instructions/how-to-forward-from-public-telegram-channel-or-group)"

### Steps
(Each step is a screenshot with a caption; screenshots have no alt text.)

1. Open the chat with Junction Bot and tap **Menu** (Меню).
2. Tap the **Create forwarding** (Создать пересылку) button.
3. Select the source from the list — where messages will be sent from. If the source isn't in the list, try pinning it in your chat list first and then repeat the search.
4. Select the destination from the list — where messages will be sent to.
5. (optional) If you don't have a destination chat yet, tap **Create new chat** (Создать новый чат). Enter its name and type: channel or group, and tap **OK**.
6. On the **Main settings** (Основные настройки) screen choose forwarding type **New messages** (Новые сообщения).
7. Next choose on whose behalf messages will arrive (on behalf of the bot or of the connected account) by specifying the delivery mode ([docs](/documentation/publishing-and-moderation#publishing-mode)) — copy or forward.
8. Option **Replace links to the source** (Заменять ссылки на источник) — the automatic link replacement system ([docs](/documentation/message-processing#links-auto-replacement)) (available only on the **Expert** plan).
9. There are several variants of this option. (Variants shown only in screenshot.)
10. Tap the **Create** (Создать) button.

### Troubleshooting (Устранение неполадок)
While creating a forwarding you may encounter the following errors:
1. After creating a new destination chat, you must make the bot an administrator of that destination.
2. For this reason a message appears informing about this necessity.
3. When you scroll down this message disappears. Then tap **Create**.
4. Junction Bot again informs you that you need to make the bot an administrator.
5. You need to choose one of the options. (Options shown only in screenshot.)
6. The forwarding is created.

## Features mentioned
- Connected-account (direct) mode — user account (userbot) connection allows choosing private sources from own chat list; plan-dependent (Direct/Expert) [doc]
- Source/destination picker from own chats — pin a chat to make it appear in the list [doc]
- Create new destination chat from the wizard — name + type (channel/group) [doc]
- Forwarding type "New messages" — vs. old/history messages [doc]
- Delivery mode — copy vs forward, on behalf of bot or connected account [doc]
- Replace links to the source — automatic link replacement, several variants, Expert-only [doc]
- Bot-admin requirement warning — wizard warns when bot isn't admin in the new destination [doc]

## Open questions / ambiguities
- The "several variants" of link replacement and the troubleshooting options are only in screenshots.
