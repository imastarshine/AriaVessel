from telebot import asyncio_filters
from telebot.async_telebot import AsyncTeleBot
from src.shared import BOT_TOKEN

bot = AsyncTeleBot(BOT_TOKEN)
bot.add_custom_filter(asyncio_filters.StateFilter(bot))
