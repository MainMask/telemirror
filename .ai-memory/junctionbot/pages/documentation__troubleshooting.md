# Troubleshooting (Устранение неполадок)
- Source: https://www.junctionbot.io/ru/documentation/troubleshooting
- EN: https://www.junctionbot.io/documentation/troubleshooting
- Fetched: 2026-11-19, method: curl+html2md

Note on plans: the page distinguishes two plan families without prices. Below, "basic plans" = the two lower plans where delivery works through Junction's service user-bot (no account connection); "direct-connection plans" = the two higher plans where the user's own Telegram account is connected. "Lowest plan" = the cheapest one. Plan names omitted.

## Content

### Connection (Подключение)

#### Telegram authorization code does not arrive (Не приходит код авторизации Telegram)

- **Check Telegram:** the authorization code comes inside Telegram itself, not as SMS. Open Telegram and look for a message from the official Telegram account — sometimes the code arrives without a separate notification and the chat does not jump to the top of the list.
- **Wait a bit:** Telegram may sometimes delay sending the code to third-party clients. Wait a few minutes and check again.
- **Check the number's usage history:** make sure this number was not used in the bot before. It may already be bound to another account. Then log in to the bot under the other account, and in the personal account (`Личный кабинет`) you will be able to transfer the number.

#### Unknown device connected to the account (Неизвестное устройство подключилось к аккаунту)

