# Junction Bot docs — crawl inventory

Checkpoint file. Resume from the first row whose status is `pending`.

Source: https://www.junctionbot.io/sitemap.xml (probed 2026-11-19). EN set mirrors RU 1:1 (no EN-only pages).
Scope: documentation/*, instructions/*, features/*. Out of scope: articles, solutions, plans, affiliate, about, business, offers.

| # | URL (RU) | EN twin | batch | status | pages file |
|---|---|---|---|---|---|
| 1 | https://www.junctionbot.io/ru/documentation/getting-started | https://www.junctionbot.io/documentation/getting-started | B1 | read | documentation__getting-started.md |
| 2 | https://www.junctionbot.io/ru/documentation/account-connection | https://www.junctionbot.io/documentation/account-connection | B1 | read | documentation__account-connection.md |
| 3 | https://www.junctionbot.io/ru/documentation/forwarding | https://www.junctionbot.io/documentation/forwarding | B1 | read | documentation__forwarding.md |
| 4 | https://www.junctionbot.io/ru/documentation/digests | https://www.junctionbot.io/documentation/digests | B1 | read | documentation__digests.md |
| 5 | https://www.junctionbot.io/ru/documentation/copying-old-messages | https://www.junctionbot.io/documentation/copying-old-messages | B1 | read | documentation__copying-old-messages.md |
| 6 | https://www.junctionbot.io/ru/documentation/filters | https://www.junctionbot.io/documentation/filters | B1 | read | documentation__filters.md |
| 7 | https://www.junctionbot.io/ru/documentation/message-processing | https://www.junctionbot.io/documentation/message-processing | B2 | read | documentation__message-processing.md |
| 8 | https://www.junctionbot.io/ru/documentation/publishing-and-moderation | https://www.junctionbot.io/documentation/publishing-and-moderation | B2 | read | documentation__publishing-and-moderation.md |
| 9 | https://www.junctionbot.io/ru/documentation/projects | https://www.junctionbot.io/documentation/projects | B2 | read | documentation__projects.md |
| 10 | https://www.junctionbot.io/ru/documentation/integrations-and-settings | https://www.junctionbot.io/documentation/integrations-and-settings | B2 | read | documentation__integrations-and-settings.md |
| 11 | https://www.junctionbot.io/ru/documentation/troubleshooting | https://www.junctionbot.io/documentation/troubleshooting | B2 | read | documentation__troubleshooting.md |
| 12 | https://www.junctionbot.io/ru/instructions | https://www.junctionbot.io/instructions | B2 | read | instructions__index.md |
| 13 | https://www.junctionbot.io/ru/instructions/delayed-filters | https://www.junctionbot.io/instructions/delayed-filters | B2 | read | instructions__delayed-filters.md |
| 14 | https://www.junctionbot.io/ru/instructions/delivery-report-message-has-been-successfully-delivered | https://www.junctionbot.io/instructions/delivery-report-message-has-been-successfully-delivered | B2 | read | instructions__delivery-report-message-has-been-successfully-delivered.md |
| 15 | https://www.junctionbot.io/ru/instructions/delivery-report-message-has-not-been-delivered-due-to-must-have-filter | https://www.junctionbot.io/instructions/delivery-report-message-has-not-been-delivered-due-to-must-have-filter | B3 | read | instructions__delivery-report-message-has-not-been-delivered-due-to-must-have-filter.md |
| 16 | https://www.junctionbot.io/ru/instructions/delivery-report-message-has-not-been-delivered-due-to-must-not-have-filter | https://www.junctionbot.io/instructions/delivery-report-message-has-not-been-delivered-due-to-must-not-have-filter | B3 | read | instructions__delivery-report-message-has-not-been-delivered-due-to-must-not-have-filter.md |
| 17 | https://www.junctionbot.io/ru/instructions/how-to-add-a-link-to-the-original-message-when-copying-messages | https://www.junctionbot.io/instructions/how-to-add-a-link-to-the-original-message-when-copying-messages | B3 | read | instructions__how-to-add-a-link-to-the-original-message-when-copying-messages.md |
| 18 | https://www.junctionbot.io/ru/instructions/how-to-change-connected-account | https://www.junctionbot.io/instructions/how-to-change-connected-account | B3 | read | instructions__how-to-change-connected-account.md |
| 19 | https://www.junctionbot.io/ru/instructions/how-to-clone-a-forwarding | https://www.junctionbot.io/instructions/how-to-clone-a-forwarding | B3 | read | instructions__how-to-clone-a-forwarding.md |
| 20 | https://www.junctionbot.io/ru/instructions/how-to-copy-old-messages-from-any-telegram-channel-or-group | https://www.junctionbot.io/instructions/how-to-copy-old-messages-from-any-telegram-channel-or-group | B3 | read | instructions__how-to-copy-old-messages-from-any-telegram-channel-or-group.md |
| 21 | https://www.junctionbot.io/ru/instructions/how-to-copy-topic-structure | https://www.junctionbot.io/instructions/how-to-copy-topic-structure | B3 | read | instructions__how-to-copy-topic-structure.md |
| 22 | https://www.junctionbot.io/ru/instructions/how-to-disable-auto-renewal | https://www.junctionbot.io/instructions/how-to-disable-auto-renewal | - | skipped (payment) | - |
| 23 | https://www.junctionbot.io/ru/instructions/how-to-filter-any-media | https://www.junctionbot.io/instructions/how-to-filter-any-media | B3 | read | instructions__how-to-filter-any-media.md |
| 24 | https://www.junctionbot.io/ru/instructions/how-to-filter-forwarded-messages | https://www.junctionbot.io/instructions/how-to-filter-forwarded-messages | B3 | read | instructions__how-to-filter-forwarded-messages.md |
| 25 | https://www.junctionbot.io/ru/instructions/how-to-find-leads-clients-and-potential-orders-ai | https://www.junctionbot.io/instructions/how-to-find-leads-clients-and-potential-orders-ai | B4 | read | instructions__how-to-find-leads-clients-and-potential-orders-ai.md |
| 26 | https://www.junctionbot.io/ru/instructions/how-to-forward-from-private-telegram-channel-or-group | https://www.junctionbot.io/instructions/how-to-forward-from-private-telegram-channel-or-group | B4 | read | instructions__how-to-forward-from-private-telegram-channel-or-group.md |
| 27 | https://www.junctionbot.io/ru/instructions/how-to-forward-from-public-telegram-channel-or-group | https://www.junctionbot.io/instructions/how-to-forward-from-public-telegram-channel-or-group | B4 | read | instructions__how-to-forward-from-public-telegram-channel-or-group.md |
| 28 | https://www.junctionbot.io/ru/instructions/how-to-forward-messages-between-topics-in-telegram-groups | https://www.junctionbot.io/instructions/how-to-forward-messages-between-topics-in-telegram-groups | B4 | read | instructions__how-to-forward-messages-between-topics-in-telegram-groups.md |
| 29 | https://www.junctionbot.io/ru/instructions/how-to-forward-messages-from-several-topics-to-general-topic | https://www.junctionbot.io/instructions/how-to-forward-messages-from-several-topics-to-general-topic | B4 | read | instructions__how-to-forward-messages-from-several-topics-to-general-topic.md |
| 30 | https://www.junctionbot.io/ru/instructions/how-to-purchase-a-plan | https://www.junctionbot.io/instructions/how-to-purchase-a-plan | - | skipped (payment) | - |
| 31 | https://www.junctionbot.io/ru/instructions/how-to-remove-ads-from-forwarding-ai | https://www.junctionbot.io/instructions/how-to-remove-ads-from-forwarding-ai | B4 | read | instructions__how-to-remove-ads-from-forwarding-ai.md |
| 32 | https://www.junctionbot.io/ru/instructions/how-to-replace-a-word-or-part-of-text-when-copying-messages | https://www.junctionbot.io/instructions/how-to-replace-a-word-or-part-of-text-when-copying-messages | B4 | read | instructions__how-to-replace-a-word-or-part-of-text-when-copying-messages.md |
| 33 | https://www.junctionbot.io/ru/instructions/how-to-set-up-a-digest | https://www.junctionbot.io/instructions/how-to-set-up-a-digest | B4 | read | instructions__how-to-set-up-a-digest.md |
| 34 | https://www.junctionbot.io/ru/instructions/how-to-set-up-manual-moderation-via-junction-review-bot | https://www.junctionbot.io/instructions/how-to-set-up-manual-moderation-via-junction-review-bot | B4 | read | instructions__how-to-set-up-manual-moderation-via-junction-review-bot.md |
| 35 | https://www.junctionbot.io/ru/instructions/how-to-set-up-manual-moderation-via-own-chat | https://www.junctionbot.io/instructions/how-to-set-up-manual-moderation-via-own-chat | B5 | read | instructions__how-to-set-up-manual-moderation-via-own-chat.md |
| 36 | https://www.junctionbot.io/ru/instructions/how-to-setup-an-ai-integration | https://www.junctionbot.io/instructions/how-to-setup-an-ai-integration | B5 | read | instructions__how-to-setup-an-ai-integration.md |
| 37 | https://www.junctionbot.io/ru/instructions/how-to-specify-the-author-when-copying-messages | https://www.junctionbot.io/instructions/how-to-specify-the-author-when-copying-messages | B5 | read | instructions__how-to-specify-the-author-when-copying-messages.md |
| 38 | https://www.junctionbot.io/ru/instructions/how-to-specify-the-name-of-the-source-chat-when-copying-messages | https://www.junctionbot.io/instructions/how-to-specify-the-name-of-the-source-chat-when-copying-messages | B5 | read | instructions__how-to-specify-the-name-of-the-source-chat-when-copying-messages.md |
| 39 | https://www.junctionbot.io/ru/instructions/how-to-split-forwardings-into-2-accounts | https://www.junctionbot.io/instructions/how-to-split-forwardings-into-2-accounts | B5 | read | instructions__how-to-split-forwardings-into-2-accounts.md |
| 40 | https://www.junctionbot.io/ru/instructions/how-to-top-up-balance | https://www.junctionbot.io/instructions/how-to-top-up-balance | - | skipped (payment) | - |
| 41 | https://www.junctionbot.io/ru/instructions/media-caption | https://www.junctionbot.io/instructions/media-caption | B5 | read | instructions__media-caption.md |
| 42 | https://www.junctionbot.io/ru/features/account-connection | https://www.junctionbot.io/features/account-connection | B5 | read | features__account-connection.md |
| 43 | https://www.junctionbot.io/ru/features/ai-digests | https://www.junctionbot.io/features/ai-digests | B5 | read | features__ai-digests.md |
| 44 | https://www.junctionbot.io/ru/features/and-more | https://www.junctionbot.io/features/and-more | B5 | read | features__and-more.md (page is an empty template on the live site) |
| 45 | https://www.junctionbot.io/ru/features/content-filtering | https://www.junctionbot.io/features/content-filtering | B6 | read | features__content-filtering.md |
| 46 | https://www.junctionbot.io/ru/features/feed-aggregation | https://www.junctionbot.io/features/feed-aggregation | B6 | read | features__feed-aggregation.md |
| 47 | https://www.junctionbot.io/ru/features/folders-forwarding | https://www.junctionbot.io/features/folders-forwarding | B6 | read | features__folders-forwarding.md |
| 48 | https://www.junctionbot.io/ru/features/gpt-processing | https://www.junctionbot.io/features/gpt-processing | B6 | read | features__gpt-processing.md |
| 49 | https://www.junctionbot.io/ru/features/history-copying | https://www.junctionbot.io/features/history-copying | B6 | read | features__history-copying.md |
| 50 | https://www.junctionbot.io/ru/features/manual-moderation | https://www.junctionbot.io/features/manual-moderation | B6 | read | features__manual-moderation.md |
| 51 | https://www.junctionbot.io/ru/features/message-forwarding | https://www.junctionbot.io/features/message-forwarding | B6 | read | features__message-forwarding.md |
| 52 | https://www.junctionbot.io/ru/features/text-modification | https://www.junctionbot.io/features/text-modification | B6 | read | features__text-modification.md |
| 53 | https://www.junctionbot.io/ru/features/topic-mapping | https://www.junctionbot.io/features/topic-mapping | B6 | read | features__topic-mapping.md |
| 54 | https://www.junctionbot.io/ru/features/watermark-overlay | https://www.junctionbot.io/features/watermark-overlay | B6 | read | features__watermark-overlay.md |
