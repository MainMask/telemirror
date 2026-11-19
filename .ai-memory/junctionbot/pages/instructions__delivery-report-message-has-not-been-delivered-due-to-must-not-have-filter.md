# Delivery report. The message was not delivered because it was caught by a mustNotHave filter (Отчет о доставке. Сообщение не было доставлено, потому что попало под mustNotHave фильтр)
- Source: https://www.junctionbot.io/ru/instructions/delivery-report-message-has-not-been-delivered-due-to-must-not-have-filter
- EN: https://www.junctionbot.io/instructions/delivery-report-message-has-not-been-delivered-due-to-must-not-have-filter
- Fetched: 2026-11-19, method: curl+html2md

## Content
Category: Instruction — Delivery report (Отчет о доставке)

(The RU page carries a banner: "This is an automatically translated version, so errors are possible".)

1. A message arrives in the source chat (in our case, a picture). You noticed that this message did not arrive in the destination chat.
2. Copy the link to the message in the source chat that did not arrive in the destination chat.
3. Enter the command `/track` in the chat with the bot.
4. The bot responds to the command. Paste the link to the message you just copied.
5. The message link has been added to the chat with the bot.
6. We received the delivery report for this message: the forwarding settings had a filter forbidding pictures. And the message we are checking is a picture.
7. Indeed, the forwarding settings have a forbidding filter "mustNotHave" — `<photo>` — set, which prevents messages with pictures from arriving.

(Screenshots have no alt text.)

## Features mentioned
- /track command — per-message delivery report from a pasted source message link [doc]
- mustNotHave filter — forbidding (blacklist) filter; messages matching it are not forwarded [doc]
- Media-type tokens in filters — `<photo>` matches messages with pictures [doc]

## Open questions / ambiguities
- Exact text of the delivery report is only in screenshots.
