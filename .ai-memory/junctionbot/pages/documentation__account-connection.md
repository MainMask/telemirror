# Account Connection (Подключение аккаунта)
- Source: https://www.junctionbot.io/ru/documentation/account-connection
- EN: https://www.junctionbot.io/documentation/account-connection
- Fetched: 2026-11-19, method: curl+html2md

## Content

*Available on: Direct and Expert (Директ и Эксперт).*

With account connection you can copy messages from **any** Telegram chat you are a member of, including **personal** and **protected (copy-restricted) chats**.

This works by connecting @junction_bot to your account as a separate Telegram client.

### How it works (Как это работает)

- The bot "sees" and forwards messages that are **visible to your account**.
- Access rights are granted **only to the bot**, not to any of the staff.
- The bot works within Telegram's **official secure** protocol.
- You can use a **work** or **secondary** number — just make sure it's the number linked to Telegram.

For details on how account connection works, see the article: Privacy and security in Junction Bot: How account connection works (/ru/articles/privacy-and-security-in-junction-bot-how-account-connection-works).

### How to connect an account (Как подключить аккаунт)

- Get a package with account connection (Direct and above). [payment-related content omitted]
- When creating a new forwarding or digest you will see an option to set up connection of a new account.
- Enter the phone number of the Telegram account you want to connect.
- Enter the 5-digit code that arrives in the official Telegram chat. Why is this safe? (/ru/articles/privacy-and-security-in-junction-bot-how-account-connection-works)
- Done — your account is connected. You will now see the list of chats you participate in among the available sources and destinations of your digests and forwardings.

### Junction Bot Alerts

Currently all system notifications (including billing reminders) arrive in the main chat with the bot. So such notifications don't get lost, it is recommended to add the Junction Bot Alerts bot (https://t.me/junction_ctrl_bot) and **enable notifications** in it.

### Important nuances (Важные нюансы)

- The connected account is not necessarily the account from which you pay for and manage the bot (the *managing account* (управляющий аккаунт)). The connected account can be, for example, your **second account**, e.g. a **work** one.
- You can use many connected numbers but manage them from one managing account. [payment-related content omitted]
- **Do not delete** the channel **"Junction Bot Service Channel"** created by the bot. It is needed for service messages. You can **archive** it so it doesn't get in the way.
- **Do not block** and **do not delete the chat** with @junction_bot from the connected account. This will cause some messages to fail to be forwarded.
- If a connected account stopped working (e.g. the number became inactive), open **Menu → Personal account (Меню → Личный кабинет)** and press **"Reconnect" («Переподключить»)** next to the phone number.

## Features mentioned
- Account connection (userbot) — bot logs in as a separate Telegram client on the user's account to read any chat it can see, incl. personal and copy-protected chats [doc]
- Login flow — phone number + 5-digit code from official Telegram chat; offered inline when creating a forwarding/digest [doc]
- Connected chats appear as sources and destinations for forwardings and digests [doc]
- Managing account vs connected accounts — one managing account, many connected numbers [doc]
- Junction Bot Alerts bot (@junction_ctrl_bot) — separate channel for system notifications [doc]
- Junction Bot Service Channel — auto-created service channel on connected account; must not be deleted (archive OK) [doc]
- Reconnect — Menu → Personal account → "Reconnect" next to phone number for a dead session [doc]

## Open questions / ambiguities
- What the Service Channel is used for exactly ("service messages") is not specified.
- Whether connected accounts can also be used as senders is not stated here (covered elsewhere: Delivery mode).
