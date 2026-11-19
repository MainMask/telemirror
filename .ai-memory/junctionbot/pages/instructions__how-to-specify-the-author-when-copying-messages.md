# How to specify the author when copying messages (Как указать автора при копировании сообщений)
- Source: https://www.junctionbot.io/ru/instructions/how-to-specify-the-author-when-copying-messages
- EN: https://www.junctionbot.io/instructions/how-to-specify-the-author-when-copying-messages
- Fetched: 2026-11-19, method: curl+html2md

## Content
Tags: Instruction (Инструкция) · About the source (Об источнике)

Related in-page links: "How to specify the name of the source chat when copying messages" (/ru/instructions/how-to-specify-the-name-of-the-source-chat-when-copying-messages); "How to add a link to the original message when copying messages" (/ru/instructions/how-to-add-a-link-to-the-original-message-when-copying-messages)

Steps (screenshots without alt text):

1. Open the chat with Junction Bot and tap **Menu** (Меню).
2. Select a forwarding.
3. In "Forwarding settings" (Настройки пересылки), scroll down.
4. Find the "Author" (Автор) setting and open it.
5. You need to choose one of the styles for passing the message author's name:
   - **name** — in the destination chat, messages from the source arrive with the author's original name. With "name" enabled, the author's name is added at the beginning of the message; clicking it opens the user's profile.
   - **username** — in the destination chat, messages from the source chat arrive with the author's @username. With "username" enabled, the author's name is added at the beginning of the message; clicking it opens the user's profile.
   - **full** — messages arrive with both the name and the @username. With "full" enabled, the author's name and @username are added at the beginning of the message; clicking them opens the user's profile.
   - **full_except_bot** — messages arrive with both name and @username for all messages except those sent by @junction_bot itself.
   - **none** — all author settings are reset (no author shown).

Menu path: `Menu → <forwarding> → Forwarding settings → Author (Автор) → name | username | full | full_except_bot | none`.

## Features mentioned
- Author attribution — prepend the original sender (hyperlinked to profile) to copied messages; modes name/username/full/full_except_bot/none [doc]

## Open questions / ambiguities
- Exact rendering format (separator, line break, bold) not described in text; shown only in screenshots.
- Behaviour for channel posts (no individual author) or anonymous admins is not stated.
