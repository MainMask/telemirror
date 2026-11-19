# How to filter photos/videos (or any other media type) (Как отфильтровать фото/видео (или любой другой тип медиа))
- Source: https://www.junctionbot.io/ru/instructions/how-to-filter-any-media
- EN: https://www.junctionbot.io/instructions/how-to-filter-any-media
- Fetched: 2026-11-19, method: curl+html2md

## Content
Category: Instruction — Forwarding media (Пересылка медиа)

(The RU page carries a banner: "This is an automatically translated version, so errors are possible".)

Here we'll explain how to remove messages with videos, video circles (round video notes) or GIFs from the forwarding, but keep messages with photos.

Note: if you need to remove **ONLY** the picture or video itself but keep their captions, you need a different guide (/instructions/media-caption — "How to copy only photo/video without text (or) How to remove all media, keeping only text").

1. Open the chat with Junction Bot and tap **Menu** (**Меню**).
2. Select a forwarding.
3. Find the option "Filters" ("Фильтры") in the "Filtering" ("Фильтрация") section.
4. Tap **+** to create a new filter. Filter type: "By text match" ("По текстовому совпадению").
5. In the "Value" ("Значение") field specify the required media type:
   - `<photo>` — pictures and photos
   - `<document>` — file attachments
   - `<audio>` — audio and music
   - `<video>` — video
   - `<sticker>` — stickers
   - `<voice>` — voice messages
   - `<location>` — geolocation pins
   - `<animation>` — GIF animation
   - `<videonote>` — video circles (round video notes)
   - `<poll>` — polls
6. If the checkbox is enabled, an allowing filter for messages with pictures will be created (i.e. only messages with photos will arrive in your channel; no other messages will arrive).
7. Save the filter.
8. Done! Now only messages that contain the selected media type — a picture (regardless of whether with text or without) — will be forwarded to the destination. Other media types and plain text messages will be ignored.

Example: several messages with text and media arrived in the source. With the `<photo>` filter only messages with images reached the destination.

### Forbidding a media type
You can also choose media that should **not** be forwarded.
1. Create another text filter and specify the required media type (e.g. `<video>`).
2. Uncheck the checkbox — this will create a forbidding filter for video.
3. Don't forget to save — our forbidding filter for video is ready! Now messages with this media type will not be forwarded.

Example: videos and other media arrived in the source. Only media and text messages without video reach the destination.

Menu path: `Menu (Меню) → <forwarding> → Filtering (Фильтрация) → Filters (Фильтры) → + → By text match (По текстовому совпадению) → Value (Значение)`

(Screenshots have no alt text.)

## Features mentioned
- Text-match filters with media-type tokens — `<photo>`, `<document>`, `<audio>`, `<video>`, `<sticker>`, `<voice>`, `<location>`, `<animation>`, `<videonote>`, `<poll>` [doc]
- Allow vs forbid filter via a checkbox — checked = allowing (mustHave), unchecked = forbidding (mustNotHave) [doc]
- Multiple filters per forwarding [doc]
- Strip media but keep caption — separate feature (media-caption guide) [doc]

## Open questions / ambiguities
- How multiple allowing filters combine (OR vs AND) is not stated.
- Behavior for albums (mixed photo+video groups) is not described.
- The checkbox label text is only in screenshots.
