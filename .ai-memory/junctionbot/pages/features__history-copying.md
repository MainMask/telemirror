# History Copying (Копирование истории)
- Source: https://www.junctionbot.io/ru/features/history-copying
- EN: https://www.junctionbot.io/features/history-copying
- Fetched: 2026-11-19, method: curl+html2md
- HTML <title>: "Экспорт Telegram чата: полный архив и резервная копия" (Telegram chat export: full archive and backup)

## Content
Page navigation: previous feature "Account connection" (Подключение аккаунта) → /ru/features/account-connection; next feature "Content filtering" (Фильтрация контента) → /ru/features/content-filtering.

# History Copying

## Use Junction Bot's message history copying feature for convenient content transfer and creating backups

**Telegram offers a built-in tool for exporting history**, letting you save a conversation history or a channel's contents. **This function saves content as separate files on your computer, not letting you keep them in the messenger's cloud.** This is inconvenient if you need to move content from one channel to another or save important messages right inside Telegram. Besides, sometimes there is a need to copy important information from a bot or a closed chat.

**Junction Bot solves this task by automatically copying the entire message history from any source in Telegram to your channel or chat.**

#### YOU
- **choose** the copy source
- **define** the needed range of messages
- **configure** filters and other parameters

#### THE BOT
- **copies old messages** in the background

[Image: "History copying"]

History copying lets you transfer all or part of the messages from one Telegram chat to another, fully preserving their original appearance and order.

Button: "Try it" (Попробовать) → https://t.me/junction_bot?start=docs-features-hero

## What functionality? (Какой функционал?)

### TIME RANGE (ВРЕМЕННОЙ ДИАПАЗОН)
Choose any time period for copying.

### CONTENT FILTERING (ФИЛЬТРАЦИЯ КОНТЕНТА)
Screen out messages by author, keywords and content type.

### MEDIA (МЕДИА)
Save media of all types and sizes.

### CLOSED CHANNELS (ЗАКРЫТЫЕ КАНАЛЫ)
Copy from channels with forwarding prohibited.

Button: "Read the guide" (Читать руководство) → /ru/documentation/forwarding#copy-history

## Features mentioned
- History copy — background copy of old messages from any source to a channel/chat [doc: /ru/documentation/forwarding#copy-history]
- Message range / time range — copy all or part of history; any time period [doc]
- Order & appearance preserved — original look and order kept [doc]
- Filters during history copy — author, keywords, content type [doc: /ru/documentation/filters]
- All media types and sizes [doc]
- Protected-content sources — copy from channels with forwarding restricted [doc]
- Sources incl. bots and closed chats [doc]

## Open questions / ambiguities
- "Range of messages" vs. "time range": unclear whether ranges can be set by message ID/count as well as by date.
- "All sizes" of media — no explicit file-size limit stated; may depend on account (Telegram Premium) or plan.
- Copy speed / rate limits not mentioned.
