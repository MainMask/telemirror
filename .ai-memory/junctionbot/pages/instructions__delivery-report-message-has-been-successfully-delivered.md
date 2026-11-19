# Delivery report "Message has been successfully delivered" (Отчет о доставке "Сообщение успешно доставлено")
- Source: https://www.junctionbot.io/ru/instructions/delivery-report-message-has-been-successfully-delivered
- EN: https://www.junctionbot.io/instructions/delivery-report-message-has-been-successfully-delivered
- Fetched: 2026-11-19, method: curl+html2md

## Content

Type: Instruction (`Инструкция`) · Category: Delivery report (`Отчет о доставке`)

(Banner: machine-translated version, errors possible. "Back to instructions" → /ru/instructions.)

You may also be interested in:
- [Instruction] [Delivery report "Message was not delivered because it hit a mustHave filter"](/ru/instructions/delivery-report-message-has-not-been-delivered-due-to-must-have-filter)
- [Instruction] [Delivery report. Message was not delivered because it hit a mustNotHave filter](/ru/instructions/delivery-report-message-has-not-been-delivered-due-to-must-not-have-filter)

Steps (each step is accompanied by a screenshot without meaningful alt text):

1. A message arrived in the source chat.
2. The message was forwarded to the destination chat.
3. To get a delivery report for the message, first copy the link to the message in the source chat.
4. Enter the command `/track` in the chat with the bot.
5. The bot responded to the command. Paste the link to the message you just copied.
6. The message link has been added in the chat with the bot.
7. The delivery report arrived. From the report we see that the message was published to the destination chat.

(Page ends with a "was this helpful" feedback widget — omitted.)

## Features mentioned
- `/track` delivery report — paste a source message link, bot replies with a per-message delivery report (delivered / filtered) [doc]

## Open questions / ambiguities
- The exact report format/fields are only shown in screenshots (no alt text), so the report contents are not captured in text.