If this warning appeared right after initiating the [account connection](/ru/documentation/getting-started#direct-connection), no need to worry. In this mode the bot connects to your account as a regular Telegram client, and Telegram issues the standard new-login warning.

#### I accidentally deleted the session with the bot (Я случайно удалил сессию с ботом)

Deleting the session with the bot loses the ability to receive and send messages. To restore:

- Open the mini-app (the Menu button in the chat with the bot).
- Go to the Personal account (`Личный кабинет`).
- Tap the **Reconnect** (`Переподключить`) link next to the number you want to reconnect.
- Follow the bot's instructions: it will guide you through reconnection.

#### Why is there a "Junction Bot Service Channel" in my feed? (Откуда в моей ленте канал Junction Bot Service Channel?)

This channel was created by the bot; it is needed for service messages. Do not delete it! To keep it out of the way, you can archive it.

#### I changed my Telegram account and want to transfer settings (Я поменял аккаунт Телеграм и хочу перенести на него настройки и баланс)

Contact support and give the username or ID of your new account. They will help transfer all your settings to the new account. [payment-related content omitted]

#### I want to change the direct-connection number (Я хочу сменить номер прямого подключения)

Open **`Menu → Personal account`** (`Меню → Личный кабинет`), tap the edit icon [📝] on the card of the package the number is connected to, and choose "Change the number of the connected account" (`Поменять номер подключенного аккаунта`). Number change is available only on direct-connection plans (depends on plan).

[Instruction card] Instruction: [How to change the connected account number](/ru/instructions/how-to-change-connected-account)

### Forwardings (Пересылки)

#### Forwarding disables itself (Пересылка сама отключается)

If a forwarding unexpectedly turns off, the problem may be:

- **Lost access to the source:** make sure the bot still has access to the source the messages come from.
- **Large message flow:** if there are too many messages, Telegram's [flood control](/ru/documentation/troubleshooting#ts-flood) may trigger. In the [flood reaction settings](/ru/documentation/publishing-and-moderation#ts-flood) you can change the bot's behavior in this scenario.

#### Forwarding stuck in "connecting" state (Пересылка зависла в состоянии подключения)

Everything in this section is relevant only for basic plans. Plans working via account connection (direct-connection plans) cannot have such problems.

If your source is used for the first time in the system, it may take some time to connect to it. Then you will see this status on the forwarding page. It is a one-time delay; after connection, messages arrive instantly.

A source may also go into "connecting" status if the bot lost access to it — e.g. the invite link stopped working or the source admin blocked the bot. Such sources can be used only on direct-connection plans.

If the forwarding stays in "connecting…" (`«подключение…»`) for more than a day:

- **Re-create the forwarding:** delete the current forwarding and create it again.
- **Check the service user-bot status:** if the source is yours, make sure our service user-bot is not blocked in your channel. This account joins the channel when the forwarding is created and is required for delivery on basic plans.

If "(expired)" is appended to the channel name, the link no longer works. Maybe it was deleted by the admin, or the bot was blocked in that channel.

#### I don't see the needed channel in the list when creating a forwarding (При создании пересылки я не вижу нужного канала в списке)

Close the Junction Bot mini-app, pin the needed channel in your Telegram chat list, wait a few minutes, then open the app and repeat creating the forwarding. If the channel still does not appear, enter its username manually in search. The same trick works for the destinations list: make sure you are a member of that chat, pin it, and retry the selection after a few minutes.

#### I want to transfer settings or replace a source (Хочу перенести настройки или заменить источник)

- With `/dump` you can export as a file all current subscriptions, forwardings and related settings. The file is a list of commands for the bot, so you can edit or save your settings. To execute some or all of these commands at once, use `/batch`: send the bot a list of commands starting with `/batch`, each line a separate command. Note: when you send Telegram a too-long text, it is split into several messages; the bot processes only commands in the first message (starting with `/batch`). For a very long list, send it in several messages, each starting with `/batch`.
- You can also copy all filters from another channel, using the command format: `/filter <link_where_to_copy> addAllFrom <link_to_source>` (`/filter ссылка_куда_копировать addAllFrom ссылка_на_источник`)
- To fully transfer settings to another account, contact support.

### History copying (Копирование истории)

[Instruction card] Instruction: [How to copy old messages from any Telegram chat](/ru/instructions/how-to-copy-old-messages-from-any-telegram-channel-or-group)

If history copying seems "stuck", it means your account exceeded Telegram's limit on downloading or uploading content. Steps you can take:

- Make sure that on mobile devices connected to this account **automatic media download is disabled** in Telegram settings (**Settings -> Data and Storage -> Automatic media download**). This setting makes your account spend its download limits even when you are not using it.
- **Pause all activity on the account for 12 hours.** That means not opening Telegram on any device, not reading any messages, etc. Then start copying only the problematic message (specifying only its number at the second step of the wizard).
- You can **buy Telegram Premium** for the connected account. This increases download/upload limits, but does not guarantee a solution if your traffic is still too large.

If copying is running but not all messages arrive, you can check the reason with the [`/track` command](/ru/documentation/troubleshooting#delivery-tracking).

[Instruction cards]:
- [Delivery report. Message has been successfully delivered.](/ru/instructions/delivery-report-message-has-been-successfully-delivered)
- [Delivery report. Message was not delivered because it hit a mustHave filter](/ru/instructions/delivery-report-message-has-not-been-delivered-due-to-must-have-filter)
- [Delivery report. Message was not delivered because it hit a mustNotHave filter](/ru/instructions/delivery-report-message-has-not-been-delivered-due-to-must-not-have-filter)

### Delivery (Доставка)

#### Messages arrive with a delay (Сообщения приходят с задержкой)

**On the lowest plan:**

- Delivery from public channels usually takes up to an hour, but sometimes may take longer.

**On the other (higher) plans:**

- Delivery is instant. If there is a noticeable delay, use `/track` to find the cause. Besides a delivery report, the bot runs diagnostics and re-tunes the forwarding, which may fix the problem.
- If the source has copy protection, the bot has to fully process the protected media file, which takes some time depending on file size.

#### Messages don't arrive at all (Сообщения вообще не приходят)

- **Check the delivery report:** use `/track` to find the cause. In 99% of such cases the message turns out to be filtered by your own filter or another setting.
- **Check the forwarding status:** open the problematic forwarding in the app to make sure it is enabled.
- **Check the account status:** open the personal account (`Menu → Personal account`) to make sure your account is connected to the bot and active.
- [payment-related content omitted — a check that the account was not disabled for billing reasons]
- **Check the account hasn't left the source channel:** make sure the connected account is still a member of the source channel and has access to messages.

The message may have been edited shortly after publication. If the original message did not pass your filters, the bot cannot pass the edit either.

**On the lowest plan:**

- Most likely the problem is the [delay](/ru/documentation/troubleshooting#messages-arrive-with-delay) or a too-large message from a protected channel.

**On direct-connection plans:**

- If the previous steps didn't help, write to the support chat.

#### Too large a message flow in the destination (flood) (Слишком большой поток сообщений в назначении (флуд))

Delays may be caused by a too-high publishing rate in the destination channel. By default Telegram allows publishing no more than 20–30 messages per minute; above this threshold it simply blocks publishing new ones for some time. The bot will try to send the blocked message again later. **We know of no cases where Telegram banned bots or accounts for flood; the penalty is limited to a temporary posting ban.**

You can configure the reaction to posting blocks in the destination: [`Menu → My forwardings → Select a forwarding → Debug settings → Flood reaction`](/ru/documentation/publishing-and-moderation#ts-flood) (`Отладочные настройки → Реакция на флуд`).

To reduce the likelihood and consequences of flood blocks:

- Try [sending on behalf of your account](/ru/documentation/publishing-and-moderation#publishing-mode). Limits should be softer in this mode.
- Use the [account publishing with bot fallback on flood](/ru/documentation/publishing-and-moderation#publishing-mode) mode. Great for bypassing flood limits, reaching 40–60 messages per minute.
- Try [spreading publications over time](/ru/documentation/publishing-and-moderation#pub-frequency).
- Split traffic between several connected accounts.
- Consider splitting the destination channel into several.

#### Duplicate messages arrive (Приходят дубли сообщений)

Sometimes a source admin publishes a message twice by mistake and then deletes one of the duplicates. But the bot may already have passed both messages.

If you face duplicates:

- **Enable the duplicates filter:** in forwarding settings, group "Filtering" (`Фильтрация`), set "Duplicates filter" (`Фильтр дублей`) to `filter`. This helps eliminate repeated messages.
- **Enable "Pass deletions"** (`Передавать удаления`) (direct-connection plans only): in group "Scheduling and publishing", set "Pass deletions" to `yes`.
- **Check "Pass edits"** (`Передавать правки`) (direct-connection plans only): make sure "Pass edits" (group "Scheduling and publishing") is not set to `new`. In this mode the bot re-sends every edited version of the message, even for minor edits.
- If the duplicates filter is on and duplicates still pass, the messages may not be identical. Look at their [source code](/ru/documentation/troubleshooting#source-code) and compare the composition of the messages in the received reports.

#### Messages come from the bot, but I want them from the group (Сообщения приходят от бота, а хочу от группы)

To enable forwarding on behalf of your account on an existing redirection:

- Switch the [Delivery mode](/ru/documentation/publishing-and-moderation#publishing-mode) in settings to **Copy via account** (`Копировать через аккаунт`). Messages will then be published on behalf of your account.
- If you want messages published on behalf of the group, enable "Anonymity" (`Анонимность`) in the group's administrator settings.

### Content (Контент)

#### Messages arrive differently from the source (Сообщения приходят не как в источнике)

##### Replacements (Замены)

First check whether the message is being modified by replacement rules you configured yourself. Delete all replacement rules and check whether the message arrives correctly. Another way to check without deleting the rules is to create another redirection (to a different destination).

##### Edits (Редактирования)

Sometimes a source message is edited after publication. The bot may copy the message before the admin edits it, so the first version lands in the destination. Edited messages sometimes even lack an "edited" mark. If the source post contains text with a picture but you received only text — most likely this is the cause.

On direct-connection plans you can [pass edits](/ru/documentation/forwarding#fw-edits) of source messages (enabled by default).

It may also be that the original message passed your filters but the edit did not. Then the message will not be changed.

Sometimes a channel publishes a message twice by mistake and then deletes one. With the duplicates filter on, only the first passes. If the admin then deletes the first and edits the second, the edit will not pass.

#### Premium features are not passed (Не передаётся премиум-функционал)

The bot cannot publish one-to-one messages with premium features such as premium emoji and long captions. E.g., if the channel author published a picture with a caption longer than 1024 characters, the bot has to trim it, since regular bots may publish captions no longer than 1024.

The premium problem can be fixed with a direct connection. To forward messages with premium emoji and long captions:

- **You need a direct-connection plan** (depends on plan).
- **Direct connection:** make sure account connection is set up.
- **Premium subscription:** your connected account must have an active Telegram Premium subscription.
- **Delivery mode:** enable [delivery on behalf of the account](/ru/documentation/publishing-and-moderation#publishing-mode) (Copy via account).

#### Messages arrive with truncated text (Сообщения приходят с обрезанным текстом)

If messages are truncated, the cause may be the message length limit for regular accounts. In Telegram the caption length limit for Premium accounts is four times larger. To forward long messages published by Premium users you need a direct-connection plan (depends on plan). Your connected account also needs Premium, and the [delivery mode](/ru/documentation/publishing-and-moderation#publishing-mode) must be on behalf of the account (Copy via account).

If your connected account already has Premium but text is still shortened, most likely publishing on behalf of the account is not enabled.

#### Messages arrive without pictures (Сообщения приходят без картинок)

Make sure the redirection parameter "[Media caption](/ru/documentation/forwarding#fw_caption)" (`Подпись к медиа`) is set to `caption_name`.

#### Messages arrive without buttons (Сообщения приходят без кнопок)

- **Check the "Copy buttons" setting (group "Buttons")** (`Копировать кнопки`, group `Кнопки`): make sure [Copy buttons](/ru/documentation/forwarding#fw-buttons) is enabled. It determines whether buttons from the original message are copied.
- **Delivery mode:** Telegram allows publishing messages with buttons only to bots. If you have a direct connection, switch the redirection to [delivery on behalf of the bot](/ru/documentation/publishing-and-moderation#publishing-mode) (Copy via bot).

These steps ensure correct copying and forwarding of messages with buttons.

### Filters (Фильтры)

#### How to figure out why filters don't work as I want? (Как разобраться, почему фильтры не работают, как я хочу?)

If a message did not pass because of a specific filter, you can see this in [delivery tracking](/ru/documentation/troubleshooting#delivery-tracking) and in the [processing report](/ru/documentation/troubleshooting#processing-report).

To better understand how your regex filters work, see [here](/ru/documentation/troubleshooting#regex).

If that didn't help, ask support for help. Your request must contain the [delivery report](/ru/documentation/troubleshooting#delivery-tracking) for the problematic message, including its [source code](/ru/documentation/troubleshooting#source-code).

### Replacements (Замены)

#### How to figure out why replacements don't work as I want? (Как разобраться, почему замены не работают, как я хочу?)

If it's hard to understand why your replacement rules don't work, try this procedure.

[Instruction card] Instruction: [How to replace a word or part of text when copying messages](/ru/instructions/how-to-replace-a-word-or-part-of-text-when-copying-messages)

Check the current replacement rules and whether they are correct in `Menu → My forwardings → Select a forwarding → Text processing → Replace links and words in text` (`Обработка текста → Замена ссылок и слов в тексте`).

If nothing looks suspicious, look at the [message source code](/ru/documentation/troubleshooting#source-code). That is exactly how the bot sees the message before applying replacement rules. Usually this shows why your rule is not applied.

If that didn't help, ask support. Your request must contain:

- The **forwarded** (native-forwarded) message from the source.
- The source code of this message.
- If you use regular expressions — a link to a [regex101.com](https://regex101.com/) project containing the message body and the regex you are trying to fix. See more [here](/ru/documentation/troubleshooting#regex-debug).
- The **forwarded** (native-forwarded) message from the destination.

Questions about non-working regex replacements will not be considered by support without this information.

### Delivery and processing reports (Отчёты о доставке и обработке)

#### Delivery tracking (Отслеживание доставки)

[Instruction cards]:
- [Delivery report. Message has been successfully delivered.](/ru/instructions/delivery-report-message-has-been-successfully-delivered)
- [Delivery report. Message was not delivered because it hit a mustHave filter](/ru/instructions/delivery-report-message-has-not-been-delivered-due-to-must-have-filter)
- [Delivery report. Message was not delivered because it hit a mustNotHave filter](/ru/instructions/delivery-report-message-has-not-been-delivered-due-to-must-not-have-filter)

The `/track` command launches a wizard that helps find out why a message did not arrive or arrived late. We recommend trying this before anything else.

#### Processing report (Отчёт по обработке)

If `/track` didn't help, enable the processing report:

**Where to find**

`Menu → My forwardings → Select a forwarding → Debug settings → Processing report` (`Отладочные настройки → Отчет об обработке`)

For each new message it sends a report explaining in detail why the message did not arrive. If you don't understand how to read the report or fix the filter, contact the support chat.

#### Source code (Исходный код)

A message's source code is how the bot sees the message when applying replacements or filters. It is very useful for debugging settings. Ways to get it:

- `/track`, besides the delivery report, also shows the message source code.
- The [processing report](/ru/documentation/troubleshooting#processing-report) contains the source code. The downside is that report generation must be enabled in advance, before the message arrives. Enable at `Menu → My forwardings → Select a forwarding → Debug settings → Processing report → ON`. After enabling, wait for a new message in the source; you receive the report together with the message.
- Send the message to the bot @junction_helper0_bot. You can forward messages to it directly from the source. It replies with the source code of the message.

### Regular expressions (Регулярные выражения)

#### Composing (Составление)

Regular expressions are a vast topic. Help in this area is beyond the bot administration's capacity. **Please do not DM the admins asking them to compose a replacement rule or filter for you.** The bot administration also does not provide such help in the support chat.

The easiest way to get the regex you need is to ask [ChatGPT](https://chat.openai.com/). It's an expert!

You can also turn to relevant forums, e.g. [StackOverflow (RU)](https://ru.stackoverflow.com/questions/tagged/регулярные-выражения), [CyberForum](https://www.cyberforum.ru/javascript-regexp/) or [RuBoard](http://forum.ru-board.com/topic.cgi?forum=33&topic=0472&start=40).

#### Debugging (Отладка)

For regex debugging we recommend [https://regex101.com](https://regex101.com/). Set Flavor to **"Java 8"** and tick the flags **"Single line: Dot matches the new line"** and **"Global: Don't return after first match"**. This makes it behave the same as Junction Bot.

You can get the message source text for debugging via [delivery tracking](/ru/documentation/troubleshooting#delivery-tracking).

### Advanced questions (Продвинутые вопросы)

#### Can I receive messages from the bot via Webhooks or API? (Могу ли я получать сообщения от бота через Webhooks или API?)

Sometimes you need to receive Telegram messages on your own API. The first idea developers have is to use a REST-style HTTP endpoint receiving requests from the bot in some format like JSON.

We strongly do not recommend this approach and deliberately do not add this feature. Such requests tend to get lost or arrive multiple times due to various network issues. As your system evolves, you will need to "replay" call history, view call logs for debugging, etc. Such functionality would require building a separate product on our side.

For such tasks we recommend a message-queue architecture. And since we already have a ready messenger, why not use it? Just create your own simplest bot (takes 15 minutes) and set up forwarding from the needed source directly into this bot. This gives an extremely reliable, future-proof system.

#### Could you add some feature? (Не могли бы вы добавить кое-какую функцию?)

Of course! Most current features were created at users' requests. The feature you want may already be planned. Write to us!

## Features mentioned
- Account connection via Telegram login code (code in Telegram app, not SMS); number transfer between bot accounts [doc]
- Reconnect session — Personal account → Reconnect next to the number [doc]
- Service channel — "Junction Bot Service Channel" auto-created for service messages [doc]
- Change connected number — via package card edit icon (plan-dependent) [doc]
- Forwarding auto-disable — on lost source access or flood (configurable) [doc]
- "Connecting…" status and "(expired)" marker for basic-plan sources via service user-bot [doc]
- Chat picker workaround — pin chat in Telegram, wait, or type username [doc]
- `/dump` + `/batch` settings export/import [doc]
- `/filter <dst> addAllFrom <src>` — copy all filters from another channel [doc]
- History copying troubleshooting — download limits, 12h pause, single-message retry in wizard step 2 [doc]
- `/track` delivery-tracking wizard — reason for non-delivery/delay, auto-diagnostics and re-tuning, shows source code [doc]
- Processing report — per-message debug report incl. source code (must be enabled in advance) [doc]
- @junction_helper0_bot — returns source code of forwarded messages [doc]
- Delivery latency — lowest plan up to ~1h from public channels; others instant; protected-media processing adds time [doc]
- Flood guidance — 20–30 msg/min Telegram limit, 40–60 with fallback mode, split accounts/channels [doc]
- Duplicates filter (`filter`), pass deletions (`yes`), pass edits (`new` re-sends every edit) [doc]
- Premium content passthrough — premium emoji/long captions (>1024) need direct connection + Premium + copy via account [doc]
- Media caption setting `caption_name` — fixes missing pictures [doc]
- Copy buttons setting — original buttons only in copy via bot [doc]
- Regex semantics — Java 8 flavor, single-line (dot matches newline), global [doc]
- No webhooks/API by design — recommend forwarding into your own bot as a message queue [doc]

## Open questions / ambiguities
- "Pass edits" values other than `new` are not listed here (see forwarding doc `#fw-edits`).
- Media caption values other than `caption_name` not listed here (see forwarding doc `#fw_caption`).
- Regex "Single line" flag implies `.` matches newlines by default, which conflicts with message-processing example 16 saying `.*` covers at most one line and needs `(?s)` — ambiguous.
