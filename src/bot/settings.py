import re
from itertools import groupby

import telebot.asyncio_helper
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, Message, CallbackQuery

import src.configs
import src.text
import src.bot
import src.bot.security
import src.bot.states
from src.logger import logger

CATEGORIES_REGEX = r"([a-zA-Z]+)_([a-zA-Z]+)_"


def get_categories(item):
    key, _ = item
    match = re.search(CATEGORIES_REGEX, key)
    if match:
        return match.group(1), match.group(2)
    return "other", "keys"


def generate_settings_keyboard_markup() -> InlineKeyboardMarkup:
    config_dict = src.configs.config.to_dict()
    markup = InlineKeyboardMarkup(row_width=1)

    sorted_items = sorted(config_dict.items(), key=get_categories)

    for (cat1, cat2), group in groupby(sorted_items, key=get_categories):
        header_btn = InlineKeyboardButton(text=f"{cat1} | {cat2}", callback_data="ignore")
        markup.add(header_btn)

        for key, value in group:
            callback_value = key if len(key) <= 50 else key[:50]
            style = ((src.text.boolean_to_telegram_style(value) if isinstance(value, bool) else None)
                     or "Primary")

            item_btn = InlineKeyboardButton(
                text=f"{src.configs.config.get_pretty_label(key)}"
                     f": {src.text.boolean_to_human_readable_string(value) if isinstance(value, bool) else value}",
                callback_data=f"e:{callback_value}",
                style=style
            )
            markup.add(item_btn)

    return markup


async def settings_command(m: Message):
    markup = generate_settings_keyboard_markup()
    await src.bot.bot.reply_to(m, text="<b>Bot settings...</b>", parse_mode="HTML", reply_markup=markup)


async def set_int_config_item(m: Message) -> None:
    try:
        logger.info(f"[set_int_config]: received a message from: {m.from_user.id}")
        user_message = m.text

        if user_message == "/cancel":

            return

        async with src.bot.bot.retrieve_data(m.from_user.id, m.chat.id) as data:
            setting_key = data.get('setting_key')
            helper_msg_id = data.get('helper_message_id')
            original_markup_message_id = data.get('original_markup_message_id')

        logger.info(
            f"[set_int_config]: settings_key: {setting_key} | helper_msg_id: {helper_msg_id} "
            f"| orig_msmg_id: {original_markup_message_id}"
        )

        try:
            int(user_message)
        except (ValueError, TypeError):
            await src.bot.bot.delete_message(chat_id=m.chat.id, message_id=m.message_id)
            try:
                await src.bot.bot.delete_message(chat_id=m.chat.id, message_id=helper_msg_id)
            except telebot.asyncio_helper.ApiTelegramException:
                pass
            await src.bot.bot.send_message(chat_id=m.chat.id, text="❌ <b>The value must be an integer. Try again.</b>", parse_mode="HTML")
            # await bot.delete_state(m.from_user.id, m.chat.id)
            return

        setattr(src.configs.config, setting_key, int(user_message))
        src.configs.config.save()

        new_value = getattr(src.configs.config, setting_key)
        await src.bot.bot.send_message(
            chat_id=m.chat.id,
            text=f"Setting <code>{setting_key}</code> has been updated to <code>{new_value}</code>",
            parse_mode="HTML"
        )
        await src.bot.bot.delete_message(chat_id=m.chat.id, message_id=helper_msg_id)
        await src.bot.bot.delete_message(chat_id=m.chat.id, message_id=m.message_id)

        await src.bot.bot.edit_message_reply_markup(
            chat_id=m.chat.id,
            message_id=original_markup_message_id,
            reply_markup=generate_settings_keyboard_markup()
        )
        await src.bot.bot.delete_state(m.from_user.id, m.chat.id)
    except Exception as e:
        logger.error(f"error while handling set int config state step: {e}", exc_info=e)


async def process_settings_callback(call: CallbackQuery):
    setting = call.data.removeprefix("e:")
    value = getattr(src.configs.config, setting)
    if isinstance(value, bool):
        setattr(src.configs.config, setting, not value)
        await src.bot.bot.answer_callback_query(call.id, text=f"Changed {setting} to {not value}")
        await src.bot.bot.edit_message_reply_markup(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            reply_markup=generate_settings_keyboard_markup()
        )
        src.configs.config.save()
    elif isinstance(value, int):
        message = await src.bot.bot.send_message(
            chat_id=call.from_user.id,
            text=f"Enter a new number for <code>{setting}</code>\n↩️ Send <code>/cancel</code> to cancel this action",
            parse_mode="HTML"
        )
        try:
            await src.bot.bot.set_state(
                call.from_user.id,
                src.bot.states.UserSteps.waiting_for_setting_int_value,
                call.message.chat.id
            )
            async with src.bot.bot.retrieve_data(call.from_user.id, call.message.chat.id) as data:
                data['setting_key'] = setting
                data['helper_message_id'] = message.message_id
                data['original_markup_message_id'] = call.message.message_id
        except Exception as e:
            logger.exception(f"an error occurred on set int value for setting: {setting}", exc_info=e)
    else:
        # TODO: Make it better
        await src.bot.bot.answer_callback_query(call.id, text="Cannot change this")
