# How to change the phone number of the connected account (Как поменять номер подключенного аккаунта)
- Source: https://www.junctionbot.io/ru/instructions/how-to-change-connected-account
- EN: https://www.junctionbot.io/instructions/how-to-change-connected-account
- Fetched: 2026-11-19, method: curl+html2md

## Content
Category: Instruction — Account (Аккаунт)

(The RU page carries a banner: "This is an automatically translated version, so errors are possible".)

1. Open the chat with Junction Bot and tap **Menu** (**Меню**).
2. Tap the app menu icon.
3. Go to the **My account** (**Мой аккаунт**) section.
4. Go to plan **editing** (**редактирование** тарифа). [payment-related content omitted] Note: account connection is available only on certain plans (plan-dependent).
5. Tap **Change the number of the connected account** (**Поменять номер подключенного аккаунта**).
6. Enter the phone number starting with `+`, then tap the **OK** button.
7. Next, the bot will ask you to enter the code sent by Telegram to the new number. This is needed to connect the account to the bot.

Note: the **Change the number of the connected account** option allows changing the number once for free; subsequent changes are paid. [payment-related content omitted]

Menu path: `Menu (Меню) → app menu icon → My account (Мой аккаунт) → plan editing → Change the number of the connected account (Поменять номер подключенного аккаунта)`

(Screenshots have no alt text.)

## Features mentioned
- Connected user account — bot logs into a user's Telegram account (phone + Telegram login code) to act on its behalf; availability depends on plan [doc]
- Change connected account number — re-login with a different phone; one free change, further changes paid [doc]

## Open questions / ambiguities
- Whether existing forwardings keep working/are migrated after the account number changes is not stated.
- 2FA (cloud password) handling during connection is not mentioned.
