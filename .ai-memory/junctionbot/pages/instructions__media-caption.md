# How to copy only photo/video without text (or) How to remove all media, keeping only text (Как скопировать только фото/видео без текста (или) Как убрать все медиа, оставив только текст)
- Source: https://www.junctionbot.io/ru/instructions/media-caption
- EN: https://www.junctionbot.io/instructions/media-caption
- Fetched: 2026-11-19, method: curl+html2md

## Content
Tags: Instruction (Инструкция) · Media forwarding (Пересылка медиа)

Related in-page link: "How to filter photo/video (or any other media type)" (/ru/instructions/how-to-filter-any-media)

This instruction helps copy only the text without attachments, or conversely only the media without text. The setting does **not** block messages entirely; it splits the text and attachment into components.

The "Media caption" (Подпись к медиа) setting lets you forward the text part of a message. Note: if you need to **completely** remove messages with video notes (кружки), photos, etc., or, for example, let through only messages with video, use another instruction (/instructions/how-to-filter-any-media).

Steps (screenshots without alt text):

1. Open the chat with Junction Bot and tap **Menu** (Меню).
2. Select a forwarding.

**(A) Keep only text, remove all media (as in the example):**
3. Find the "Media caption" (Подпись к медиа) setting in the "Content" (Контент) section.
4. Select the **text_only** mode — send only the caption, without the picture.
5. Done! Now only the text part of the message will be forwarded to the destination — without the picture or other media.

**(B) More complex example: remove all text from a channel and forward only videos and photos without captions:**
3. First, in the "Media caption" setting choose the **separate** option.
4. Then, in the "Filters" (Фильтры) setting, create allowing (whitelist) text filters `<photo>` and `<video>`. For details see the instruction "Filters by media type" (/instructions/how-to-filter-any-media).
5. Done! Now only photos and videos will be published in your channel.

Menu path: `Menu → <forwarding> → Content (Контент) → Media caption (Подпись к медиа) → text_only | separate | …`; `Menu → <forwarding> → Filters (Фильтры)`.

## Features mentioned
- Media caption mode — controls how captions/media are passed: text_only (drop media, keep caption), separate (send media and text as separate messages), others not listed here [doc]
- Media-type filters — allow/deny filters using pseudo-tokens like `<photo>`, `<video>` in text filters [doc]
- Combining separate + allow filters — yields media-only output by splitting and then filtering out the text-only part [doc]

## Open questions / ambiguities
- Full list of Media caption modes (default value, other options) not given on this page.
- Exact semantics of "separate" inferred (media and text sent as separate messages, so text part can be filtered out).
