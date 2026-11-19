# Message processing (Обработка сообщений)
- Source: https://www.junctionbot.io/ru/documentation/message-processing
- EN: https://www.junctionbot.io/documentation/message-processing
- Fetched: 2026-11-19, method: curl+html2md

## Content

`PLEASE NOTE:` (`ОБРАТИТЕ ВНИМАНИЕ:`)

Message processing is only possible when messages are delivered by the **copy** method (see [publishing mode](/ru/documentation/publishing-and-moderation#publishing-mode)). When messages are delivered using Telegram's built-in forward mechanism, no content transformation is possible!

### Video tutorial (Видеоурок)

In the video below we explain **how to set up a replacement**, using the example of removing links from posts with a **regular expression**. [video]

### New! AI transformation (Трансформация с помощью ИИ)

You can describe in free form the changes that should be made to message text, and let AI do the rest. This lets you either change individual text elements or numbers, or rewrite the text completely (e.g. into another language, in another style, changing length while keeping the meaning, analyzing and drawing conclusions, etc.).

How to set it up: see [here](/ru/documentation/integrations-and-settings#chat-gpt-integration).

### Adding text (Добавление текста)

These settings add text before or after the message text.

**Where to find**

- `Menu → My forwardings → Select a forwarding → Text processing → Add header` (`Меню → Мои пересылки → Выберите пересылку → Обработка текста → Добавлять заголовок`)
- `Menu → My forwardings → Select a forwarding → Text processing → Add text after message` (`... → Обработка текста → Добавлять текст после сообщения`)

Example of adding text at the beginning:

> Here is what I heard. (Вот что я слышал.)

Note that the original message text continues on the same line as your text, i.e. the message will look like:

> Here is what I heard. Once the Buddha came...

If you want the original text to start on a new line, remember to add a line break at the end of your header.

Examples of adding text at the end:

> All questions to support@mail.com

> `<a href="https://junctionbot.io/">My website</a>`

Note that if you do not put a line break at the beginning, your text starts on the same line as the original message text.

### Trimming and shortening text (Обрезка и укорачивание текста)

**Where to find**

`Menu → My forwardings → Select a forwarding → Text processing → Text trimming` (`Обрезка текста`)

Long messages are shortened to the specified length. Recommended values: from 150 (Twitter-style posts) to 1000 (several paragraphs). To disable, set the value to 0.

### Text replacement (Замена текста)

[Instruction card] Instruction: [How to replace a word or part of text when copying messages](/ru/instructions/how-to-replace-a-word-or-part-of-text-when-copying-messages)

**Where to find**

`Menu → My forwardings → Select a forwarding → Text processing → Replace links and words in text` (`Замена ссылок и слов в тексте`)

You can set an auto-replace rule that replaces text A in incoming messages with text B (or with an empty string if B is not given).

Note: this setting works **only on the message body and buttons**; it does not change the header (the channel name, if you enabled showing it) or the link to the original message.

If there are several rules, they are applied strictly in list order, top to bottom, and each next rule operates on the already-modified text. A new replacement is always appended to the end of the list; it cannot be dragged higher. So if a short rule fires inside a longer word and breaks it, create the long replacements before the short ones (if needed, delete the short replacement and re-create it — it will end up at the end of the list). Automatic replacement of links to the source ("Replace cross-links with source" / «Заменять кросс-ссылки на источник») runs after all your rules.

#### Replacement using regular expressions (Замена с использованием регулярных выражений)

You can also use [regular expressions](https://ru.wikipedia.org/wiki/Регулярные_выражения) for replacement. To do so, on the replacements settings page tick the **RE** (Regular Expression) checkbox for the needed replacement.

Useful regex replacement examples: [Advanced examples](/ru/documentation/message-processing#advanced-regex-examples).

#### Regex help (Помощь по регулярным выражениям)

More on debugging regular expressions: [here](/ru/documentation/troubleshooting#regex).

#### Adding formatting (Добавление форматирования)

Text formatting is done via HTML tags. See tags supported by Telegram [here](https://core.telegram.org/bots/api#html-style).

To **add formatting**, surround the piece of text with the corresponding tags. E.g., to make a piece of text bold, create a new replacement:

- Source (Источник): `the needed piece of text`
- New value (Новое значение): `<b>the needed piece of text</b>`

Useful advanced formatting examples: [Advanced examples](/ru/documentation/message-processing#advanced-formatting-examples).

#### Removing formatting (Удаление форматирования)

To **remove formatting**, you first need to understand what the [source text of the message](/ru/documentation/troubleshooting#source-code), including tags, looks like.

Then you can add replacement rules that remove the unwanted tags.

E.g., to remove bold from a piece of text, add a new replacement:

- Source: `<b>the needed piece of text</b>`
- New value: `the needed piece of text`

Alternative setup via command (Альтернативный способ настройки через команду):

Command: `/replace source <b>needed&nbsp;piece&nbsp;of&nbsp;text</b> needed&nbsp;piece&nbsp;of&nbsp;text` (spaces inside arguments written as `&nbsp;`)

#### Replacing premium emoji (Замена премиум emoji)

Premium emoji are transmitted with a `<strong>` tag, e.g.:

`<strong documentid="123456789">(emoji)</strong>`

You can find the exact code in [one of several ways](/ru/documentation/troubleshooting#source-code), e.g. by enabling in forwarding settings "Debug settings → Processing report" (`Отладочные настройки → Отчет об обработке`) and waiting for a message from the source with the needed emoji.

Knowing the exact code, you can use it in replacements or add this emoji to your message via "Add header" or "Add text after message". Note that publishing premium emoji requires the [corresponding conditions](/ru/documentation/forwarding#fw-tg-premium) to be met.

### Link to the original message setting (Настройка ссылки на оригинальное сообщение)

This setting controls displaying a link to the original message at the end of the message. This means **only** the link that by default appears at the bottom of a **forwarded** message as the `@` symbol. If you want to change other links in the message, see [here](/ru/documentation/message-processing#replacing-links).

**Where to find**

`Menu → My forwardings → Select a forwarding → Source info → Link to original post` (`Информация об источнике → Ссылка на оригинальный пост`)

**Available settings**

- `none` — do not pass the link
- `full` — pass the link as is
- arbitrary value — hide the link behind this string

### Automatic replacement of all mentions (links) of the source (Автоматическая замена всех упоминаний (ссылок) на источник)

[Available only on a specific (top) plan — limit depends on plan]

This smart link-replacement setting automatically replaces absolutely all links to the source without creating replacement rules manually. These can be plain links to the channel in incoming message text, or references to other messages in this channel.

**Where to find**

`Menu → My forwardings → Select a forwarding → Source info → Replace cross-links with source` (`Заменять кросс-ссылки на источник`)

### Replacing links in text (Замена ссылок в тексте)

[Instruction card] Instruction: [How to replace a word or part of text when copying messages](/ru/instructions/how-to-replace-a-word-or-part-of-text-when-copying-messages)

Links in a message come in different types, so no single universal command exists. First determine the link type, only then create the right replacement rule. To determine the link type, view the [message source code](/ru/documentation/troubleshooting#source-code). That is exactly how the bot sees the message when applying replacement rules.

**Option 1. HTML links with the `<a>` tag**

In the received report we see that the link is set by formatting with the `<a>` tag. E.g.:

```
Fresh news!
We won the "Fastest bot in Telegram!" award
<a href="https://junctionbot.io">Welcome to our website!</a>
```

Then the replacement rule must use the whole construction.

To simply remove the link, create a replacement leaving "New value" empty:

- Source: `<a href="https://junctionbot.io">Welcome to our website!</a>`
- New value: (empty)

To swap one link for another:

- Source: `<a href="https://junctionbot.io">Welcome to our website!</a>`
- New value: `<a href="https://lectumbot.com">Welcome to our website!</a>`

To replace not a specific link but all possible links set via `<a>`:

- Source: `<a[^<]+</a>`
- RE (Regular expression): Yes
- New value: (empty)

**Option 2. Plain links**

In the received report we see the link is given without formatting, just as text — no `<a>` tag around it. E.g.:

```
Fresh news!
We won the "Fastest bot in Telegram!" award
Welcome to our website!
https://junctionbot.io
```

Then just put the link in the replacement rule.

To remove it:

- Source: `https://junctionbot.io`
- New value: (empty)

To replace with another:

- Source: `https://junctionbot.io`
- New value: `https://lectumbot.com`

To remove any such links:

- Source: `https:\/\/\S+`
- RE: Yes
- New value: (empty)

Any `@username` links not added by the bot itself can be removed with:

- Source: `@([a-zA-Z0-9=&_\-]+)`
- RE: Yes
- New value: (empty)

The link to the source post added by the bot itself can be removed in: `Menu → My forwardings → Select a forwarding → Source info → Link to original post → none`

### Name and other data about the source (Название и другие данные об источнике)

This setting adds the source channel name and other message data to the message.

[Instruction card] Instruction: [How to specify the name of the source chat when copying messages](/ru/instructions/how-to-specify-the-name-of-the-source-chat-when-copying-messages)

**Where to find**

`Menu → My forwardings → Select a forwarding → Source info → Source name` (`Название источника`)

**Available settings**

- `none` — do not show names
- `simple` — add the source channel name as a header (at the start of the message)
- `bold` — add the name in **bold** as a header
- `from_only` — do not show the immediate source name, but show the name of the original source (if any)
- `id` — instead of the name, show the message ID in the source channel
- `date` — instead of the name, show the publication date of the message in the source channel
- arbitrary value — replace the channel name with this text (standard [Telegram HTML tags](https://core.telegram.org/bots/api#html-style) supported)

Use the last option carefully: if formatting is broken (e.g. unclosed or unsupported tags), you will stop receiving messages from this channel or they will arrive completely unformatted.

### Author display setting (Настройка отображения автора)

Applies only to messages containing an author name.

You can choose how the message author's name is displayed.

[Instruction card] Instruction: [How to specify the author when copying messages](/ru/instructions/how-to-specify-the-author-when-copying-messages)

**Where to find**

`Menu → My forwardings → Select a forwarding → Source info → Author` (`Автор`)

**Available settings**

- `none` — do not show the name
- `name` — show the name
- `username` — show @username
- `full` — show name and @username
- `full_except_bot` — show name and @username for everyone except Junction Bot

If you chose to show the name and/or username, the bot tries to make the author name full and a link. This is not always possible, since the bot does not immediately receive the author's full name due to Telegram limits on the number of user profiles fetched per minute. It also depends on things like the author's privacy settings. So in some cases the name may be passed as `User#123456`.

Another way to keep the author name is to not copy but forward messages using the delivery mode "Forward via account" (`Пересылать через аккаунт`, see [publishing mode](/ru/documentation/publishing-and-moderation#publishing-mode)).

Alternative setup via commands: `/setting author none`, `/setting author name`, etc.

### Adding your own buttons (Добавление своих кнопок)

You can add your own URL buttons to forwarded messages.

Important: due to Telegram limitations, native buttons are published only in the [delivery mode](/ru/documentation/publishing-and-moderation#publishing-mode) "Copy via bot" (`Копировать через бота`, `copy_bot`). In delivery modes on behalf of an account (e.g. "Copy via account" / `Копировать через аккаунт`), your buttons are added only if the connected account has Telegram Premium: the message is published as a rich message, and link buttons are shown inside it. In "Forward via account" mode your buttons are not added.

**Where to find**

`Menu → My forwardings → Select a forwarding → Buttons → Add your own buttons` (`Кнопки → Добавить свои кнопки`)

**Available settings**

- `none` — do not add own buttons
- arbitrary value — add own buttons

To add buttons, in the "Arbitrary value" field enter the button URL and the button text separated by a space. Each new button on a new line.

Example:

```
https://junction.space About the project
https://tgchannels.org All channels here
```

Alternative via command:

```
/setting mybuttons
https://junction.space About the project
https://tgchannels.org All channels here
```

### Adding feedback buttons (Добавление кнопок обратной связи)

Adds feedback buttons to the message (e.g. "likes").

Feedback buttons work only in "Copy via bot" (`copy_bot`) delivery mode: when delivering on behalf of an account they are not added, even if the account has Telegram Premium.

**Where to find**

`Menu → My forwardings → Select a forwarding → Buttons → Feedback buttons` (`Кнопки обратной связи`)

**Available settings**

- `none` — no buttons
- `1` — a 👍 button
- `2` — two buttons: 👍 and 👎
- arbitrary value — each word of the string becomes a separate button

Example: the string `👍 👎` has the same effect as option 2.

Example: `Yes No Maybe` (`Да Нет Возможно`) adds 3 buttons "Yes", "No", "Maybe".

Alternative via command: `/setting like Да Нет Возможно`

### Media replacement and transformation (Замена и трансформация медиа)

Regular replacements work only with message text and buttons. If you want to replace one picture with another or add media to a text message, use [moderation mode](/ru/documentation/publishing-and-moderation#review-mode).

How to add watermarks: see [here](/ru/documentation/message-processing#adding-watermarks).

You can process media with third-party Telegram bots and then use them in Junction Bot: see [here](/ru/documentation/message-processing#using_other_bots).

### New! Adding watermarks (Добавление водяных знаков (ватермарок))

[Available only on certain plans — depends on plan]

Junction Bot can protect your Telegram media with watermarks. Add your watermarks to photos, animations and videos.

**Where to find**

`Menu → My forwardings → Select a forwarding → Images and video → Watermarks` (`Изображения и видео → Водяные знаки`)

- Choose a watermark from the list of previously uploaded ones.
- Tick which content types to apply it to:
  - **Apply to image** (`Накладывать на изображение`)
  - **Apply to video** (`Накладывать на видео`)
  - **Apply to animation** (`Накладывать на анимацию`)

#### Creating a new watermark (Создание нового водяного знака)

In **My watermarks** (`Мои водяные знаки`) choose **Create new watermark** (`Создать новый знак`). Fill in:

- **Name** of the watermark
- Upload the **Watermark file**. Only PNG images are supported as watermarks.
- **Choose opacity level** — the higher the value, the more transparent the applied mark.
- Choose **Scaling** (`Масштабирование`):
  - Fit (proportional) (`Вместить (пропорционально)`) — fit the watermark inside the image bounds, shrinking if needed.
  - Cover (proportional) (`Покрыть (пропорционально)`) — enlarge the watermark to the image size.
  - Do not scale (`Не масштабировать`) — neither shrink nor enlarge.
- Choose **Alignment** (`Выравнивание`) (center, one of the sides or corners, or "Random" / «Случайное»).

### Using other Telegram bots (Использование других Telegram ботов)

If you need features like advanced image processing etc., you can embed a bot that performs that function into your forwarding rule.

**Step 1** — Find the Telegram bot you want to use.

**Step 2** — Set up a forwarding from the needed source to this bot.

**Step 3** — Set up a forwarding from the bot to the needed destination channel.

If you need to run several sources through a third-party bot and then split them into different destinations again:

- Set up forwarding from the source to the third-party bot.
- For each source, add a specific text key to the message, e.g. `ИСТОЧНИК1` (SOURCE1):
  `Menu → My forwardings → Select a forwarding → Text processing → Add header`, value: `ИСТОЧНИК1`
- Set up forwarding from the third-party bot to an intermediate channel.
- Add a filter on the forwarding from the third-party bot to the intermediate channel so only messages with the key pass:
  `Menu → My forwardings → Select a forwarding → Filtering → Keywords and stop words` (`Фильтрация → Ключевые и стоп-слова`). Choose type "By text match" (`По текстовому совпадению`), press "+", mode "Pass matching messages" (`Пропускать подходящие сообщения`), value: `ИСТОЧНИК1`
- Set up forwarding from the intermediate channel to the destination channel.
- Remove the key when forwarding from the intermediate channel to the destination:
  `Menu → My forwardings → Select a forwarding → Text processing → Replace links and words in text`, Source: `ИСТОЧНИК1`, New value: (empty)

### Manual editing (Ручное редактирование)

If you want to edit a forwarded message manually, use [moderation mode](/ru/documentation/publishing-and-moderation#review-mode).

### Advanced message processing examples (Продвинутые примеры обработки сообщений)

#### Useful replacement settings (Полезные настройки замен)

Below are expressions for popular replacement tasks. Some can be solved without regular expressions, but most cannot.

##### 1. Remove the header with the source channel name added by the bot

Where to find: `Menu → My forwardings → Select a forwarding → Source info → Source name → none`

Alternative via command: `/setting header none`

##### 2. Remove the link to the source post added by the bot

Where to find: `Menu → My forwardings → Select a forwarding → Source info → Link to original post → none`

#### Replacements with regular expressions (Замены с регулярными выражениями)

Where to find: `Menu → My forwardings → Select a forwarding → Text processing → Replace links and words in text`

##### 3. Remove specific links from the message body

- Source: `<a href="https://specific-link">text of this link</a>`
- RE: No
- New value: (empty)

Alternative via command: `/replace link_to_source <a href="https://specific-link">text&nbsp;of&nbsp;this&nbsp;link</a>`

In all messages from channel @source it will replace exactly such links with an empty string.

##### 4. Remove all links in the message body if they are passed as formatting

- Source: `<a[^<]+</a>`
- RE: Yes
- New value: (empty)

Alternative via command: `/replacerx source <a[^<]+</a>`

##### 5. Remove links in the message body passed as plain text

- Source: `(http:\/\/|https:\/\/)([a-zA-Z0-9.\/\?=&_]+)`
- RE: Yes
- New value: (empty)

Alternative via command: `/replacerx source (http:\/\/|https:\/\/)([a-zA-Z0-9.\/\?=&_]+)`

##### 6. Remove only links containing "t.me"

- Source: `(http:\/\/|https:\/\/)(t.me)([a-zA-Z0-9.\/\?=&_]+)`
- RE: Yes
- New value: (empty)

##### 7. Remove username links like @username

- Source: `@([a-zA-Z0-9=&_\-]+)`
- RE: Yes
- New value: (empty)

##### 8. Remove the whole part of the message starting with the word "Postscriptum"

- Source: `Postscriptum.*`
- RE: Yes
- New value: (empty)

##### 9. Turn the text "piece of text" into a link to https://junctionbot.io/

- Source: `кусок текста` (piece of text)
- RE: Yes
- New value: `<a href="https://junctionbot.io/">кусок текста</a>`

##### 10. Remove all numbers of the form "№12345"

- Source: `№([0-9]+)`
- RE: Yes
- New value: (empty)

##### 11. Remove text from captions of all pictures (forward only pictures)

All other text messages (without pictures) will not be forwarded.

- Source: `.*`
- RE: Yes
- New value: (empty)

##### 12. Remove all lines containing the word `keyword`

- Source: `.*\bkeyword\b.*`
- RE: Yes
- New value: (empty)

##### 13. Remove all empty lines

- Source: `<br><br>`
- RE: Yes
- New value: `<br>`

##### 14. Make the word `keyword` **bold**

- Source: `keyword`
- RE: Yes
- New value: `<b>keyword</b>`

##### 15. Make all numbers **bold**

Note that in the last argument we substitute the text matched by the regex using a so-called numbered backreference `$1`. More about it [here](https://www.regular-expressions.info/replacebackref.html).

- Source: `([0-9]+)`
- RE: Yes
- New value: `<b>$1</b>`

Make the entire message bold:

- Source: `(.*)`
- RE: Yes
- New value: `<b>$1</b>`

##### 16. Remove all text, leaving only a line of a specific format

Remove all text, leaving only a line like "Token: 0xdAC17F958D2ee523a2206206994597C13D831ec7", where the token value can be any ETH20-format address.

- Source: `(?s).*(Token: 0x[a-zA-Z0-9]+).*`
- RE: Yes
- New value: `$1`

What's happening here? We replace all text matching the expression with the value of the first group (`$1`). The first group here is `(Token: 0x[a-zA-Z0-9]+)`. The wrapping `(?s).*` and `.*` makes all text around the needed line fall under the replacement. Since `.*` covers at most one line, we add the `(?s)` modifier; thanks to it `.*` covers all lines before and after the token line.

#### Advanced formatting change example (Продвинутый пример изменения форматирования)

Suppose we created a channel aggregating free trading signals from other channels and want to bring all signals to one format. Example message in a source channel:

```
Buy BTC/USD
Stop-Loss at 11000
Take-Profit 1 at 11500
Take-Profit 2 at 11700
Take-Profit 3 at 12000
```

We want to bring such messages to the format:

```
BUY
#BTC/USD
SL: 11000 points
TP: 12000 points
Trade at your own risk!
```

1. Replace `Buy` with a space by `BUY`, a line break and `#`. Create a new replacement:
   - Source: `Buy ` — don't forget to include the space after Buy
   - New value: `BUY<br>#` — line break is given by `<br>`; you can replace it with an ordinary line break.
2. Similarly, replace `Stop-Loss at` with `SL:`
   - Source: `Stop-Loss at` — without trailing space: the space before the number must remain
   - New value: `SL:`
3. The next replacement is harder: remove the `Take-Profit 1` line and append `points` to the previous `SL` line, using a regex:
   - Source: `(\d+)\nTake-Profit 1.*\n`
   - RE: Yes
   - New value: `$1 points<br>`
4. Then replace the `Take-Profit 2` line with price and `Take-Profit 3` with `TP:` and add `points`:
   - Source: `Take-Profit 2.*\nTake-Profit 3 at (\d+)`
   - RE: Yes
   - New value: `TP: $1 points`
5. Finally, append the line `Trade at your own risk!` using the "Add text after message" setting:
   - `<br>Trade at your own risk!`

#### Using intermediate channels (Использование промежуточных каналов)

If you need to apply a setting only to part of the forwarded messages, use intermediate channels.

Say you want to add an "Open" button to all posts forwarded from A to B that contain the word `junction_bot`:

- Create a forwarding from channel A to intermediate channel C.
- Add to it the "Keywords and stop words" filter of type "By text match" with the word `junction_bot` in mode "Pass matching messages".
- Create a forwarding from channel A to intermediate channel D.
- Add to it the "Keywords and stop words" filter of type "By text match" with the word `junction_bot` in mode "Stop matching messages" (`Останавливать подходящие сообщения`).
- Create a forwarding from C to B.
- Add to it the setting "Buttons → Add your own buttons" with the needed button.
- Create a forwarding from D to B.

Done!

### Replacement diagnostics (Диагностика замен)

More on debugging replacements: [here](/ru/documentation/troubleshooting#replace).

## Features mentioned
- Copy-only processing — all transformations require copy delivery, not native forward [doc]
- AI text transformation — free-form prompt rewrites/translates message text (ChatGPT integration) [doc]
- Add header / add footer text — prepend/append text (HTML allowed), line-break caveats [doc]
- Text trimming — cut long messages to N chars (0 = off; 150–1000 recommended) [doc]
- Text/link replacement rules — A→B (or empty), body+buttons only, ordered top-to-bottom, append-only list [doc]
- Regex replacements — RE checkbox, backreferences `$1`, `(?s)` modifier; commands `/replace`, `/replacerx` [doc]
- Add/remove formatting via HTML tags in replacements [doc]
- Premium emoji replacement — `<strong documentid=...>` tags, find via processing report [doc]
- Link to original post — none / full / custom text [doc]
- Auto-replace cross-links to source — smart replacement of all source links (plan-dependent) [doc]
- Source name header — none/simple/bold/from_only/id/date/custom HTML; `/setting header none` [doc]
- Author display — none/name/username/full/full_except_bot; fallback `User#123456`; `/setting author` [doc]
- Custom URL buttons — URL + text per line; copy_bot only, or account mode with Premium (rich message); `/setting mybuttons` [doc]
- Feedback (like) buttons — 1/2/custom words; copy_bot only; `/setting like` [doc]
- Watermarks — PNG, opacity, fit/cover/none scaling, alignment incl. random; images/video/animation (plan-dependent) [doc]
- Third-party bot chaining — route through other bots, tag with key, filter and strip key [doc]
- Intermediate channels — apply settings to a filtered subset via split forwardings [doc]
- Moderation mode for media replacement/manual editing [doc]
- Processing report debug setting — shows message source code [doc]

## Open questions / ambiguities
- Watermark opacity scale range is not specified.
- Example 11 (`.*` → empty) states text-only messages won't be forwarded — implies empty-after-replace messages are dropped; not stated explicitly as a general rule.
- Cross-link replacement and watermarks carry plan badges on the page — plan names omitted per instructions.
