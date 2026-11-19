# How to add a link to the original message when copying messages (Как указать ссылку на оригинальное сообщение при копировании сообщений)
- Source: https://www.junctionbot.io/ru/instructions/how-to-add-a-link-to-the-original-message-when-copying-messages
- EN: https://www.junctionbot.io/instructions/how-to-add-a-link-to-the-original-message-when-copying-messages
- Fetched: 2026-11-19, method: curl+html2md

## Content
Category: Instruction — About the source (Об источнике)

(The RU page carries a banner: "This is an automatically translated version, so errors are possible".)

1. Open the chat with Junction Bot and tap **Menu** (**Меню**).
2. Select a forwarding.
3. Scroll down and find the option "Link to the original message" ("Ссылка на оригинальное сообщение").
4. Click "**Link to the original message:** none", where "none" is the default value.
5. If you click **full**, the message will arrive with the original link to the message in the source.

Example: some message arrives in the source Test_JB. The same message is forwarded to the destination with a link to it in the source.

You can also hide the link to the source message under some text.
- To do this, enter the text that masks the link in the field "Custom value" ("Произвольное значение").

Example: some message arrives in the source Test_JB. In the destination a link to the original message appeared in the form of the phrase "не ходи сюда" ("don't go here").

The "none" option removes all settings of the link to the original message.

Menu path: `Menu (Меню) → <forwarding> → Link to the original message (Ссылка на оригинальное сообщение): none | full | Custom value (Произвольное значение)`

(Screenshots have no alt text.)

## Features mentioned
- Link to the original message — per-forwarding option appending a link to the source post: `none` (default) / `full` (raw link) / custom text that the link is hidden under [doc]

## Open questions / ambiguities
- Where exactly the link is placed in the copied message (end of text? separate line?) is only shown in screenshots.
- Behavior for private sources (t.me/c/... links) or sources without public links is not described.
