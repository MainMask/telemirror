# How to set up manual moderation via your own chat (Как настроить ручную модерацию через свой чат)
- Source: https://www.junctionbot.io/ru/instructions/how-to-set-up-manual-moderation-via-own-chat
- EN: https://www.junctionbot.io/instructions/how-to-set-up-manual-moderation-via-own-chat
- Fetched: 2026-11-19, method: curl+html2md

## Content
Tags: Instruction (Инструкция) · Moderation (Модерация)

Related in-page link: "How to set up manual moderation via @Junction_Review_Bot" (/ru/instructions/how-to-set-up-manual-moderation-via-junction-review-bot)

Steps (each step is accompanied by a screenshot; screenshots have no alt text):

1. Open the chat with Junction Bot and tap **Menu** (Меню).
2. Find the forwarding.
3. You land in the forwarding settings. In the list of all settings, find the "Moderation" (Модерация) function and tap it.
4. Select "On" (Вкл) in the "Moderate messages" (Модерировать сообщения) row. By default, message moderation happens in a private chat with a special bot — @Junction_Review_Bot. But you can also assign a group or channel for moderation by tapping "Select chat" (Выбрать чат).
5. Select a chat created in advance for message moderation (note: the bot must be an administrator in the chat you select) or create a new one right here.
6. The selected moderation chat is now shown on the page. Tap **Save** (Сохранить).
7. Settings are saved.
8. Add @Junction_Review_Bot as an administrator to the moderation chat (in the example: Test_JB3_intermediate).
9. A message is published in the source group (example: Test_JB).
10. The moderation chat (Test_JB3_Intermediate) will appear at the top of the chat list as soon as the first message arrives in it.
11. The message has arrived; now you need to choose "Publish" (Опубликовать) or "Skip" (Пропустить).
12. If you tapped **Publish**, the message will be published in the destination channel.

Menu path: `Menu → <forwarding> → Moderation (Модерация) → Moderate messages: On → Select chat → Save`.

## Features mentioned
- Manual moderation (premoderation) — each source message is held for approval before publishing to the destination [doc]
- Moderation via @Junction_Review_Bot — default: review happens in a private chat with a dedicated review bot [doc]
- Moderation via own chat — a user-chosen group/channel (bot must be admin; @Junction_Review_Bot added as admin) receives messages for review [doc]
- Publish / Skip buttons — per-message moderation decision buttons [doc]

## Open questions / ambiguities
- Page says both "the bot must be an administrator" (likely Junction Bot) and "add @Junction_Review_Bot as administrator"; unclear whether both bots are required as admins.
- Not stated what happens to skipped messages, whether edits are possible before publishing, or whether there is a timeout for unmoderated messages.
