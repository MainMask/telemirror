# Feed Aggregation (Агрегация ленты)
- Source: https://www.junctionbot.io/ru/features/feed-aggregation
- EN: https://www.junctionbot.io/features/feed-aggregation
- Fetched: 2026-11-19, method: curl+html2md
- HTML <title>: "Telegram лента: ваш персональный новостной агрегатор" (Telegram feed: your personal news aggregator)

## Content
Page navigation: previous feature "Message forwarding" (Пересылка сообщений) → /ru/features/message-forwarding; next feature "Account connection" (Подключение аккаунта) → /ru/features/account-connection.

# Feed Aggregation

## Use Junction Bot feeds to read news, aggregate digests and monitor mentions in Telegram chats

Paradoxically, one of Telegram's main features is not a feature but its absence. The messenger has no recommendation feed, a basic function of most other social media. **The platform's user chooses content to view following their own preferences, not under the influence of a recommendation algorithm.**

**But as the platform grew, the number of channels and subscriptions increased so much that many readers simply lost the ability to navigate them.** It is getting harder to remember and find a channel; more and more interesting content passes by.

**Junction Bot solves this problem by automatically collecting posts from your sources into a feed, leaving you full control over every stage of the process. You can create any number of feeds.**

#### YOU
- **choose** the content sources
- **create / choose** a channel to publish the feed in, configure its name and picture
- **configure** filters and other parameters

#### THE BOT
- **tracks** updates in the sources
- **screens out** information noise and ads, **selects** what matters to you
- **edits** and formats the text
- **places** posts into the feed

[Image: "Feed aggregation"]

A feed (Лента) is a chat for automatically collecting messages from various sources in Telegram.

Button: "Try it" (Попробовать) → https://t.me/junction_bot?start=docs-features-hero

## What functionality? (Какой функционал?)

### MANY FEEDS (МНОГО ЛЕНТ)
1 / Set up additional feeds
2 / Collect news on different topics

### FILTERS (ФИЛЬТРЫ)
1 / Choose the type: by keyword, author, attachment type and others
2 / Set the filtering criteria
3 / Automatically select interesting content

### CHAT FOLDERS (ПАПКИ С ЧАТАМИ)
1 / In a minute, set up a feed from the posts of all channels in a folder
2 / Manage sources simply by changing the folder's contents

### ACCESS (ДОСТУП)
1 / Build a feed for yourself
2 / Invite friends to read
3 / Make it a public channel

Button: "Read the guide" (Читать руководство) → /ru/documentation/forwarding#destinations

## Features mentioned
- Feeds — a destination chat/channel that aggregates posts from many sources [doc: /ru/documentation/forwarding#destinations]
- Unlimited feeds — "any number of feeds" can be created [doc]
- Feed channel creation by bot — create/choose a channel and set its name and picture [doc]
- Filters — keyword, author, attachment type, etc. [doc: /ru/documentation/filters]
- Noise/ad removal — bot screens out noise and ads [doc]
- Text editing/formatting — bot edits and formats text before posting [doc]
- Folder-based feed — feed built from all channels in a Telegram chat folder; sources follow folder membership [doc: /ru/documentation/forwarding#folders]
- Feed access modes — private, shared with friends, or public channel [doc]

## Open questions / ambiguities
- "Any number of feeds" may in practice be limited by plan (not stated on this page).
- Whether the bot itself creates the feed channel (and sets name/picture) via the user account or the user does it manually is ambiguous ("create / choose").
