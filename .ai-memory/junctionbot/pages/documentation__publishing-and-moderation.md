# Publishing and moderation (Публикация и модерация)
- Source: https://www.junctionbot.io/ru/documentation/publishing-and-moderation
- EN: https://www.junctionbot.io/documentation/publishing-and-moderation
- Fetched: 2026-11-19, method: curl+html2md

## Content

### New! Moderation mode (Режим модерации)

[Available only on certain plans — depends on plan]

A long-awaited feature that lets you manually edit posts from the source before publishing them to the destination. It also lets you manually approve posts for publication or skip them. We call this **moderation mode** or **approval mode** (`режим одобрения`). How does it work?

[Instruction card] Instructions:
- [How to set up manual moderation via your own chat](/ru/instructions/how-to-set-up-manual-moderation-via-own-chat)
- [How to set up manual moderation via @Junction_Review_Bot](/ru/instructions/how-to-set-up-manual-moderation-via-junction-review-bot)

- Create a new forwarding.
- Enable moderation mode on the source.

**Where to find**

`Menu → My forwardings → Select a forwarding → Moderation → Moderation → "Moderate messages" → ON` (`Меню → Мои пересылки → Выберите пересылку → Модерация → Модерация → «Модерировать сообщения» → ВКЛ`)

- Now for each new post in the source, **your connected account** will send a copy of this post to the special bot @Junction_Review_Bot. Under such a post there will be info about the source and destination and the buttons "Publish" (`Опубликовать`) and "Skip" (`Пропустить`).
- Since the post is published on behalf of your account, you can edit it directly in the chat with @Junction_Review_Bot.
- If you want to publish the resulting post to the destination, press "Publish".

To disable moderation mode, use the same menu section.

#### Moderation in a group (Модерация в группе)

You can also send posts for approval to a group.

Open `Menu → My forwardings → Select a forwarding → Moderation → Moderation`, enable "Moderate messages", press "Select chat" (`Выбрать чат`) and choose a group (or create a new one). To return to moderation via the bot, press "Send to @Junction_Review_Bot" (`Слать в @Junction_Review_Bot`).

- Note that @Junction_Review_Bot and your connected account must be admins in this group.
- If the above conditions are not met, you will get the error `NO_ACCESS`.

`PLEASE NOTE:`

