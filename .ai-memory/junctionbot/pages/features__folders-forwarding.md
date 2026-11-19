# Forwarding from Folders (Пересылка из папок)
- Source: https://www.junctionbot.io/ru/features/folders-forwarding
- EN: https://www.junctionbot.io/features/folders-forwarding
- Fetched: 2026-11-19, method: curl+html2md
- HTML <title>: "Telegram папки: автоматизация целых папок" (Telegram folders: automating entire folders)

## Content
Page navigation: previous feature "Working with topics" (Работа с темами) → /ru/features/topic-mapping; next feature "Watermark overlay" (Наложение водяных знаков) → /ru/features/watermark-overlay.

# Forwarding from Folders

## Use Junction Bot to automatically forward messages from chat folders in Telegram

**Folders let you conveniently distribute chats and channels in Telegram by topic and category.** But when we need to see a folder's contents in a single feed, the standard functionality is no longer enough.

**Junction Bot solves this problem by making it possible to forward messages from an entire folder at once.** It greatly simplifies setting up and managing sources in Telegram.

#### YOU
- **Choose** a folder with chats and channels in your account
- **Configure** forwarding parameters, including filters and topic mapping
- **Define** the destination chat or channel for forwarded messages

#### THE BOT
- **Tracks** all messages from the chats and channels in the selected folder
- **Filters** and processes messages according to your settings
- **Automatically forwards** messages to the chat or channel you specified

[Image: "Forwarding from folders"]

With this feature you can choose any folder in your Telegram, and the bot will automatically set up forwarding from all chats and channels contained in it.

Button: "Try it" (Попробовать) → https://t.me/junction_bot?start=docs-features-hero

## What functionality? (Какой функционал?)

### QUICK SETUP (БЫСТРАЯ НАСТРОЙКА)
Set up forwarding from the sources of an entire folder in one click.

### EASY MANAGEMENT (ЛЕГКОЕ УПРАВЛЕНИЕ)
Manage many sources within just one forwarding rule.

Button: "Read the guide" (Читать руководство) → /ru/documentation/forwarding#folders

## Features mentioned
- Folder as source — use a Telegram chat folder of the connected account as a single source [doc: /ru/documentation/forwarding#folders]
- One rule, many sources — all folder chats handled within one forwarding rule [doc]
- Dynamic membership — sources managed by changing folder contents (per feed-aggregation page) [doc]
- Filters and topic mapping apply to folder forwardings [doc]

## Open questions / ambiguities
- Whether changes to folder membership are picked up automatically/live or require re-sync is not stated on this page (feed-aggregation page implies automatic).
- Requires a connected user account (folders are "in your account"); not explicitly said.
