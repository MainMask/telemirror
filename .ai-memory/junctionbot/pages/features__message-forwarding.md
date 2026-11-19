# Message Forwarding (Пересылка сообщений)
- Source: https://www.junctionbot.io/ru/features/message-forwarding
- EN: https://www.junctionbot.io/features/message-forwarding
- Fetched: 2026-11-19, method: curl+html2md
- HTML <title>: "Telegram пересылка: обход ограничений и автоматизация" (Telegram forwarding: bypassing restrictions and automation)

## Content
Page navigation: previous feature "Watermark overlay" (Наложение водяных знаков) → /ru/features/watermark-overlay; next feature "Feed aggregation" (Агрегация ленты) → /ru/features/feed-aggregation.

# Message Forwarding

## Use Junction Bot to automatically forward and copy messages from any chats and channels in Telegram

Telegram stands out with a unique message format common to all chat types. It lets you effortlessly publish content, share interesting posts or save them. **But when the task is regular copying of new messages, the standard functions become insufficient.** Monitoring and manual copying take far too much time and attention.

**Junction Bot solves this task by tracking updates in your sources and automatically forwarding them to your channel, chat or bot.**

#### YOU
- **Choose** the copy source
- **Define** the destination chat
- **Set** filters and other forwarding parameters

#### THE BOT
- **Tracks** the release of new posts in the sources
- **Filters and modifies** messages according to the settings
- **Publishes** in your channel or chat as a repost or a copy

[Image: "Message forwarding"]

The bot can both copy and forward messages using Telegram's built-in mechanism, preserving the author's name and a link to the original.

Any sources are supported.

Button: "Try it" (Попробовать) → https://t.me/junction_bot?start=docs-features-hero

## What functionality? (Какой функционал?)

### ANY SOURCES (ЛЮБЫЕ ИСТОЧНИКИ)
1 / Public, private and closed
2 / Channels, groups and forums
3 / Personal chats and bots
4 / Chat folders

### ALL CONTENT (ВЕСЬ КОНТЕНТ)
1 / Text and emoji, including premium ones
2 / Pictures, GIFs and video
3 / Audio and voice messages
4 / Documents and files
5 / Polls and text from stories

### BYPASSING RESTRICTIONS (ОБХОД ОГРАНИЧЕНИЙ)
Copy messages even from protected sources.

Button: "Read the guide" (Читать руководство) → /ru/documentation/forwarding

## Features mentioned
- Real-time forwarding — track sources and forward new posts automatically [doc: /ru/documentation/forwarding]
- Copy vs. forward (repost) mode — copy, or native Telegram forward preserving author name and link to original [doc]
- Destinations — channel, chat or bot [doc]
- Source types — public/private/closed; channels, groups, forums; personal chats, bots; chat folders [doc]
- Content types — text, premium emoji, images, GIFs, video, audio, voice, documents/files, polls, story text [doc]
- Protected-content bypass — copy from sources with forwarding restricted [doc]
- Filters and modification applied in-flight [doc]

## Open questions / ambiguities
- "Preserving the author's name and a link to the original" — reads as describing the native-forward mode; unclear whether copy mode can also add attribution (see text-modification page: source info).
- "Text from stories" — only text, apparently not story media.
- Forwarding *to a bot* as a destination — mechanism not explained.
