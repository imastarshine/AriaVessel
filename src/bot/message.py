from telebot.types import Message

import src.bot
from src.logger import logger
from src.shared import ADMIN_ID


async def try_to_send_message(text: str, parse_mode: str | None, *args, **kwargs):
    try:
        await src.bot.bot.send_message(
            ADMIN_ID,
            text,
            *args,
            parse_mode=parse_mode,
            **kwargs
        )
    except Exception as e:
        logger.exception(f"failed to send message due to: {e}", exc_info=True)


async def try_to_reply(message: Message, text: str, parse_mode: str | None, **kwargs):
    try:
        await src.bot.bot.reply_to(
            message,
            text,
            parse_mode=parse_mode,
            **kwargs
        )
    except Exception as e:
        logger.exception(f"failed to reply to message: {message} due to: {e}", exc_info=True)
