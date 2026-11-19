# How to forward messages from several group topics to the General topic (Как пересылать сообщения из нескольких тем группы в тему General)
- Source: https://www.junctionbot.io/ru/instructions/how-to-forward-messages-from-several-topics-to-general-topic
- EN: https://www.junctionbot.io/instructions/how-to-forward-messages-from-several-topics-to-general-topic
- Fetched: 2026-11-19, method: curl+html2md

## Content
Category tag: Instruction (Инструкция) · Forwarding between group topics (Пересылка между темами группы)

### Steps
(Each step is a screenshot with a caption; screenshots have no alt text.)

1. Choose the **source** — a group with topics from which messages will be forwarded. In the screenshot this is a group named "Test_themes_1".
2. Now create the **destination** — the group where messages will arrive. In the screenshot the group Test_themes_2 is created. Go to the **Manage group** (Управление группой) settings.
3. In the **Group settings** (Настройки группы) section enable the **Topics** (Темы) parameter.
4. Open the chat with Junction Bot and tap **Menu** (Меню).
5. Tap the **Create forwarding** (Создать пересылку) button.
6. Select the source group — Test_themes_1.
7. Select the destination group — Test_themes_2. In this instruction you don't need to click "Create new chat" (Создать новый чат), because it was created earlier.
8. Next we get to the **Topic mapping** (Сопоставление тем) settings. A default forwarding rule is already created here — messages of all topics of group Test_themes_1 will be forwarded to the General topic of group Test_themes_2. Tap **Next** (Далее).
9. We get to **Main settings** (Основные настройки). Here choose which messages will be forwarded: New messages (Новые сообщения) or old messages (старые сообщения).
10. If you choose to forward **New messages**, tap **Create** (Создать).
11. The forwarding is created.

## Features mentioned
- Topic mapping default rule — all source topics → destination General, created automatically, no extra config [doc]
- Forum destination requires Topics enabled in Telegram group settings [doc]
- New vs old messages — forwarding type in Main settings [doc]

## Open questions / ambiguities
- Whether the destination must have Topics enabled at all for "all → General" (General exists only in forum groups) — page implies yes.
