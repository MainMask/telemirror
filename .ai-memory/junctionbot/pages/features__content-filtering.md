# Content Filtering (Фильтрация контента)
- Source: https://www.junctionbot.io/ru/features/content-filtering
- EN: https://www.junctionbot.io/features/content-filtering
- Fetched: 2026-11-19, method: curl+html2md
- HTML <title>: "Умные фильтры Telegram: настраиваемые правила для ленты" (Smart Telegram filters: configurable rules for the feed)

## Content
Page navigation: previous feature "History copying" (Копирование истории) → /ru/features/history-copying; next feature "Text modification" (Модификация текста) → /ru/features/text-modification.

# Content Filtering

Guided by the criteria you set, the bot **automatically picks out only the content you need** from the stream of posts. That can be posts mentioning **specific words**, or simply posts on a **specific topic**, posts from certain **authors** only, or just **getting rid of ads**.

You choose whether to use **precise configuration** with **keywords** or to rely on neural networks (link: /ru/documentation/filters#ai-filtering).

Deferred filters (Отложенные фильтры) (link: /ru/documentation/filters#conditional-filter) help select only posts that have gathered a certain number of views, reactions, comments, etc.

#### YOU
- **Create** a forwarding from a source to a feed
- **Define** the selection or blocking criteria

#### THE BOT
- **Tracks** new publications in the source
- **Forwards** only those that satisfy the specified conditions

[Image: "Content filtering"]

Use Junction Bot filters to build topical feeds, monitor mentions and protect against information noise.

Button: "Try it" (Попробовать) → https://t.me/junction_bot?start=docs-features-hero

## What functionality? (Какой функционал?)

### AI filters (ИИ-фильтры)
Use a neural network for filtering.

### Reaction count (Число реакций)
Filtering by number of comments, views, etc.

### Keywords (Ключевые слова)
Find the posts you need by text match.

### Regular expressions (Регулярные выражения)
An advanced tool for filtering by pattern.

### Author (Автор)
Read messages only from the authors you are interested in.

### Publication time (Время публикации)
Precisely set the time range for forwarding.

### Media type (Тип медиа)
Select only text, images, video, etc.

Button: "Read the guide" (Читать руководство) → /ru/documentation/filters

## Features mentioned
- Keyword filter — select/block posts by text match [doc: /ru/documentation/filters]
- Regex filter — pattern-based filtering [doc: /ru/documentation/filters]
- AI filtering — neural-network-based (topic/meaning) filtering [doc: /ru/documentation/filters#ai-filtering]
- Deferred / conditional filter — forward only posts that reach a threshold of views, reactions, comments, etc. [doc: /ru/documentation/filters#conditional-filter]
- Author filter — only messages from chosen authors [doc]
- Publication-time filter — time range for forwarding [doc]
- Media-type filter — text/images/video/etc. only [doc]
- Ad removal — filtering out advertising posts [doc]
- Select vs block criteria — filters can be allow (selection) or deny (blocking) [doc]

## Open questions / ambiguities
- How the deferred (engagement-threshold) filter waits for metrics (delay window, re-check interval) is not stated here; see /ru/documentation/filters#conditional-filter.
- "Publication time" — unclear whether it is a time-of-day window or an absolute date range.
- How ad removal is implemented (AI vs. keyword) is not specified.
