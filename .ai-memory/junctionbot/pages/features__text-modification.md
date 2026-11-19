# Text Modification (Модификация текста)
- Source: https://www.junctionbot.io/ru/features/text-modification
- EN: https://www.junctionbot.io/features/text-modification
- Fetched: 2026-11-19, method: curl+html2md
- HTML <title>: "Авторедактирование Telegram: форматирование и замены" (Telegram auto-editing: formatting and replacements)

## Content
Page navigation: previous feature "Content filtering" (Фильтрация контента) → /ru/features/content-filtering; next feature "GPT processing" (GPT обработка) → /ru/features/gpt-processing.

# Text Modification

## Use Junction Bot to automatically edit messages in Telegram

**Telegram offers a decent set of tools for styling posts**, including link previews, URL buttons, formatting and animated emoji. A recognizable visual style of publications is an important method of promoting a channel in Telegram, increasing the number of reposts and conversion.

**However, when posts from different channels meet in one feed, stylistic inconsistency can reduce its readability.** And sometimes, out of the whole message, we are interested only in certain fragments. With a large amount of incoming content, manual editing can become tedious.

**Junction Bot solves this problem by offering convenient tools for automatic message modification.**

#### YOU
- **specify** a part of the text **to replace** and the new value to put in its place
- **configure** the display of source information
- **add watermarks** to overlay on images

#### THE BOT
- **searches** for the specified text fragments **by exact match** or **regular expression**
- **replaces** them with the values you specified
- **supplements** the message with information about the author and source
- **overlays watermarks**

[Image: "Text modification"]

Message modification is the automatic changing and supplementing of text and media attachments using auto-replace rules and other settings.

Button: "Try it" (Попробовать) → https://t.me/junction_bot?start=docs-features-hero

## What functionality? (Какой функционал?)

### TEXT EDITING (ПРАВКА ТЕКСТА)
Add your own text before or after the main content.

### AUTO-REPLACEMENTS (АВТО-ЗАМЕНЫ)
Use keywords and regular expressions for automatic text replacement.

### FORMATTING (ФОРМАТИРОВАНИЕ)
Style text using HTML tags.

### HEADERS AND CAPTIONS (ЗАГОЛОВКИ И ПОДПИСИ)
Add and change headers and captions of messages.

### LINKS AND BUTTONS (ССЫЛКИ И КНОПКИ)
Transform links and add buttons.

### WATERMARKS (ВАТЕРМАРКИ)
Protect copyright with watermarks.

Button: "Read the guide" (Читать руководство) → /ru/documentation/message-processing

## Features mentioned
- Prefix/suffix text — add custom text before or after content [doc: /ru/documentation/message-processing]
- Auto-replace rules — exact-match or regex find/replace [doc]
- HTML formatting of added/modified text [doc]
- Headers and captions — add/change [doc]
- Source/author attribution — configurable display of source info [doc]
- Link transformation — rewrite links [doc]
- URL buttons — add buttons to messages [doc]
- Watermarks on images (see watermark-overlay page) [doc: /ru/documentation/message-processing#adding-watermarks]

## Open questions / ambiguities
- "Transform links" — unclear whether this means replacing URLs, removing them, or converting to hidden links.
- "Headers" (заголовки) vs. "captions" (подписи) distinction is not explained; may mean header/footer text vs. media captions.
- Whether replacement can delete text (empty value) is implied but not stated.
