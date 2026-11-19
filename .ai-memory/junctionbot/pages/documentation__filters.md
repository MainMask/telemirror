# Filtering (Фильтрация)
- Source: https://www.junctionbot.io/ru/documentation/filters
- EN: https://www.junctionbot.io/documentation/filters
- Fetched: 2026-11-19, method: curl+html2md

## Content

### What filters are (Что такое фильтры)

Filtering rules let you manage incoming messages: decide which to publish and which not (e.g. those containing ads).

Filters can apply to all sources in a folder or to an individual source. Any number of filter rules can be used and combined.

**Where to find:** `Menu → My forwardings → Select forwarding → Filtering` (Меню → Мои пересылки → Выберите пересылку → Фильтрация)

Note the filter debugging function (/ru/documentation/troubleshooting#filters-not-working), which can potentially save you many hours.

### Video lesson (Видеоурок)

[video] How to set up filters, using posts with crypto tokens as an example, with a **regular expression**.

### New! AI filtering (Фильтрация с помощью ИИ)

You can describe any filtering criteria in free form and let AI filter your messages automatically. Notably, this filters not just by message text as such but by its meaning and sentiment. E.g. you can ask the AI to pass only positive news :)

How to set it up: (/ru/documentation/integrations-and-settings).

### Allowing and blocking filters (Разрешающие и запрещающие фильтры)

On the filter settings page you choose what to do with messages matching the filter criterion.

An allowing filter (a.k.a. **mustHave**) **passes** only messages matching the criterion. If you have one or more allowing filters and a message matches none of them, the message is definitely stopped. In other words, multiple **mustHave** filters of the same type **are combined with "OR"**: the message passes if it matches at least one.

A blocking filter (a.k.a. **mustNotHave**) **stops** messages matching the criterion. If you have one or more blocking filters and the message matches at least one, it's definitely stopped. Multiple **mustNotHave** filters are **combined with "OR"**.

The filter type is shown in the first column: green icon = allowing, red = blocking. When creating a filter, tick or untick the left checkbox to make it allowing or blocking.

If you have several allowing text filters and several blocking text filters, the message is published **only** if it matches **at least one** allowing text filter and **none of the blocking** text filters.

These combination rules work within a set of filters of the same type. E.g. if you have allowing text-match filters and allowing regex filters, the message is published only if it matches **at least one** allowing text filter **and at least one** allowing regex filter.

There are different filter types: text match, regular expression, date, etc. Filtering is done for each type **separately**: first text filters, then regex, etc. If, e.g., text filters decide the message should be stopped, it's stopped **regardless of the results of other filters**.

### Text-match filter (Фильтр по текстовому совпадению)

The simplest type. Works on exact text match: the condition fires only if the message text contains the exact criterion text.

**Where to find:** `Menu → My forwardings → Select forwarding → Filtering → Keywords and stop words` (Фильтрация → Ключевые и стоп-слова)

To create a text filter, choose "By text match" («По текстовому совпадению») at the bottom of the screen, press the plus, enter text in the "Value" («Значение») field and save.

- **Case-sensitive.** If the criterion is "Bitcoin", it won't fire if the text only contains "bitcoin".
- If the criterion has several words, the whole criterion string must occur in the message — all words, in that order, with those separators. E.g. "Buy bitcoin" won't fire on only "Buy", only "bitcoin", or "Buy or sell bitcoin".
- For more flexible rules, use regex filtering.

### Regular-expression filter (Фильтр по регулярному выражению)

Complex rules can be set with regular expressions (RegEx).

**Where to find:** `Menu → My forwardings → Select forwarding → Filtering → Keywords and stop words`

Choose "By regular expression" («По регулярному выражению») at the bottom, press plus, enter the regex in "Value" and save.

Popular examples:

