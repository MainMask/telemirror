# How to filter forwarded messages (Как фильтровать пересланные сообщения)
- Source: https://www.junctionbot.io/ru/instructions/how-to-filter-forwarded-messages
- EN: https://www.junctionbot.io/instructions/how-to-filter-forwarded-messages
- Fetched: 2026-11-19, method: curl+html2md

## Content
Category: Instruction — Filtering (Фильтрация)

(The RU page carries a banner: "This is an automatically translated version, so errors are possible".)

1. Open the chat with Junction Bot and tap **Menu** (**Меню**).
2. Select a forwarding.
3. Find the setting "Filter forwards" ("Фильтровать пересылки") in the list and tap it.
4. The initial option "all" sends all types of messages from the source to the destination without filtering.

Example: two messages arrive in the source "Test_JB": the first is a regular one and the second is a forwarded one.
- With the "all" option, all messages were forwarded to the destination "Назад в прерии" ("Back to the prairies"): both the first regular one and the second forwarded one.
- If you click "direct only", only regular messages will be sent to the destination. With the "direct only" option, only the first regular message was forwarded to the destination "Назад в прерии".
- If you click "forward only", only forwarded messages will be sent to the destination. With the "forward only" option, only the second, forwarded message was forwarded to the destination "Назад в прерии".

Menu path: `Menu (Меню) → <forwarding> → Filter forwards (Фильтровать пересылки): all | direct only | forward only`

(Screenshots have no alt text.)

## Features mentioned
- Filter forwards — per-forwarding option: `all` (default) / `direct only` (skip messages that are forwards from elsewhere) / `forward only` (only forwarded messages) [doc]
