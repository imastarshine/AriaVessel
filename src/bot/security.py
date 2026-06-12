import typing

from telebot.types import Message, CallbackQuery

from src.shared import ADMIN_ID
from src.logger import logger

def restricted(func: typing.Callable) -> typing.Callable:
    async def wrapper(message: Message | CallbackQuery, *args, **kwargs):
        if message.from_user.id == ADMIN_ID:
            return await func(message, *args, **kwargs)
        else:
            logger.warning(f"user {message.from_user.username} {message.from_user.id} not allowed")
        return False

    return wrapper
