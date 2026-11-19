# How to set up an AI integration (Как настроить ИИ-интеграцию)
- Source: https://www.junctionbot.io/ru/instructions/how-to-setup-an-ai-integration
- EN: https://www.junctionbot.io/instructions/how-to-setup-an-ai-integration
- Fetched: 2026-11-19, method: curl+html2md

## Content
Tags: Instruction (Инструкция) · AI integration (Интеграция с ИИ)

Related in-page links: "How to remove ads from a forwarding (AI)" (/ru/instructions/how-to-remove-ads-from-forwarding-ai); "How to find leads, clients and potential orders (AI)" (/ru/instructions/how-to-find-leads-clients-and-potential-orders-ai)

Steps (each accompanied by a screenshot without alt text):

1. Open the chat with Junction Bot and tap **Menu** (Меню).
2. Select a forwarding.
3. In the forwarding settings, make sure you have selected the correct delivery mode.
   - Note: AI processing is only possible when messages are delivered via the **copy** method (link: /documentation/publishing-and-moderation#publishing-mode). Telegram does not allow modifying forwarded messages, so processing in forward mode is unavailable.
4. In the forwarding settings, scroll down and find the option "AI processing (ChatGPT and others)" (ИИ обработка (ChatGPT и другие)).
5. The AI processing settings have 2 main lists:
   1. **My prompts** (Мои промпты) — a list of all prompts you created or modified yourself.
   2. **Prompt library** (Библиотека промптов) — a collection of ready-made templates for popular tasks.
6. To use one of the ready-made templates from the library, select a specific prompt and tap "Apply" (Применить).
7. If you want to change the suggested options, you can edit the text of a library prompt.
8. After editing the prompt text, don't forget to save the changes.
9. The modified prompt appears as a copy of the system prompt: on **Save** it is added to the "My prompts" section, or it becomes the active prompt if you choose **Save and Apply**.
10. If you need a unique instruction for the AI, you can add your own prompt. To do this, tap "Create prompt" (Создать промпт).
11. An editing screen opens. Fill in the fields. (The fields are only shown in a screenshot; not listed in text.)
    - With a paid subscription (paying from balance or with your own API key) you get access to more than **300 models**. In free mode only **1 model** is available.
12. At the end, don't forget to save the prompt:
    1. **Save and apply** (Сохранить и применить) — the prompt is created and immediately activated for the current forwarding, appearing in the "Active prompt" (Активный промпт) block.
    2. **Save** (Сохранить) — the prompt is simply added to your "My prompts" list, and you can apply it later.
13. The new prompt is now active, i.e. it works right now for this forwarding. If no prompt is applied, this block is hidden.

### AI processing payment/usage modes
We offer several ways to use AI processing so you can choose the one that best fits your tasks. Important: this choice applies to **all your forwardings and other AI services in the bot**, not only the currently selected one.

1. **Free mode**: 10 free processings are provided to get acquainted with the service. This limit renews monthly. In free mode a single default model is used for processing.
2. **Pay from balance**: [payment-related content omitted] — functionally, this mode uses OpenRouter's provider-selection optimization, which automatically picks the best provider by cost and speed for the model you selected. The per-call cost is shown when choosing a model.
3. **Use your own API key**: this mode lets you connect your own API key from one of the providers. Billing is done directly via your provider; Junction Bot does not charge for processing.

Menu path: `Menu → <forwarding> → AI processing (ChatGPT and others) → My prompts | Prompt library | Create prompt → Save / Save and apply`.

## Features mentioned
- AI processing of messages — rewrite/transform copied messages with an LLM prompt; copy mode only [doc]
- Prompt library — ready-made system prompt templates, can be applied or edited (edited copy goes to My prompts) [doc]
- My prompts — user-created/modified prompts, reusable across forwardings [doc]
- Active prompt — one prompt active per forwarding; block hidden when none [doc]
- Model choice — 300+ models (via OpenRouter) on paid/BYO key; 1 default model in free mode [doc]
- Free AI quota — 10 processings/month, renews monthly [doc]
- Bring-your-own API key — direct billing with provider, no Junction Bot fee [doc]
- Global AI usage mode — choice applies to all forwardings and AI services (incl. digests) [doc]

## Open questions / ambiguities
- Fields on the "Create prompt" screen (name, prompt text, model, etc.) are not described in text.
- Which providers are supported for own API key is not stated.
- Unclear what happens to messages when the free quota is exhausted (skipped vs. sent unprocessed).