1. Don't pass posts with the word `word` inside an image caption: `.*word.*<photo>.*`
2. Two words — bitcoin and ethereum — in a specific order: `.*bitcoin.*ethereum.*`
3. Two words — litecoin and ethereum — in any order: `.*(?=.*\blitecoin\b)(?=.*\bethereum\b).*`
4. Two words — bitcoin and litecoin — in specific order, ignore case: `(?i:.*BitCoin.*liTeCoin.*)`
5. Any of the words: `.*bitcoin.*|.*litecoin.*|.*ethereum.*`
6. Rules can be combined, e.g. any of the words, case-insensitive: `(?i:.*BitCoin.*|.*liTeCoin.*|.*EthereUm.*)`
7. A word in Russian: `.*([а-яА-Я]+).*`
8. Any link: `.*(http:\/\/|https:\/\/).*`
9. Any number: `.*([0-9]+).*`
10. Any @username: `.*@([a-zA-Z0-9=&_\-]+).*`
11. Pass only images with captions (don't pass without captions): `[^<].*<photo>\s*`
12. Pass only images without captions (including albums): `(\s*<photo>)+\s*`

**IMPORTANT!**

- When filtering, the bot may append a space and/or a media-content code at the end of the text. So always put `.*` at the end of your RegEx filters.
- Filter regexes usually have `.*` at the start and end because you want the whole message to match. If you use a similar expression for replacements, you most likely want to remove these `.*` (otherwise the replacement applies to the whole message text).

#### Regex help

Regex debugging: (/ru/documentation/troubleshooting#regex-debug).

### Filtering by all word forms (Фильтрация по всем словоформам)

*Advanced filters (Продвинутые фильтры) add-on.*

Enter a word in any form — the bot recognizes all its declensions and conjugations in message text. Depending on filter type such messages are **passed** or **stopped**.

Handy for keyword search in chats. E.g. an allowing filter (/ru/documentation/filters#allowing-and-blocking-filters) with "купить" (to buy) passes messages with both "купил" and "куплю" — no need to enumerate all forms. Same for a blocking filter if a word must be excluded in all variations.

**Where to find:** `Menu → My forwardings → Select forwarding → Filtering → Keywords and stop words`

Choose "By word forms" («По словоформам») at the bottom and press plus. In "Value" enter the word in any form, tick the type — allowing or blocking — and save.

Say you search a chat for messages like "ищу мастера" ("looking for a craftsman") or "искала специалиста". Instead of adding "ищу", "искал", "искала", "ищем" separately, one rule with "ищу" suffices — the bot recognizes the rest.

Nuances:

- Prefixes and prepositions are not accounted for: "купить" and "выкупить" are different words; a match on one won't fire on the other.
- Case-insensitive: "купил" = "Купил".
- One word — one filter: if you enter a phrase, the bot uses only the first word.
- Supported languages: Russian, English, Ukrainian and German; words not in the dictionary (slang, names, titles) are matched only exactly as entered.

The filter is part of the "Advanced filters" add-on (attachable to any package) and of the "Business" («Бизнес») package. [payment-related content omitted] Without the add-on, word-form filters are not applied: messages are forwarded as if these filters didn't exist.

**Want to set up something similar manually?**

To filter a word in all declensions without matching prefixed words, use regexes. E.g. pass all messages with "заявка" (application/request) in any case, but not "подзаявка" (sub-request):

- Write out all forms: заявка, заявки, заявку, заявок, etc.
- Put each form into `\bword\b`, which passes only exact whole-word matches (and won't pass "подзаявка"): `\bзаявка\b`, `\bзаявки\b`, `\bзаявку\b`, `\bзаявок\b`.
- Add these 4 regex filters via **Menu → My forwardings → Select forwarding → Filtering → Keywords and stop words** (image: example of adding regex filters).

Done! Only messages with "заявка" in any form will be published; "подзаявка" won't.

If you accumulate many filters, it's easier to collect them in a table first and import them all at once via the bulk import button.

### Date/time filter (Фильтр по дате/времени публикации)

Sets pass rules depending on message arrival time.

The criterion is a time interval. It defines:
- the period when messages should arrive — for allowing filters (mustHave);
- the period when messages should not arrive — for blocking filters (mustNotHave).

**Where to find:** `Menu → My forwardings → Select forwarding → Filtering → Keywords and stop words → choose type "By date/time" («По дате/времени») → "+"`

The interval can contain a weekday, a time and a time zone:

**Weekday** — always starts with the letter `w` followed by digits of weekdays. E.g.:
- `w135` — 1st, 3rd and 5th days of the week (Mon, Wed, Fri)
- `w67` — 6th and 7th days — weekend.

**Time** — always 24-hour format, a from–to interval, inclusive, `hours:minutes`. E.g. `9:30-17:30`, `0:00-23:59`.

An interval across midnight (e.g. `17:00-03:00`) can't be set in one line: start must be earlier than end, otherwise the bot shows an error. Use a blocking filter on the daytime part (`3:00-16:59 Europe/Moscow`) or two allowing ones (`17:00-23:59 Europe/Moscow` and `0:00-3:00 Europe/Moscow`) — with several allowing time filters, a message passes if it falls in at least one. Note: the filter doesn't pause the forwarding or queue messages — messages outside the window are dropped and won't arrive later. To publish later, use "Delay" («Задержать») or "Schedule ('deferred')" («Запланировать ("отложка")»).

**Time zone** — list of available zones: https://junction.space/timezones.html. If no zone is given, UTC is assumed. Specify the zone explicitly, e.g. `Europe/Berlin` or `Europe/Moscow`, otherwise the window shifts.

**EXAMPLES**

- Blocking `0:00-7:00 Europe/Berlin` — messages will **not** arrive from midnight to 7 am Berlin time.
- `w12345 8:00-20:00 Europe/Moscow` — messages arrive only on weekdays from 8 am to 8 pm Moscow time.

**Alternative: via commands**

`/filtertime <source_link> mustHave w12345 8:00-20:00 Europe/Moscow`

To add a date/time filter **to all your sources at once** use `/filtertimeall`. E.g.: `/filtertimeall add mustNotHave 0:00-7:00 Europe/Berlin`. To remove: `/filtertimeall remove mustNotHave 0:00-7:00 Europe/Berlin`.

### Delayed filter (Отложенный фильтр)

*"Advanced filters" add-on (attachable to any package); also included in the "Business" package.* [payment-related content omitted]

With this setting you can:

- **Delay publication** of a message by a fixed or random time,
- Specify a **condition under which** the message should be published (minimum number of ❤️ reactions, 👀 views, ✈️ forwards **or** 🗨️ replies).

**Where to find:** `Menu → My forwardings → Select forwarding → Filtering → Reactions filter` (Фильтрация → Фильтр по реакциям)

The same setting exists in the "Scheduling and publishing" («Планирование и публикация») group → "Delay" («Задержать»).

[img: Instruction image] Instruction: Delayed filters (/ru/instructions/delayed-filters)

#### How to set up delayed publication

- To delay by a fixed time (e.g. 3 hours), set "From" («От») to 3 hours. If the source message appeared at 14:00, forwarding happens exactly 3 hours later, at 17:00 (left picture).
- If you set "From" and "To" («До»), the message is sent at a random time within the range. Source message at 14:00 with "From 3 to 6 hours" → sent at a random moment between 17:00 and 20:00 (right picture).

#### How to set up a publication condition

Use this when you want only messages with enough **❤️ reactions, 👀 views, ✈️ forwards or 🗨️ replies** in the destination.

E.g. only messages with **at least 2 reactions**: create the "Min. reactions" («Мин. реакций») filter with value "2". Keep the check interval at 3–6 hours.

Source message at 14:00; the bot checks:

- **1st check** — 3 hours after publication (17:00). If ≥ 2 reactions, published. Otherwise the next check is scheduled.
- **2nd check** — 6 hours after publication (20:00). If ≥ 2 reactions by then, published. If still < 2, the message is not published at all.

If you tick "**Repeat the check hourly throughout the period**" («Повторять проверку раз в час в течение всего периода»), the bot additionally checks at 18:00 and 19:00.

If the time range is less than 1 hour and set in minutes or seconds, there are only 2 checks (at the start and end of the range).

Delayed filters let you forward **only messages with the highest audience engagement** — based on interactions-to-views ratio:

- ❤️/👁 **Min. reactions to views** (Мин. реакций к просмотрам)
- ➡️/👁 **Min. forwards to views** (Мин. пересылок к просмотрам)
- 💬/👁 **Min. replies to views** (Мин. ответов к просмотрам)

**How it works:** specify the filter value as the ratio (interactions / views). **Examples:**

- Copy posts with 1 reaction per 10 views (1/10) → **0.1**
- Copy posts with 50 replies per 1000 views (50/1000) → **0.05**
- Copy posts with 20 forwards per 100 views (20/100) → **0.2**

### New! Filtering order (Порядок фильтрации)

Defines when filtering is applied relative to replacements (/ru/documentation/message-processing#replacing-text) and AI processing (/ru/documentation/message-processing#gpt-processing). Set per forwarding.

**Where to find:** `Menu → My forwardings → Select forwarding → Filtering → Filtering order` (Фильтрация → Порядок фильтрации)

**Available settings:**

- `after reception` — immediately after receipt, before replacements.
  **Processing order:** Filters → Replacements → AI processing.
  **Filtering on the original text:** the bot filters first, then applies replacements. Useful with complex replacement rules so replacements don't affect filters.
- `after replacements` — after replacements but before AI processing.
  **Processing order:** Replacements → Filters → AI processing.
  **Filtering after replacements:** useful when you need to pass only posts with replaced links and then modify the text with AI.
- `after ai` — after AI processing, right before publication.
  **Processing order:** Replacements → AI processing → Filters.
  **Filtering after AI:** the AI marks irrelevant content with a keyword, and the filter cuts it.

**How to set up (after ai example):**

1. **Configure AI processing:** in the forwarding settings find AI processing and choose the prompt "Ad check" («Проверка на рекламу»). Edit it so the AI replaces the text of irrelevant messages with a specific word, e.g. "ПРОПУСК" ("SKIP").
2. Add a blocking text filter (/ru/documentation/filters#text-filters) on the word "ПРОПУСК".
3. Set **"Filtering order"** to `after ai`.
4. **Done!** All ads from the source are filtered out and only relevant content reaches the destination.

### Author filter (Фильтр по автору)

**Where to find:** `Menu → My forwardings → Select forwarding → Filtering → Keywords and stop words → choose type "By author" («По автору») → "+"`

Filtering by author ID: pass rules based on the message author's number (ID). For anonymous messages, the author number is the number of the corresponding group or channel without the `-100` prefix. Enter digits only, no spaces, e.g. `123456789`. Note: **the criterion is the number, not the author's name**.

Filtering by author number is the most effective and convenient way and is recommended. But sometimes you need to filter by author name. The procedure is slightly more complex:

**Step 1.** `Menu → My forwardings → Select forwarding → Source info → Author` (Информация об источнике → Автор) — enable display of the author name in forwarding settings.

**Step 2.** `Menu → My forwardings → Select forwarding → Filtering → Keywords and stop words → choose type "By text match" → "+"` — add a text filter with the author name as the criterion.

With this approach, resulting messages contain the author's name. Sometimes you need no author name — then use an intermediate channel:

Suppose we forward A → B. Create channel C and set up filtered forwarding A (source) → C (intermediate), applying steps 1 and 2. Then set up C (intermediate) → B (destination). On that forwarding create a replacement deleting author names:

`Menu → My forwardings → Select forwarding → Text processing → Replace links and words in text → "➕ Create new replacement"` (Обработка текста → Замена ссылок и слов в тексте → «➕ Создать новую замену»)

- Source: `@user (Name)` — where `@user` is the author's username and `(Name)` is the display name in Telegram.
- New value: (empty)

Done! If you applied the replacement on the first forwarding (A → C), it wouldn't affect the author name: the author name, like the source channel name, is service text, isn't replaced by Replacements and is configured by other means.

### Own messages filter (Фильтр собственных сообщений)

*Direct or Expert plans.*

Show or hide messages sent on behalf of the connected account.

**Where to find:** `Menu → My forwardings → Select forwarding → Filtering → Filter my messages` (Фильтр моих сообщений)

**Available settings:**

- `pass` — disabled; show messages authored by you
- `filter` — filter out (don't show)

### Media type filter (Фильтр по типу медиа)

[img: Instruction image] Instruction: How to filter photo/video (or any other media type) (/ru/instructions/how-to-filter-any-media)

To filter by media type, use one of these **text filters**:

- `<photo>` — images and photos
- `<document>` — file attachments
- `<audio>` — audio and music
- `<video>` — video
- `<sticker>` — stickers
- `<voice>` — voice messages
- `<location>` — geolocation pins
- `<animation>` — GIF animation
- `<videonote>` — round video notes
- `<poll>` — polls

**Where to find:** `Menu → My forwardings → Select forwarding → Filtering → Keywords and stop words → choose type "By text match" → "+"`

### Forwarded messages filter (Фильтр пересланных сообщений)

[img: Instruction image] Instruction: How to filter forwarded messages (/ru/instructions/how-to-filter-forwarded-messages)

Filters Telegram messages that were forwarded into the source channel from other channels or chats.

**Where to find:** `Menu → My forwardings → Select forwarding → Filtering → Filter forwarded messages` (Фильтровать пересланные сообщения)

**Available settings:**

- `all` — send all message types from source to destination without splitting into regular and forwarded
- `direct only` — only regular messages are sent to the destination
- `forward only` — only forwarded messages are sent to the destination

"Direct only" is useful if you follow a channel with lots of info from various sources but want only the author's own opinion: choose `direct only` and filter out messages forwarded into the channel under someone else's name.

### Every n-th message filter (Фильтр каждого n-го сообщения)

You can set the frequency of forwarded messages, i.e. forward only every n-th message. Send the bot: `/filter <source_link> every 2` (forward only every second message from the source).

### Duplicate filter (Фильтр дубликатов)

Sometimes the same message arrives several times (e.g. you follow two channels that forwarded the same post). To filter identical messages, use the "Duplicate filter" («Фильтр дублей») setting.

**Where to find:** `Menu → My forwardings → Select forwarding → Filtering → Duplicate filter`

**Available settings:**

- `pass` — disabled; duplicates don't affect publication
- `filter` — don't publish duplicates
- `only_duplicates` — publish only duplicates

"Publish only duplicates" is useful if you have two sources and want to publish only messages identical in both: set up two forwardings from the two sources into an intermediate channel, then one more forwarding from it to the final channel publishing only duplicates. Only messages that hit the intermediate channel twice pass.

**The duplicate filter ignores buttons.** Two messages with the same text but different buttons are considered identical.

**The duplicate filter remembers the last 300 messages in the source.** If 300 other messages occur between identical ones, the bot no longer remembers the first and won't filter the second. If there are no messages for 24 hours, the filter memory is reset.

**Note:** the duplicate filter compares **source (original)** messages. To avoid duplicates in the destination that arise from your replacement rules, use an intermediate channel:

Suppose we forward A → B.

**Step 1.** Create channel C and set up A (source) → C (intermediate). Apply all your replacement rules to channel A. No duplicate filter needed on A.

**Step 2.** Set up C (intermediate) → B (destination). Set the filter rule on this forwarding (via the menu or the command `/settingchannel C duplicate filter`). It removes all duplicates, including those created by replacement rules.

**Step 3.** Add @junction_bot to the destination channel's admins. Any rights are fine.

Done! Had you set the duplicate filter on the first forwarding (A → C), it wouldn't catch duplicates produced by replacements.

Note: the duplicate filter doesn't work with the delivery mode `forward_client`.

### Creating a filter for all sources (Создание фильтра на все источники)

To add a filter to all **current** sources use `/filterall` or `/filterrxall` (for regexes).

E.g.: `/filterrxall add mustNotHave .*(http:\/\/|https:\/\/).*` — adds to all sources a filter blocking messages with links. To remove the same filter from all channels, replace `add` with `remove`.

New forwardings are always created with an empty filter list. You can copy (/ru/documentation/filters#copy-filters) filters onto them from an existing source.

### Editing and deleting filters (Редактирование и удаление фильтров)

Most convenient via the menu:

**Where to find:** `Menu → My forwardings → Select forwarding → Filtering → Keywords and stop words`

To delete filters **from all sources at once**, use `/filterall DELETE ALL`.

**Alternative: via commands**

- To see all filters applied to a channel: `/filter <source_link>`
- To remove a filter from one source, run the same command again (toggle). E.g. added with `/filter <source_link> mustHave some_text` → removed with `/filter <source_link> mustHave some_text`.
- If added with `/filterall add mustHave some_text`, remove it from just one source with `/filter <source_link> mustHave some_text`.
- To delete all filters from all channels: `/filterall DELETE ALL`

### Copying filters (Копирование фильтров)

Copy all filters from another channel: `/filter <target_link> addAllFrom <source_link>`

### Manual filtering (Ручная фильтрация)

To decide manually whether to pass or filter a post, use moderation mode (/ru/documentation/publishing-and-moderation#review-mode).

### Filter diagnostics (Диагностика фильтров)

Filter debugging: (/ru/documentation/troubleshooting#filters-not-working).

## Features mentioned
- Filter rules per forwarding or per folder; unlimited count [doc]
- mustHave / mustNotHave semantics — OR within same type; AND across types; per-type sequential evaluation, any type can veto [doc]
- Text-match filter — exact, case-sensitive substring [doc]
- Regex filter — 12 example patterns; media tokens like `<photo>` appended to text; trailing `.*` advised [doc]
- Word-form (morphological) filter — RU/EN/UK/DE, case-insensitive, one word per filter; paid add-on "Advanced filters" / Business package [doc]
- Bulk import of filters from a table [doc]
- Date/time filter — `w135`, `9:30-17:30`, IANA tz (default UTC); no cross-midnight; drops out-of-window messages [doc]
- Commands `/filtertime`, `/filtertimeall add|remove` [doc]
- Delayed filter — fixed or random delay; publish conditions min reactions/views/forwards/replies; 2 checks (start/end) or hourly; engagement ratios (reactions/forwards/replies per view); Advanced filters add-on [doc]
- Filtering order — after reception / after replacements / after ai; AI-tag-then-block pattern ("Ad check" prompt + "ПРОПУСК") [doc]
- AI filtering — free-form criteria by meaning/sentiment [doc]
- Author filter by numeric ID (anonymous = chat ID without -100); by name via author display + text filter, intermediate-channel trick to strip name [doc]
- Own messages filter (Direct/Expert) — pass/filter [doc]
- Media type filter via text tokens `<photo> <document> <audio> <video> <sticker> <voice> <location> <animation> <videonote> <poll>` [doc]
- Forwarded messages filter — all / direct only / forward only [doc]
- Every n-th message — `/filter <src> every N` [doc]
- Duplicate filter — pass/filter/only_duplicates; ignores buttons; window 300 msgs; memory reset after 24h idle; compares originals; incompatible with forward_client [doc]
- Intermediate channel pattern for post-replacement dedup / AND of two sources [doc]
- Bulk commands — `/filterall`, `/filterrxall add|remove`, `/filterall DELETE ALL`, `/filter <src>` list/toggle, `addAllFrom` copy, `/settingchannel C duplicate filter` [doc]
- New forwardings start with empty filter list [doc]
- Manual filtering via moderation; filter debugging in troubleshooting [doc]

## Open questions / ambiguities
- Order in which filter types are evaluated is only partially stated ("first text, then regex, etc.").
- "Business" package name appears here but not in getting-started's tier list (possibly the 5th package).
- Delayed filter checks: with "From" only (fixed delay), whether the condition is checked once is not explicit.
- `forward_client` delivery mode identifier is referenced but defined on publishing-and-moderation page.
