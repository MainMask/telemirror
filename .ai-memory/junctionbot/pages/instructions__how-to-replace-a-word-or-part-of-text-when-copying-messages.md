# How to replace a word or part of the text when copying messages (Как заменять слово или часть текста при копировании сообщений)
- Source: https://www.junctionbot.io/ru/instructions/how-to-replace-a-word-or-part-of-text-when-copying-messages
- EN: https://www.junctionbot.io/instructions/how-to-replace-a-word-or-part-of-text-when-copying-messages
- Fetched: 2026-11-19, method: curl+html2md

## Content
Category tag: Instruction (Инструкция) · Moderation (Модерация)

### Steps
(Each step is a screenshot with a caption; screenshots have no alt text.)

1. Open the chat with Junction Bot and tap **Menu** (Меню).
2. Select the forwarding.
3. In the forwarding settings find the option "Replacements" (Замены) and tap it.
4. Enter into the "Source" (Источник) field the original value to be replaced, and into the "New value" (Новое значение) field what to replace it with.
5. To edit a replacement, tap the "Edit" (Редактирование) icon.
6. A message with the word "Биткоин" arrives in the source chat.
7. The replacement of this word, "Bitcoin", arrives in the destination chat.
8. The "RE" icon toggles using a regular expression in the replacement. More about using regular expressions [here](https://www.junctionbot.io/ru/documentation/message-processing#advanced-regex-examples).

## Features mentioned
- Replacements (Замены) — per-forwarding list of source value → new value text substitutions, editable [doc]
- Regex toggle "RE" — per-replacement switch to treat the source value as a regular expression [doc]

## Open questions / ambiguities
- Case sensitivity / whole-word matching for plain replacements not specified.
- Presumably requires a copy delivery mode (title says "when copying"), not stated explicitly.
