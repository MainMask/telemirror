# Account connection (Подключение аккаунта)
- Source: https://www.junctionbot.io/ru/features/account-connection
- EN: https://www.junctionbot.io/features/account-connection
- Fetched: 2026-11-19, method: curl+html2md

## Content
Marketing landing page. Navigation: previous feature "Feed aggregation" (Агрегация ленты, /ru/features/feed-aggregation); next feature "History copying" (Копирование истории, /ru/features/history-copying).

### Connect Junction Bot to your account for instant forwarding and copying from any sources in Telegram, including closed channels, bots and even folders

Bots are a key element of the Telegram ecosystem, and their use is not limited to games, utilities and feedback. Under the hood there may be a highly complex system, and the network of interactions can extend far beyond Telegram. Bots are especially useful as assistants to channel and group admins: they accept join requests, moderate comments, publish posts, collect statistics.

**However, bots have a number of serious limitations. They cannot write first, join chats, or publish premium content.** Bots are practically useless for automating processes outside your own channel, such as tracking mentions, competitor analysis and content aggregation.

**Junction Bot erases these boundaries. To do this, it uses the Telegram network connection protocol for third-party clients. Connected in that capacity to a user account, the bot can act on its behalf without revealing its own presence. This enables automatic forwarding and copying of messages from any sources and publishing on behalf of the user.**

#### YOU
- **create an account** or pick an old one
- **subscribe the account** to the sources
- **connect the bot** via the standard authorization procedure
- **set up forwarding** into your chats and channels

#### THE BOT
- **connects to the account** as a Telegram client
- **monitors updates** in the specified sources
- **filters and modifies** posts according to settings
- **publishes new posts** in your chats

[img: Account connection (Подключение аккаунта)]

"Account connection" is a mode in which the bot acts on behalf of your account, thereby bypassing the limitations typical of bots.

### What functionality? (Какой функционал?)
- **FORWARDING WITHOUT DELAYS** — deliver messages without delays
- **ANY SOURCES** — connect any number of channels, groups, chats and bots
- **DELIVERY METHOD** — publish messages on behalf of your account or group
- **FOLDERS WITH CHATS** — forward messages directly from (chat) folders
- **CLOSED CHANNELS AND CHATS** — copy from channels without an invite link

Link: "Read the guide" (Читать руководство) → /ru/documentation/forwarding#destinations

(Blog teaser block and support link dropped as site chrome.)

## Features mentioned
- Account connection (userbot / MTProto client mode) — bot logs in as the user's account and reads sources as a Telegram client [doc]
- Instant forwarding — no-delay delivery when using a connected account [doc]
- Any sources — channels, groups, private chats, bots, unlimited count [doc]
- Publish as your account or group — delivery mode "on behalf of account" [doc]
- Folder sources — use a Telegram chat folder as a source [doc]
- Closed/private channels without invite link — readable as long as the account is a member [doc]

## Open questions / ambiguities
- Number of sources/folders actually depends on plan (see plan table in features__ai-digests.md: folders 5 vs unlimited); this page claims "any number".
