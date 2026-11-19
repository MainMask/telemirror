# Junction Bot — Glossary

Alphabetical. Feature IDs refer to `features.md`. Derived from `pages/*.md`; RU labels as shown in the product UI/docs.

| Term (EN) | RU label used in product | Definition | Related feature IDs |
|---|---|---|---|
| Active prompt | Активный промпт | The single AI prompt currently applied to a forwarding; block hidden when none | AI-02, AI-03 |
| Add header | Добавлять заголовок | Custom text/HTML prepended to the message text (not the same as Source name) | PROC-02 |
| Add text after message (footer) | Добавлять текст после сообщения | Custom text/HTML appended to the message (signature) | PROC-03 |
| Advanced filters add-on | Продвинутые фильтры | Add-on (also in "Business" package) unlocking word-form and delayed filters; without it those filters are ignored | FLT-05, FLT-07 |
| after ai / after reception / after replacements | Порядок фильтрации | Values of Filtering order: when filters run relative to replacements and AI | FLT-09 |
| AI processing | ИИ обработка текста / ИИ обработка (ChatGPT и другие) | LLM rewrite of message text per a prompt; text only, copy mode only | AI-01 |
| AI usage mode | Бесплатный режим / Оплата с баланса / Использовать свой API ключ | Global choice of how AI calls run: free quota, platform balance, own OpenAI/OpenRouter key | AI-05, DIG-16 |
| All other topics | Все остальные темы | Catch-all topic-mapping row: every topic without explicit mapping, incl. topics created later | TOP-02 |
| All topics | Все темы | Default topic-mapping row (or digest topic selector) covering all topics; becomes "All other topics" once explicit rows exist | TOP-02, DIG-10 |
| Allowing filter (mustHave) | Разрешающий фильтр / Пропускать подходящие сообщения | Filter that passes only matching messages; several of one type are OR'ed | FLT-02 |
| Author | Автор | Source-info setting showing the original sender (none/name/username/full/full_except_bot) | PROC-13, FLT-10 |
| Blocking filter (mustNotHave) | Запрещающий фильтр / Останавливать подходящие сообщения | Filter that stops matching messages; any match stops | FLT-02 |
| caption_name / separate / text_only | Подпись к медиа | Media caption modes: one message with name+link / media and text split / text only | PROC-16 |
| Closed source | Закрытый источник | Private chat/channel without invite link, bot, or personal chat; needs connected account | FWD-02, ACC-01 |
| Clone forwarding | Клонировать на другой источник / назначение | Copy a forwarding with all settings to a different source or destination | UI-10 |
| Comments | Комментарии | Channel comments (discussion group); copied as separate posts or as comments | FWD-16 |
| Connected account | Подключенный аккаунт | User Telegram account the bot logs into as a client to read sources and publish | ACC-01, ACC-03 |
| connecting… | подключение… | Forwarding status on basic tiers while the service user-bot joins/accesses a source | ACC-08, DIAG-08 |
| Consider past digests | Учитывать прошлые дайджесты | Number (0–10) of previous generations given to the AI to avoid repeats | DIG-07 |
| Copy (copy mode) | Копировать | Delivery that creates a new cloned message; allows all processing; separate view count | FWD-07, PUB-01 |
| Copy by script | Копировать по сценарию | History-copy mode replaying a chat with matching connected accounts and original pauses | HIST-07 |
| Copy old messages | Скопировать старые сообщения | Start history copy on an existing configured forwarding | HIST-08 |
| Copy topic structure | Скопировать структуру тем | Bot creates same-named topics in destination and maps them 1:1 | TOP-03 |
| copy_bot / copy_client / forward_client | Копировать через бота / Копировать через аккаунт / Пересылать через аккаунт | Internal identifiers of delivery modes cited in docs | PUB-01 |
| Creativity / Temperature | Креативность / Температура | LLM sampling temperature (digests 0–2 step 0.1; default/recommended 0.7) | AI-04, DIG-06 |
| Delay (bot queue) | Задержать / Публикация с задержкой (Очередь бота) | Fixed or random delay before publishing; queued posts can't be edited | PUB-04, FLT-07 |
| Delayed filter | Отложенный фильтр / Фильтр по реакциям | Delay plus condition (min reactions/views/forwards/replies or ratios) checked before publishing | FLT-07, FLT-08 |
| Delivery frequency | Частота доставки | Minimum interval between posts from one source (Telegram scheduler; account mode) | PUB-06 |
| Delivery mode | Режим доставки | Who publishes (bot/account) and how (copy/forward/hybrids) | PUB-01 |
| Delivery report | Отчет о доставке | /track output explaining a message's fate (delivered / blocked by mustHave / mustNotHave) | DIAG-01, DIAG-02 |
| Destination | Назначение / Куда | Chat receiving forwarded messages (bot chat, channel, group, user, bot, Max) | FWD-04 |
| Digest | Дайджест | Scheduled or instant AI summary of messages from several sources | DIG-01 |
| Digest type / Template | Тип дайджеста / Шаблон | Prompt set defining digest structure; library or personal | DIG-05, DIG-06 |
| Duplicate filter | Фильтр дублей | pass/filter/only_duplicates on identical source messages (last 300, 24 h reset) | FLT-15 |
| Engagement score | engagement_score | Digest metadata: reactions+comments relative to views | DIG-08 |
| Error handling (history) | Спросить / Пропустить сообщение / Подождать и повторить попытку | Policy for failed messages during history copy: Ask / Skip / Wait and retry | HIST-05 |
| Every n-th message filter | Фильтр каждого n-го сообщения | `/filter <src> every N` | FLT-14 |
| (expired) | (expired) | Suffix on a source whose invite link died or where the bot was blocked | DIAG-08 |
| Feed | Лента | Chat aggregating posts from many sources; also the user's own bot chat | TOP-09, TOP-10 |
| Feedback buttons | Кнопки обратной связи | Like-style buttons (1, 2, custom words); copy_bot only | PROC-15 |
| Filter forwarded messages | Фильтровать пересланные сообщения / пересылки | all / direct only / forward only | FLT-13 |
| Filter my messages | Фильтр моих сообщений | pass/filter messages from the connected account | FLT-11 |
| Filtering order | Порядок фильтрации | Position of filters in pipeline vs replacements and AI | FLT-09 |
| Flood | Флуд | Too many posts into a destination (~20–30/min) → temporary Telegram posting block | PUB-10, PUB-11 |
| Flood reaction | Реакция на флуд | Ignore / Stop forwarding / Postpone (default) / Notify on flood ban | PUB-10 |
| Folder | Папка | Telegram chat folder used as one source; only explicitly listed chats count | TOP-07, TOP-08 |
| Forward (native forward) | Пересылать | Telegram forward keeping origin name/link; no modification possible | FWD-07, PUB-01 |
| Forward deletions | Передавать удаления | Delete copies when original deleted (yes/no; bot 48 h limit) | FWD-10 |
| Forward edits | Передавать правки | Propagate source edits: edit / new / ignore | FWD-09 |
| Forwarding | Пересылка | Core rule: one source → one destination with settings | FWD-01 |
| Forwarding type | Тип пересылки | New messages (Новые сообщения) vs Old messages (history) (Старые сообщения (история)) | UI-02, HIST-01 |
| General / Main topic | Главная тема / Общая тема / General | Default topic of a forum group; default mapping target | TOP-02 |
| Generation | Генерация | One digest production (scheduled, instant or preview); counted against quota | DIG-16, AI-07 |
| Google Drive saving | Сохранять на Google Диск | Archive text/media to Drive, links sent instead; can send nothing to destination | INT-01 |
| History copying | Копирование истории / старых сообщений | Copying already published messages (dates become current) | HIST-01 |
| Instant digest | Мгновенный дайджест (вручную) | Manually triggered, unlimited digest | DIG-03 |
| Interval type | Тип интервала | History range: All messages / Message numbers / Publication time | HIST-02 |
| Junction Bot Alerts | @junction_ctrl_bot | Separate bot for system notifications | DIAG-07 |
| Junction Bot Service Channel | Junction Bot Service Channel | Auto-created service channel on the connected account; never delete | ACC-07 |
| Junction Bro | @junction_bro_bot | AI help bot trained on docs | DIAG-10 |
| Link preview | Предпросмотр ссылок | pass / never / always | PUB-09 |
| Link to original post | Ссылка на оригинальный пост | none / full / custom text hiding the link | PROC-11 |
| Managing account | Управляющий аккаунт | Account that talks to the bot, owns settings; can manage many connected accounts | ACC-03 |
| Media caption | Подпись к медиа | How media captions are transferred | PROC-16 |
| Media-type token | `<photo>`, `<video>`, … | Pseudo-text appended to message text so filters can match media kinds | FLT-12 |
| Moderation (approval mode) | Модерация / режим одобрения / Модерировать сообщения | Hold each post for manual Publish/Skip (and editing) before publishing | MOD-01…05 |
| mustHave / mustNotHave | mustHave / mustNotHave | Allowing / blocking filter keywords (also in commands) | FLT-02, CMD-06 |
| My prompts | Мои промпты | User-created or edited AI prompts | AI-02 |
| My templates | Мои шаблоны | User's digest templates | DIG-05 |
| NO_ACCESS | NO_ACCESS | Error when review bot / account aren't admins in the moderation chat | MOD-02 |
| Notification buttons (hidden continuation) | Кнопки с уведомлениями / Скрытое продолжение | Callback buttons with pop-up text; bot presses and transfers text | FWD-13 |
| Open source | Открытый источник | Public chat or private chat with working invite link | FWD-02 |
| Pin posts | Закреплять посты | off / pass / silent / notify | PUB-07 |
| Preview (digest) | Предпросмотр дайджеста | Test generation for a period before scheduling | DIG-13 |
| Processing report | Отчет об обработке | Debug setting sending a per-message report with source code | DIAG-03 |
| Project | Проект | Group of forwardings and digests; "Project #1" default | PROJ-01…04 |
| Prompt library | Библиотека промптов | Ready AI prompt templates (e.g. Ad check, Potential client detection) | AI-02, AI-08, AI-09 |
| Protected source | — (RU label not given; "защищённые" in text) | Chat with copying/forwarding disabled by admins; copied by re-processing | FWD-19 |
| Publication place | Место публикации | Digest target: bot chat or external chat, as bot or account | DIG-12 |
| Publication time | Время публикации | Digest schedule or instant mode | DIG-11 |
| Reconnect | Переподключить | Restore a broken connected-account session | ACC-06 |
| Remove safe pause | Убрать безопасную паузу | History-copy option disabling throttle (flood risk) | HIST-04 |
| Replace cross-links with source | Заменять кросс-ссылки на источник | Automatic rewrite of all links to the source (Expert) | PROC-10 |
| Replacement | Замена ссылок и слов в тексте / Замены | Ordered A→B text rule (RE checkbox for regex) on body and buttons | PROC-05, PROC-06 |
| Review bot | @Junction_Review_Bot | Default bot/chat ("Reviews") where moderation copies arrive with Publish/Skip | MOD-01 |
| Schedule ("deferred") | Запланировать ("отложка") | Put posts into Telegram's native scheduled messages (account mode) | PUB-05 |
| Service user-bot | — (RU label not given) | Junction's own account that joins sources on no-account tiers | ACC-08 |
| Silent mode | Тихий режим | pass / never / always notification-less delivery | PUB-08 |
| Source | Источник / Откуда | Chat (or folder) messages are taken from | FWD-02, FWD-03 |
| Source code (of a message) | Исходный код | HTML-like representation the bot uses for filters/replacements | DIAG-04 |
| Source name | Название источника | Header with source info: none/simple/bold/from_only/id/date/custom | PROC-12 |
| Stories | Истории | Story transfer: message / ignore (Expert) | FWD-15 |
| Suspended | Приостановлен | Digest status after critical error (quota, session, slot, API key) | DIG-14 |
| Sync topics automatically | Синхронизировать темы автоматически | Auto-create/rename destination topics (Expert) | TOP-06 |
| Table view | Табличный вид | Forwardings list with columns, filters, sorting, tabs | UI-06 |
| Text trimming | Обрезка текста | Shorten text to N chars (0 = off) | PROC-04 |
| Topic mapping | Сопоставление тем | Source topic → destination topic routing table | TOP-01 |
| /track | /track | Command starting the delivery-tracking wizard | DIAG-01, CMD-01 |
| Watermark | Водяной знак / ватермарка | PNG overlay on images/video/animation with opacity, scaling, alignment | PROC-17, PROC-18 |
| Web app | Веб-приложение | Mini-app opened in a browser window | UI-08 |
| Word-form filter | По словоформам | Morphological match (RU/EN/UK/DE) via add-on | FLT-05 |
