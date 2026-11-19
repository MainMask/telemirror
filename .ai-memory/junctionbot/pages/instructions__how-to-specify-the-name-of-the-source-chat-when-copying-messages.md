# How to specify the name of the source chat when copying messages (Как указать название чата-источника при копировании сообщений)
- Source: https://www.junctionbot.io/ru/instructions/how-to-specify-the-name-of-the-source-chat-when-copying-messages
- EN: https://www.junctionbot.io/instructions/how-to-specify-the-name-of-the-source-chat-when-copying-messages
- Fetched: 2026-11-19, method: curl+html2md

## Content
Tags: Instruction (Инструкция) · About the source (Об источнике)

Related in-page links: "How to specify the author when copying messages" (/ru/instructions/how-to-specify-the-author-when-copying-messages); "How to add a link to the original message when copying messages" (/ru/instructions/how-to-add-a-link-to-the-original-message-when-copying-messages)

Steps (screenshots without alt text):

1. Open the chat with Junction Bot and tap **Menu** (Меню).
2. Select a forwarding.
3. Find the setting "Source name: none" (Название источника: none).
4. Options:
   - **bold** — adds the source name. Example: in the destination "Назад в прерии" the source name "Test_JB" appears at the top of the message.
   - **from_only** — messages from the source arrive with the name of the *original* source (only if the message was forwarded into the source from another channel). Example with 3 chats: a message from Test_JB0 is forwarded into Test_JB, and from there into "Назад в прерии". In the final destination "Назад в прерии" the original source name — Test_JB0 — is shown. That is exactly what "from_only" does.
   - **id** — the destination chat shows the id of the message from the source. Example: the message in destination "Назад в прерии" shows the id of the source message from "Test_JB".
   - **date** — messages in the destination arrive with the date. Example: the message in "Назад в прерии" is shown with its publication date in the source "Test_JB".
   - **none** — all source-name settings are reset.

Menu path: `Menu → <forwarding> → Source name (Название источника) → bold | from_only | id | date | none`.

## Features mentioned
- Source name header — prepend source chat title to copied messages (bold style) [doc]
- from_only — show the original "forwarded from" origin only for messages that were themselves forwards [doc]
- Source message id / date stamps — alternative header variants showing source message id or publication date [doc]

## Open questions / ambiguities
- Whether options combine (e.g., name + date) or are mutually exclusive — UI appears to be a single choice.
- Whether the source name is hyperlinked is not stated.
