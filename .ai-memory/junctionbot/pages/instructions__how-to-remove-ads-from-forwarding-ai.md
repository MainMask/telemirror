# How to remove ads from a forwarding (AI) (Как удалить рекламу из пересылки (AI))
- Source: https://www.junctionbot.io/ru/instructions/how-to-remove-ads-from-forwarding-ai
- EN: https://www.junctionbot.io/instructions/how-to-remove-ads-from-forwarding-ai
- Fetched: 2026-11-19, method: curl+html2md

## Content
Category tag: Instruction (Инструкция) · AI integration (Интеграция с ИИ)

### Steps
(Each step is a screenshot with a caption; screenshots have no alt text.)

1. Open the chat with Junction Bot and tap **Menu** (Меню).
2. Select the forwarding.
3. To remove ads we recommend a combination of AI message processing and filtering. First find the settings section "AI processing" (ИИ обработка) ([docs](/documentation/integrations-and-settings)).
4. Choose the ready-made prompt "Ad check" (Проверка на рекламу).
5. Apply the selected prompt.
6. Find the settings section "Filtering" (Фильтрация).
7. Add a blocking filter by text match ([docs](/documentation/filters#text-filters)) on the word РЕКЛАМА ("AD"), which is written in the prompt.
8. Save the filter.
9. Find the setting "Filtering order" (Порядок фильтрации) ([docs](/documentation/filters#filtering-order)).
10. Set the value **after ai**. This way, after AI processing the message will be checked for the word РЕКЛАМА. If a match is found, the message is automatically filtered out and is not sent to the destination.
11. Make sure the delivery mode ([docs](/documentation/publishing-and-moderation#publishing-mode)) is **copy_client** or **copy_bot**. This is required so the bot can modify the message text. Done! Smart AI ad filtering is set up.

## Features mentioned
- AI processing preset "Ad check" — ready-made prompt that marks ad posts with the word РЕКЛАМА [doc]
- Blocking text-match filter — drops messages containing a given word [doc]
- Filtering order "after ai" — filters evaluated on AI-processed text [doc]
- Delivery modes copy_client / copy_bot — required for AI text modification [doc]

## Open questions / ambiguities
- The exact "Ad check" prompt text is only in a screenshot.
- Unclear whether the AI marks only ads (and passes others unchanged) or rewrites all messages.
