# How to find leads, clients and potential orders (AI) (Как находить лидов, клиентов и потенциальные заказы (AI))
- Source: https://www.junctionbot.io/ru/instructions/how-to-find-leads-clients-and-potential-orders-ai
- EN: https://www.junctionbot.io/instructions/how-to-find-leads-clients-and-potential-orders-ai
- Fetched: 2026-11-19, method: curl+html2md

## Content
Category tag: Instruction (Инструкция) · AI integration (Интеграция с ИИ)

Note: the RU page carries a banner "This is an automatically translated version, so errors are possible".

### Intro
For example, you need to set up the bot so that you receive messages mentioning orders for design, page layout, logos, etc. Main goal: quickly and massively aggregate potential requests from Telegram chats for subsequent processing by the sales department. This instruction will help you set up an effective funnel for collecting potential clients.

### Steps
(Each step is a screenshot with a caption; screenshots have no alt text.)

1. Tap the app menu icon.
2. First create a forwarding by following the instruction: [How to create a forwarding from a public source](/instructions/how-to-forward-from-public-telegram-channel-or-group) or [How to create a forwarding from a private source](/instructions/how-to-forward-from-private-telegram-channel-or-group).
   - Source: the chat **from which** you want to receive leads, clients, orders.
   - Destination: the chat **to which** you want to receive leads, clients, orders.
3. Go to the forwarding settings.
4. To find potential clients we recommend a combination of AI message processing and filtering. First find the settings section "AI processing" (ИИ обработка) ([docs](/documentation/integrations-and-settings)).
5. Choose the ready-made prompt "Potential client detection" (Определение потенциального клиента).
6. You can **Edit** (Редактировать) the prompt for your business.
7. Apply the selected prompt.
8. Find the settings section "Filtering" (Фильтрация).
9. Add a blocking filter by text match on the word "НЕ_ЛИД" ("NOT_LEAD"), which is written in the prompt.
10. Save the filter.
11. Find the setting "Filtering order" (Порядок фильтрации) ([docs](/documentation/filters#filtering-order)).
12. Set the value **after ai**. This way, after AI processing the message will be checked for the word "НЕ_ЛИД". If a match is found, the message is automatically filtered out and is not sent to the destination.
13. Make sure the delivery mode ([docs](/documentation/publishing-and-moderation#publishing-mode)) is **copy_client** or **copy_bot**. This is required so the bot can modify the message text. Done! Smart AI ad filtering is set up. (sic — the page reuses the closing sentence from the ad-removal instruction.)

### Optional: link to the client
So that an active link to the client appears in the message text in the chat receiving the orders, you can add "About source" (Об источнике) information:
1. Link to the original message ([docs](/documentation/message-processing#source-link)) (full)
2. Author ([docs](/documentation/message-processing#author)) (@username/full)

## Features mentioned
- AI processing with preset prompts — per-forwarding "AI processing" section with ready prompts (e.g. "Potential client detection"), editable [doc]
- AI-marker + blocking text filter — AI writes a marker word (НЕ_ЛИД) into non-matching messages; a blocking text-match filter drops them [doc]
- Filtering order "after ai" — filters can run after AI processing instead of before [doc]
- Delivery modes copy_client / copy_bot — required for text modification (forward modes can't change text) [doc]
- Source link (full) — append link to the original message [doc]
- Author attribution (@username/full) — append author of the original message [doc]

## Open questions / ambiguities
- The exact text of the "Potential client detection" prompt is shown only in a screenshot; not available as text.
- Closing sentence says "smart AI ad filtering" — copy-paste from the ad-removal page.
