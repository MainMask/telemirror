# How to set up manual moderation via @Junction_Review_Bot (Как настроить ручную модерацию через @Junction_Review_Bot)
- Source: https://www.junctionbot.io/ru/instructions/how-to-set-up-manual-moderation-via-junction-review-bot
- EN: https://www.junctionbot.io/instructions/how-to-set-up-manual-moderation-via-junction-review-bot
- Fetched: 2026-11-19, method: curl+html2md

## Content
Category tag: Instruction (Инструкция) · Moderation (Модерация)

### Steps
(Each step is a screenshot with a caption; screenshots have no alt text.)

1. Open the chat with Junction Bot and tap **Menu** (Меню).
2. Find the forwarding.
3. We get to the forwarding settings. In the list of all settings choose the **Moderation** (Модерация) function.
4. Select "On" (Вкл) in the row "Moderate messages" (Модерировать сообщения). By default message moderation happens in a private chat with a special bot — @Junction_Review_Bot (alternatively you can choose your own chat: [instruction](/instructions/how-to-set-up-manual-moderation-via-own-chat)).
5. Let's publish a message in the source group Test_JB.
6. The moderation chat Reviews appears at the top of the list of all chats as soon as the first message arrives in it.
7. Messages arrived in the moderation chat Reviews. Now you need to choose "Publish" (Опубликовать) or "Skip" (Пропустить).
8. If you tapped **Publish**, the message is published in the destination channel.

## Features mentioned
- Manual moderation (premoderation) — per-forwarding toggle "Moderate messages" [doc]
- @Junction_Review_Bot — default separate review bot; messages to approve arrive in a private chat with it [doc]
- Publish / Skip buttons — per-message approve or reject [doc]
- Moderation in own chat — alternative review destination (/instructions/how-to-set-up-manual-moderation-via-own-chat) [doc]

## Open questions / ambiguities
- Whether messages can be edited before publishing, and what happens to unreviewed messages (timeouts), is not described.
- The chat is called "Reviews" in screenshots — presumably the review bot's display name.
