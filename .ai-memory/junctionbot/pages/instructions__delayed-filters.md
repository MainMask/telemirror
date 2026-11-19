# How to receive only messages that collected the most reactions (Как получать только сообщения, набравшие максимум реакций)
- Source: https://www.junctionbot.io/ru/instructions/delayed-filters
- EN: https://www.junctionbot.io/instructions/delayed-filters
- Fetched: 2026-11-19, method: curl+html2md

## Content

Type: Instruction (`Инструкция`) · Category: Filtering (`Фильтрация`)

(Banner: machine-translated version, errors possible. "Back to instructions" → /ru/instructions.)

With **delayed filters** (`отложенные фильтры`) you can set up receiving only the most popular messages by number of views, comments, reactions and forwards.

You may also be interested in: [Instruction] [How to replace a word or part of text when copying messages](/ru/instructions/how-to-replace-a-word-or-part-of-text-when-copying-messages)

Steps (each step is accompanied by a screenshot without meaningful alt text):

1. Open the chat with Junction Bot and tap **Menu** (`Меню`).
2. Select the forwarding.
3. Find the setting "Delay and delayed filter" (`“Задержка и отложенный фильтр”`) in the list and tap it.
4. Here you can choose the time range within which a message published in the source will be forwarded to the destination.
5. This option is called "Delayed filter" (`“Отложенный фильтр”`).
6. Choose the minimum of reactions / views / forwards / replies (`реакций/просмотров/пересылок/ответов`) and its value. When the source chat accumulates that minimum, the message is automatically forwarded to the destination chat, respecting the delay configured above.
7. In this instruction we consider the case where messages arrive if they have at least 1 reaction in the source chat.
8. The filter is created. Tap "Save" (`“Сохранить”`).
9. A message is published in the source. A reader puts a reaction.
10. The message was forwarded according to the time range.

You can also forward only messages that generated the **highest audience engagement** — based on the ratio of interactions to views. For example:

- To copy posts with 1 reaction per 10 views (1 / 10) → specify **0.1**
- To copy posts with 50 replies per 1000 views (50 / 1000) → specify **0.05**
- To copy posts with 20 forwards per 100 views (20 / 100) → specify **0.2**

(Page ends with a "was this helpful" feedback widget — omitted.)

## Features mentioned
- Delayed filter — hold a post for a time window and forward only if it reaches a minimum of reactions/views/forwards/replies [doc]
- Delay + delayed filter combined setting ("Задержка и отложенный фильтр"; in docs also `Filtering → Reactions filter`) [doc]
- Engagement-ratio threshold — interactions/views ratio (e.g. 0.1, 0.05, 0.2) [doc]

## Open questions / ambiguities
- Whether the message is forwarded as soon as the threshold is reached within the window, or only at the window's end, is unclear ("respecting the delay"; "forwarded according to the time range").
- What happens to posts that never reach the threshold (presumably dropped at window end) is not stated.
- Whether multiple metric conditions combine with AND/OR is not stated.
- Menu label here ("Delay and delayed filter") differs from the docs' path (`Scheduling and publishing → Delay` / `Filtering → Reactions filter`) — probably UI renamed.
