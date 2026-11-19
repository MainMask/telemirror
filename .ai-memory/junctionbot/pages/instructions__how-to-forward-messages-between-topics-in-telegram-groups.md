# How to forward messages between topics in Telegram groups (Как пересылать сообщения между темами в группах Telegram)
- Source: https://www.junctionbot.io/ru/instructions/how-to-forward-messages-between-topics-in-telegram-groups
- EN: https://www.junctionbot.io/instructions/how-to-forward-messages-between-topics-in-telegram-groups
- Fetched: 2026-11-19, method: curl+html2md

## Content
Category tag: Instruction (Инструкция) · Forwarding between group topics (Пересылка между темами группы)

### Prepare the destination group (in Telegram)
(Each step is a screenshot with a caption; screenshots have no alt text.)

1. Choose the **source** — a group with topics from which messages will be forwarded. In the screenshot this is a group named "Test_themes_1".
2. Now create the **destination** — the group where messages will arrive. In the screenshot the group Test_themes_2 is created. Go to the **Manage group** (Управление группой) settings.
3. In the **Group settings** (Настройки группы) section enable the **Topics** (Темы) parameter.
4. Next create the first topic.
5. For example, name the topic topic_1_1 and tap **Create** (Создать).
6. Send any message into the just-created topic to complete its creation.
7. Topic "topic_1_1" is created.
8. Create as many topics as you need in the destination group in the same way. We created 2 topics: topic_1_1 and topic_2_2.

### Create the forwarding in Junction Bot
9. Open the chat with Junction Bot and tap **Menu** (Меню).
10. Tap the **Create forwarding** (Создать пересылку) button.
11. Select the source group — Test_themes_1.
12. Select the destination group — Test_themes_2. In this instruction you don't need to click "Create new chat" (Создать новый чат), because it was created earlier.
13. Next we get to the **Topic mapping** (Сопоставление тем) settings. A default forwarding rule "From all topics to the General topic" (Из всех тем в Общую тему) is already created here; it can be deleted.
14. We see that topics appeared in the source: topic_1, topic_2.
15. We see that topics appeared in the destination: topic_1_1, topic_2_2.
16. Map the topics: topic_1 and topic_1_1.
17. topic_1 and topic_1_1 appeared in the first row. If needed, add other mappings.
18. Note the option "All other topics -> General" (Все остальные темы -> General). Add it in case new topics are created in the source group. Then messages from new topics will be forwarded to General of the destination group.
19. Tap **Next** (Далее).
20. We get to **Main settings** (Основные настройки). Here choose which messages will be forwarded: New messages (Новые сообщения) or old messages (старые сообщения).
21. If you choose to forward **New messages**, tap **Create** (Создать).
22. The forwarding is created.

## Features mentioned
- Topic mapping (Сопоставление тем) — per-forwarding table mapping source topic → destination topic, step in the creation wizard for forum groups [doc]
- Default rule "all topics → General" — auto-created, deletable [doc]
- Fallback "All other topics -> General" — catches topics created later in the source [doc]
- New vs old messages — forwarding type chosen in Main settings [doc]
- Related: copy group topic structure (/ru/instructions/how-to-copy-topic-structure) [doc]

## Open questions / ambiguities
- Whether topics can be mapped many-to-one or one-to-many (beyond the General fallback) is not stated.
- The "old messages" flow is not described here.