- You can still use any replacements and filters on the forwarding. They are applied before the post is sent for moderation.
- You can press "Publish" as many times as you want. Each time the system publishes the current version of the post to the destination.
- Enabling moderation mode automatically enables publishing on behalf of your account (copying) (see [publishing mode](/ru/documentation/publishing-and-moderation#publishing-mode)). This means the connected account must have posting rights in the destination. It also means buttons from the original post will not be passed.
- Edits from the source are not automatically propagated to the destination.

### Message delivery modes (Режимы доставки сообщений)

Account-based modes — available only on certain plans (depends on plan).

**Delivery on behalf of the bot / on behalf of the account**

Junction Bot can publish messages either **on behalf of the bot @junction_bot** itself or **on behalf of your connected account**.

**Publishing on behalf of the account** may be relevant if you forward to a group. Then messages come not from the bot but from your connected account (everyone sees your username and profile picture).

When you set up forwarding into users' private chats or into other bots, messages are automatically sent on behalf of your connected account. In this mode there is no need to add the bot to the destination chat.

**Copy / forward**

Also, when working via the connected account, two types of forwarding are possible — via Telegram's built-in **forward mechanism**, or **copying** the message. Copying creates a new message that is a clone of the existing one. With forwarding, the existing message is forwarded via Telegram's forward mechanism, keeping the name and link of the message source (author).

**`PLEASE NOTE!`**

- **When using forward, it is impossible to change the message in any way (add your text, use replacements, etc.).**
- Views of a copied message are counted separately and do not affect views of the source message. Views of a forwarded message do affect views of the message in the source.

**Where to find**

`Menu → My forwardings → Select a forwarding → Delivery mode` (`Режим доставки`)

- **Copy via bot** (`Копировать через бота`) — messages are copied and published via the bot @junction_bot. Both the bot and your account must be administrators in the destination; the bot must have posting rights.
- **Copy via account** (`Копировать через аккаунт`) — messages are copied and published via the connected account. The account must have posting rights in the destination.
- **Copy via account, on flood — via bot** (`Копировать через аккаунт, при флуде - через бота`) (only on the top plan — depends on plan) — messages are published via the connected account. The account must have posting rights in the destination. If the Telegram limit on the number of published messages is exceeded, an attempt is made to publish via the bot @junction_bot. For this to work the bot must be an administrator in the destination with posting rights.
- **Forward via account** (`Пересылать через аккаунт`) — messages are forwarded (using forward) via the connected account, keeping the link to the original message. The account must have posting rights in the destination. The source must allow forwarding messages.
- **Copy regular and forward forwards via account** (`Копировать обычные и пересылать форварды через аккаунт`) — keeps the structure of the original source unchanged: regular messages from the source are copied under the destination's authorship, while posts that were forwarded into the source chat appear as "**Forwarded from**" + **name and link of the source** (author). Note: if the source forbids forwarding messages, in "copy or forward client" mode they will be skipped and will not reach the destination.
- **Forward via account, on protection — copy** (`Пересылать через аккаунт, при защите - копировать`) — the bot tries to forward messages on behalf of the connected account (keeping the link to the original message). If the source forbids forwarding, the message is copied and published on behalf of the account.

In the modes "Copy via account" and "Forward via account":
- No need to keep the bot in the destination chat.
- Adding native buttons to the message is not supported. In "Copy via account" mode, if the connected account has Telegram Premium, the message is published as rich text, and buttons are shown within that advanced formatting (only link buttons supported). In "Forward via account" mode buttons are not added.

Also recall that Telegram lets you post anonymously in a group if your account is a group administrator. So if you choose forwarding or copying on behalf of the account and then set anonymity, messages forwarded by Junction Bot are published anonymously on behalf of the whole group.

This is configured in the Telegram client: `Group settings - Administrators - (Select administrator - your connected account) - Anonymity: On` (`Настройки группы - Администраторы - ... - Анонимность: Вкл.`)

### Delayed publication methods (Способы отложенной публикации)

Junction Bot offers two ways to postpone sending a message. The key difference is **the level of control** over the post after setting it:

- **Publication with delay (Bot queue)** (`Публикация с задержкой (Очередь бота)`): this method does not let you view or edit messages already waiting for publication.
- **Scheduling (Telegram Scheduler)** (`Планирование (Планировщик Telegram)`): uses Telegram's native scheduler. You get full control over scheduled posts: they can be viewed, edited and deleted.

#### Publication with delay (Публикация с задержкой)

This setting delivers messages with an additional delay after they appear in the source. Messages go into Junction Bot's internal queue and you **cannot view** or **edit** them anymore.

Suitable if your goal is to add a small (including random) interval between publication in source and destination, to imitate "human" forwarding or avoid instant copying.

**Where to find**

`Menu → My forwardings → Select a forwarding → Scheduling and publishing → Delay` (`Планирование и публикация → Задержать`) (the same delay with additional filters by reactions and views is in `Filtering → Reactions filter` / `Фильтрация → Фильтр по реакциям`)

**⚙️ Time settings:**

- **Fixed delay:** in the **"From"** (`«От»`) field specify how long after publication in the source the message should be published in the destination.
- **Random delay:** to delay by a random interval, specify the delay range in the **"From"** and **"To"** (`«До»`) fields.

**Important:** with this method you **cannot** affect messages already queued for publication (view, edit or cancel them).

#### Scheduling publications (Telegram Scheduler) (Планирование публикаций (Планировщик Telegram))

Similar to delay, but works via **Telegram's internal (native) scheduler**. You get full control over scheduled posts: view, edit, delete.

**How it works:** the bot does not send the message instantly, but adds it to Telegram's scheduled messages on your behalf. This is the same mechanism you use manually when pressing "Send later" (right click on desktop or long-press on mobile).

**Mandatory requirement:** for this feature to work, [publishing on behalf of the account](/ru/documentation/publishing-and-moderation#publishing-mode) (copy or forward mode) must be enabled.

**Where to find**

`Menu → My forwardings → Select a forwarding → Scheduling and publishing → Schedule ("deferred")` (`Запланировать ("отложка")`)

**⚙️ Managing scheduled messages in Telegram:** you keep full control over posts before publication:

- **View:** all scheduled messages can be seen by clicking the **calendar icon** in the bottom panel of your destination **channel** or **chat**.
- **Edit:** you can manually change the content (text, media) and publication time.
- **Delete:** any scheduled message can be cancelled.

**⚙️ Time settings in the bot:**

- **Fixed time:** in the **"From"** field specify for when (how many minutes/hours ahead) to schedule the message.
- **Random time:** to schedule for a random interval, specify the range in **"From"** and **"To"**.

### Pinning messages (Закрепление сообщений (pin))

**Where to find**

`Menu → My forwardings → Select a forwarding → Scheduling and publishing → Pin posts` (`Закреплять посты`)

**Available settings**

- `off` — do not pin
- `pass` — pin if the original is pinned
- `silent` — pin everything without notification
- `notify` — pin everything with notification (groups only; does not work in channels)

### Delivery frequency (Частота доставки)

**Where to find**

`Menu → My forwardings → Select a forwarding → Scheduling and publishing → Delivery frequency` (`Частота доставки`)

This setting spreads the message flow from a given source over time. E.g., with a period of 60 seconds, messages from the source arrive no more than once a minute. If the source publishes 3 messages at once at 16:30, the first arrives immediately (16:30), the second a minute later (16:31) and the third two minutes later (16:32). If a fourth message appears in the source at 16:31, it is published in the destination at 16:33.

Note that the period is **always** counted for each source separately. If you want the period counted for the whole destination, first set up forwarding into an intermediate channel, then from the intermediate channel to the final channel with the rate setting.

Important: this setting works via Telegram's internal scheduler (the one used for setting a deferred publication time). Therefore [publishing on behalf of the account](/ru/documentation/publishing-and-moderation#publishing-mode) (copy or forward) must be enabled.

To reset the period timer, set rate to 0.

### Silent mode (Тихий режим)

Any message will be delivered to the destination without sound. Your channel or group receives the notification as usual but silently, even if members forgot to enable "Do not disturb".

**Where to find**

`Menu → My forwardings → Select a forwarding → Scheduling and publishing → Silent mode` (`Тихий режим`)

**Available settings**

- `pass` — pass through the silent flag
- `never` — do not pass
- `always` — make all messages silent

### Link preview (Предпросмотр ссылок)

Link preview in Telegram shows the beginning of a web page under the message text. Junction Bot lets you choose whether this preview is shown in forwarded messages.

**Where to find**

`Menu → My forwardings → Select a forwarding → Other content → Link preview` (`Прочий контент → Предпросмотр ссылок`)

**Available settings**

- `pass` — pass the flag as in the source
- `never` — never show the preview
- `always` — always show the preview (if there is a link)

### Flood reaction (Реакция на флуд)

Flood is too large a flow of messages being published in the destination channel. By default Telegram allows publishing no more than 20–30 messages per minute; when this threshold is exceeded it simply blocks publishing new ones for some time. The bot will try to send the blocked message again later. **We know of no cases where Telegram banned bots or accounts for flood; the penalty is limited to a temporary posting ban.**

You can configure the system's reaction to a posting block in the destination:

**Where to find**

`Menu → My forwardings → Select a forwarding → Debug settings → Flood reaction` (`Отладочные настройки → Реакция на флуд`)

**Available settings**

- **Ignore message** (`Игнорировать сообщение`) — if messages arriving during the block are not that important, just ignore them; they will not be published.
- **Stop forwarding completely** (`Полностью остановить пересылку`) — in some scenarios it can be convenient to fully pause this forwarding when a posting ban occurs. The forwarding rule is paused until you turn it back on.
- **Postpone and deliver when possible** (`Отложить и доставить, когда получится`) — if the message must be published but a flood ban is active in the destination, the system waits for the ban to end and tries to publish again. This is the most convenient option and it is the default.
  However, if you have a very large message flow, postponed messages on publication will cause a repeated block, the number of postponed messages will grow, and at some point the system will have to ignore them.
- **Notify on flood ban** (`Уведомлять при флуд запрете`) — when a ban is received from Telegram, notify about it in the private chat with the bot.

To reduce the likelihood and consequences of flood blocks, you can also:

- Try setting up [sending on behalf of your account](/ru/documentation/publishing-and-moderation#publishing-mode). Limits should be softer in this mode.
- Use the [publish on behalf of the account, and via bot on flood](/ru/documentation/publishing-and-moderation#publishing-mode) mode. It is great for bypassing flood limits, achieving a posting rate of 40–60 messages per minute.
- Try [spreading publications over time](/ru/documentation/publishing-and-moderation#pub-frequency).
- Split traffic between several connected accounts.
- Consider splitting the destination channel into several.

## Features mentioned
- Moderation/approval mode — posts go to @Junction_Review_Bot with Publish/Skip, editable before publish; re-publish allowed (plan-dependent) [doc]
- Moderation in a group — approval chat of choice; bot + account must be admins, else NO_ACCESS [doc]
- Moderation forces account copy mode — original buttons dropped; source edits not propagated [doc]
- Delivery modes — copy via bot / copy via account / account-with-bot-fallback-on-flood / forward via account / copy regular + forward forwards / forward with copy fallback on protection [doc]
- Account delivery to private chats and other bots — automatic, no bot in destination [doc]
- Anonymous group posting via admin anonymity on connected account [doc]
- Publication delay (bot queue) — fixed or random From/To delay, not editable once queued [doc]
- Reactions/views filter with delay [doc]
- Scheduling via native Telegram scheduler — editable/deletable scheduled posts; fixed or random offset; needs account mode [doc]
- Pin posts — off/pass/silent/notify (notify groups only) [doc]
- Delivery frequency (rate) — min interval per source; 0 resets; via Telegram scheduler; needs account mode [doc]
- Silent mode — pass/never/always [doc]
- Link preview — pass/never/always [doc]
- Flood reaction — ignore / stop forwarding / postpone (default) / notify; Telegram limit ~20–30 msg/min; fallback mode 40–60 msg/min [doc]

## Open questions / ambiguities
- "Copy via bot" requires both bot and account to be admins in the destination — unusual requirement, stated as such.
- The "copy or forward client" internal name is mentioned for the mixed mode; other modes' internal names (except `copy_bot` on another page) are not given.
- Delay units/maximum for delay and scheduling are not specified on this page.
