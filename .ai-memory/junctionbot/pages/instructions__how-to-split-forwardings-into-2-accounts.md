# How to split forwardings across 2 accounts (Как разделить пересылки на 2 аккаунта)
- Source: https://www.junctionbot.io/ru/instructions/how-to-split-forwardings-into-2-accounts
- EN: https://www.junctionbot.io/instructions/how-to-split-forwardings-into-2-accounts
- Fetched: 2026-11-19, method: curl+html2md

## Content
Tags: Instruction (Инструкция) · Account (Аккаунт)

Steps (screenshots without alt text):

1. Open the chat with Junction Bot and tap **Menu** (Меню).
2. Tap the 3 bars (hamburger) in the top-right corner of the app.
3. Go to the **My account** (Мой аккаунт) section.
4. Tap the "Edit" (Редактирование) icon.
5. Tap **Change number of packages** (Изменить количество пакетов).
6. Increase the number of packages.
7. Tap **Ok**.
8. [payment-related content omitted] (purchase confirmation step).
9. In the **My account** section you see that 2 packages are now active.
   - Functional note: each additional direct (account) connection requires an additional package — the number of connectable accounts depends on the number of packages (plan-dependent).
10. Tap the **Connect a new account** (Подключение нового аккаунта) button.
11. A message tells you that next you need to leave the app (mini app) and go **to the chat with Junction Bot**.
12. After a message about activating a direct connection arrives in the chat with Junction Bot, enter the phone number you are going to use for the second direct connection.
13. The connection succeeds.
14. Add the account of the new direct connection to the source chat (it must be a member of the source).
15. Open the chat with Junction Bot and tap **Menu**.
16. Select a forwarding.
17. In the **forwarding settings**, tap the **gear icon** to the right of **From** (Откуда).
18. Tap **Change source** (Изменить источник).
19. Expand the list.
20. Select the new direct connection.

Menu paths: `Menu → ☰ → My account (Мой аккаунт) → Edit → Change number of packages`; `My account → Connect a new account`; `Menu → <forwarding> → From (Откуда) ⚙ → Change source (Изменить источник) → <connection>`.

## Features mentioned
- Multiple direct connections — several Telegram user accounts can be connected to one Junction Bot user [doc]
- Per-forwarding reader account — each forwarding's source is bound to a chosen connection, so load can be split across accounts [doc]
- Account connection via phone number — login flow happens in the bot chat (phone number, then presumably code) [doc]

## Open questions / ambiguities
- Why one would split (rate limits / flood limits / source membership limits per account) is not explained.
- The rest of the login flow after entering the phone number (code, 2FA password) is not shown in text.
