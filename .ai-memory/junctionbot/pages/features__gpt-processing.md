# GPT Processing (GPT обработка)
- Source: https://www.junctionbot.io/ru/features/gpt-processing
- EN: https://www.junctionbot.io/features/gpt-processing
- Fetched: 2026-11-19, method: curl+html2md
- HTML <title>: "ChatGPT для Telegram: AI-автоматизация контента" (ChatGPT for Telegram: AI content automation)

## Content
Page navigation: previous feature "Text modification" (Модификация текста) → /ru/features/text-modification; next feature "Manual moderation" (Ручная модерация) → /ru/features/manual-moderation.

# GPT Processing

## Use Junction Bot to automatically process messages with ChatGPT

Generative neural networks have become firmly established in the lives of social media specialists. **Their capabilities are impressively broad: summarization, rewriting, sentiment analysis are just a few examples of their application.**

**But manual transfer of materials, prompt configuration and the service being blocked in certain regions can become a significant obstacle** to their everyday use.

**Junction Bot solves these problems thanks to integration with the OpenAI API, which allows automatic processing of all forwarded content.**

#### YOU
- **choose** a suitable way of paying for API calls [payment-related content omitted — the page only says the user picks how API requests are paid for]
- **specify** a suitable ChatGPT model
- **enter the needed prompt** in the forwarding settings

#### THE BOT
- **automatically processes** forwarded messages

[Image: "GPT processing"]

Integration with the OpenAI API makes it possible to process the stream of forwarded messages with the ChatGPT model of your choice.

Button: "Try it" (Попробовать) → https://t.me/junction_bot?start=docs-features-hero

## What functionality? (Какой функционал?)

### TRANSLATION (ПЕРЕВОД)
Translate messages into various languages.

### SUMMARY (РЕЗЮМЕ)
Shorten long messages to key points.

### SMART FILTER (УМНЫЙ ФИЛЬТР)
Select content by meaning, tone and key phrases.

### CONTENT GENERATION (ГЕНЕРАЦИЯ КОНТЕНТА)
Create new texts, headlines and descriptions based on the source message.

### SENTIMENT ANALYSIS (СЕНТИМЕНТ-АНАЛИЗ)
Assess the tone of comments and reviews.

### MODERATION (МОДЕРАЦИЯ)
Check content for prohibited topics, insults and spam.

### AUTO-RESPONDER (АВТО-ОТВЕТЧИК)
Generate automatic replies to questions in a chat.

Button: "Read the guide" (Читать руководство) → /ru/documentation/message-processing#gpt-processing

## Features mentioned
- GPT processing — per-forwarding prompt applied to every forwarded message via OpenAI API [doc: /ru/documentation/message-processing#gpt-processing]
- Model choice — user selects the ChatGPT model [doc]
- Prompt in forwarding settings — prompt configured per forwarding rule [doc]
- AI translation [doc]
- AI summarization [doc]
- AI smart filter — select by meaning/tone/key phrases (overlaps with AI filters) [doc: /ru/documentation/filters#ai-filtering]
- AI content generation — headlines, descriptions, rewrites [doc]
- Sentiment analysis [doc]
- AI moderation — prohibited topics, insults, spam [doc]
- Auto-responder — generated replies to questions in a chat [doc]
- Bypass of regional OpenAI blocking — implied via server-side integration [doc]

## Open questions / ambiguities
- API payment options (own API key vs. paid through the bot) are referenced but omitted as payment-related; whether a user-supplied OpenAI key is supported is a functional question to check in the docs.
- Auto-responder: how replies are posted (as the user account? the bot?) and in which chat is unclear.
- Which models are available is not listed.
