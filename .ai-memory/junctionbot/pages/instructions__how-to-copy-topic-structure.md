# How to copy a group's topic structure (Как скопировать структуру тем группы)
- Source: https://www.junctionbot.io/ru/instructions/how-to-copy-topic-structure
- EN: https://www.junctionbot.io/instructions/how-to-copy-topic-structure
- Fetched: 2026-11-19, method: curl+html2md

## Content
Category: Instruction — Forwarding between group topics (Пересылка между темами группы)

(The RU page carries a banner: "This is an automatically translated version, so errors are possible".)

1. Choose the **source** — a group with topics from which messages will be forwarded. In the screenshot this is a group called "Test_themes_1".
2. Now you need to create the **destination** — the group where messages will arrive. In the screenshot a group Test_themes_2 has been created. Go to the **Manage group** (**Управление группой**) settings.
3. In the **Group settings** (**Настройки группы**) section, enable the **Topics** (**Темы**) parameter.
4. Open the chat with Junction Bot and tap **Menu** (**Меню**).
5. Tap the **Create forwarding** (**Создать пересылку**) button.
6. Select the source group — Test_themes_1.
7. Select the destination group — Test_themes_2. In this guide you don't need to click "Create new chat" ("Создать новый чат"), because it was already created earlier.
8. Next you get to the **Topic mapping** (**Сопоставление тем**) settings. A default forwarding rule "From all topics to the General topic" ("Из всех тем в Общую тему") is already created here; it can be deleted.
9. We see that topics have appeared in the source: topic_1, topic_2.
10. We see that the destination has only the General topic, since we have not created our own topics inside this group.
11. For the destination group Test_themes_2 to get the same topic names as the source group (topic_1, topic_2), tap **Copy topic structure** (**Скопировать структуру тем**).
12. Tap the **Let's go** (**Поехали**) button.
13. Note the option "All other topics -> General" ("Все остальные темы -> General"). Add it in case new topics are created in the source group. Then messages from new topics will be forwarded to General of the destination group.
14. Tap **Next** (**Далее**).
15. You get to **Main settings** (**Основные настройки**). Here you need to choose which messages will be forwarded: New messages (Новые сообщения) or old messages (старые сообщения).
16. If you choose to forward **New messages**, tap **Create** (**Создать**).
17. The forwarding has been created.

(Screenshots have no alt text.)

## Features mentioned
- Forum/topic groups as source and destination [doc]
- Topic mapping (Сопоставление тем) — per-forwarding rules mapping source topics to destination topics; default rule "all topics → General" [doc]
- Copy topic structure — bot creates topics in the destination with the same names as in the source and maps them 1:1 [doc]
- "All other topics → General" catch-all rule — routes messages from topics created later [doc]
- "Create new chat" option when picking a destination (bot can create the destination chat) [doc]
- Main settings: New messages vs old messages (history) [doc]

## Open questions / ambiguities
- Whether topics created in the source after the structure copy are auto-mirrored (beyond the catch-all → General rule) is not described — the catch-all suggests they are not.
- Whether topic icons/colors are copied is not stated.
- Which identity (bot or account) needs admin rights to create topics in the destination is not stated.
