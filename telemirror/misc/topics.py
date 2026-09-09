GENERAL_TOPIC_ID = 1


def topic_id_of(message) -> int:
    """The forum topic id a message belongs to (the General topic is ``1``).

    message: topic id = ``reply_to.reply_to_msg_id``
    reply:   topic id = ``reply_to.reply_to_top_id``
    A non-forum ``reply_to`` (or no ``reply_to``) means the General topic.
    """
    reply_to = message.reply_to
    if reply_to is not None and reply_to.forum_topic:
        return reply_to.reply_to_top_id or reply_to.reply_to_msg_id
    return GENERAL_TOPIC_ID
