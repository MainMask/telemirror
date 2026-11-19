# Delivery report "The message was not delivered because it was caught by a mustHave filter" (Отчет о доставке "Сообщение не было доставлено, потому что попало под mustHave фильтр")
- Source: https://www.junctionbot.io/ru/instructions/delivery-report-message-has-not-been-delivered-due-to-must-have-filter
- EN: https://www.junctionbot.io/instructions/delivery-report-message-has-not-been-delivered-due-to-must-have-filter
- Fetched: 2026-11-19, method: curl+html2md

## Content
Category: Instruction — Delivery report (Отчет о доставке)

(The RU page carries a banner: "This is an automatically translated version, so errors are possible".)

1. A message with a video arrives in the source chat.
2. We see that this message with the video did not arrive in the destination chat.
3. To get a delivery report for the message, first copy the link to the message in the source chat.
4. Enter the command `/track` in the chat with the bot.
5. The bot responds to the command. Paste the link to the message you just copied.
6. The message link has been added to the chat with the bot.
7. From the delivery report we see that the forwarded message contained a video. The forwarding settings have a filter (see the next screenshot) that allows only pictures, so the message was not delivered to the destination chat.
8. In the "Filters" (Фильтры) settings we see that an allowing filter "mustHave" — `<photo>` — is set, which allows forwarding only of messages with pictures. The filter worked correctly, so the message with the video did not arrive in the destination chat.

(Screenshots have no alt text.)

## Features mentioned
- /track command — paste a source message link to get a per-message delivery report explaining why it was/wasn't delivered [doc]
- mustHave filter — allowing (whitelist) filter; only messages matching it are forwarded [doc]
- Media-type tokens in filters — `<photo>` matches messages with pictures [doc]
- Delivery report shows message contents (e.g. media type) and the filter that blocked it [doc]

## Open questions / ambiguities
- Exact wording/format of the delivery report bot message is only shown in screenshots (not in text).
