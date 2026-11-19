# Working with Topics (Работа с темами)
- Source: https://www.junctionbot.io/ru/features/topic-mapping
- EN: https://www.junctionbot.io/features/topic-mapping
- Fetched: 2026-11-19, method: curl+html2md
- HTML <title>: "Telegram темы: автоматическая маршрутизация обсуждений" (Telegram topics: automatic routing of discussions)

## Content
Page navigation: previous feature "Manual moderation" (Ручная модерация) → /ru/features/manual-moderation; next feature "Forwarding from folders" (Пересылка из папок) → /ru/features/folders-forwarding.

# Working with Topics

## Use Junction Bot to automate forwarding messages between Telegram groups

**Topics in Telegram groups help organize communication by providing separate spaces for discussions.** However, maintaining such order manually can be difficult and time-consuming, especially when messages need to be forwarded between topics of different groups.

**Junction Bot solves this problem by providing topic mapping (маппинг тем) when forwarding messages. You can define a correspondence between source and destination topics, or reproduce the topic structure of the source group in the destination group.**

#### YOU
- **Choose** the source group
- **Create topics** manually, or copy the source group's structure with the bot
- **Configure** topic mapping in the groups
- **Configure** filtering and other parameters

#### THE BOT
- **Creates** analogous groups [sic — likely "topics"] in the destination (optional)
- **Tracks** new messages in the specified group
- **Uses** the topic mapping to match source and destination topics
- **Forwards** messages to the corresponding topics of the destination group

[Image: "Working with topics"]

Topic management is a feature that automates forwarding messages between topics in Telegram groups.

Button: "Try it" (Попробовать) → https://t.me/junction_bot?start=docs-features-hero

## What functionality? (Какой функционал?)

### TOPIC MATCHING (СОПОСТАВЛЕНИЕ ТОПИКОВ)
Configure the correspondence between topics in groups.

### TOPIC CLONING (КЛОНИРОВАНИЕ ТОПИКОВ)
Reproduce the structure of the source topics in the destination group.

Button: "Read the guide" (Читать руководство) → /ru/documentation/forwarding#topic-mapping

## Features mentioned
- Topic mapping — source topic → destination topic correspondence for forum groups [doc: /ru/documentation/forwarding#topic-mapping]
- Topic cloning — bot recreates source topic structure in destination (optional) [doc]
- Manual topic creation alternative [doc]
- Filters apply to topic forwardings [doc]

## Open questions / ambiguities
- Page says the bot "creates analogous groups" in the destination; context suggests topics, not groups.
- Behavior for unmapped topics (drop vs. General topic) is not stated.
- Whether newly created source topics are cloned automatically later is not stated.
