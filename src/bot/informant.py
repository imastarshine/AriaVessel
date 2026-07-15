import html

import telebot.types
from telebot.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

import src.aria2
import src.aria2.statistics
import src.bot
import src.bot.security
import src.text
from src.logger import logger


async def start_command(m: Message):
    await src.bot.bot.reply_to(m, "📊 <b>Available commands:</b>\n\n"
                          "📊 <code>/status</code> — Show downloads status\n"
                          "📊 <code>/status exclude-completed | e</code> — Hide completed\n"
                          "⏸️ <code>/pause</code> — Pause torrent(s)\n"
                          "▶️ <code>/resume</code> — Resume torrent(s)\n"
                          "🗑️ <code>/rm</code> — Remove torrent from client\n"
                          "🧹 <code>/del</code> — Delete torrent and files\n"
                          "🔄 <code>/restart</code> — Restart download(s)\n"
                          "🔎 <code>/inspect</code> — Process inspection\n"
                          "⏳ <code>/after</code> — Queue link after downloads complete\n"
                          "💿 <code>/upload</code> — Upload completed files to Yandex.Disk\n"
                          "📊 <code>/upload_status</code> — Upload status\n"
                          "❌ <code>/upload_cancel</code> — Cancel uploading\n\n"
                          "⚙️ <code>/settings</code> — Settings\n\n"
                          "📎 Send <code>.torrent</code>, <code>.zip</code> archive, or <code>magnet:</code> link",
                       parse_mode="HTML")


FILTER_CODES = {"a": None, "e": "e"}


def _build_status_text(filter_code: str) -> list[str]:
    filter_str = FILTER_CODES.get(filter_code)
    parts = src.aria2.statistics.get_status(filter_str)
    return parts


async def status_command(m: Message):
    args = m.text.removeprefix("/status ").strip()

    filter_code = "a"
    if args.lower() in ["e", "exclude-completed"]:
        filter_code = "e"

    logger.info(f"Getting status with filter: {filter_code}")
    parts = _build_status_text(filter_code)

    if len(parts) == 1:
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("🔄 Update", callback_data=f"su:{filter_code}"))
        try:
            await src.bot.bot.send_rich_message(
                m.chat.id,
                telebot.types.InputRichMessage(markdown=parts[0]),
                reply_markup=markup,
            )
        except Exception as e:
            logger.error(f"got error on sending rich message for status command: {e}")
    else:
        for part in parts:
            try:
                await src.bot.bot.send_rich_message(
                    m.chat.id,
                    telebot.types.InputRichMessage(markdown=part),
                )
            except Exception as e:
                logger.error(f"got error on sending rich message chunk: {e}")
                break


async def status_update_callback(call: CallbackQuery):
    try:
        _, filter_code = call.data.split(":", 1)
        parts = _build_status_text(filter_code)

        if len(parts) > 1 or len(parts[0]) > 30100:
            await src.bot.bot.answer_callback_query(call.id, text="❌ Status too large, use /status command")
            return

        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("🔄 Update", callback_data=f"su:{filter_code}"))

        await src.bot.bot.edit_message_text(
            None,
            call.message.chat.id,
            call.message.message_id,
            reply_markup=markup,
            rich_message=telebot.types.InputRichMessage(markdown=parts[0]),
        )
        await src.bot.bot.answer_callback_query(call.id, text="✅ Updated")
    except Exception as e:
        err = str(e)
        if "message is not modified" in err:
            await src.bot.bot.answer_callback_query(call.id, text="ℹ️ No changes")
        else:
            await src.bot.bot.answer_callback_query(call.id, text="❌ Update failed")
            logger.warning(f"status update: {e}")


async def inspect_command(m: Message):
    try:
        idx = int(m.text.split()[1])
        dls = src.aria2.aria2.get_downloads()
        if idx >= len(dls):
            await src.bot.bot.reply_to(m, "❌ <b>The index you specified doesnt exist</b>", parse_mode="HTML")
            return

        d = dls[idx]

        files_info = "\n".join([f"📄 {f.path.name} ({src.text.format_size(f.length)})" for f in d.files[:5]])
        if len(d.files) > 5:
            files_info += f"\n... and {len(d.files) - 5} files more"

        is_magnet = False
        if d.is_torrent:
            try:
                first_file_uri = d.files[0].uris
                if first_file_uri and first_file_uri[0].get("uri", "").startswith('magnet:'):
                    is_magnet = True
            except Exception as ex:
                logger.warning(f"got an exception on getting magnet information about: gid:{d.gid} | {ex}", exc_info=ex)

        parts = [
            f"🔍 <b>Inspection for</b>\n",
            f"📎 <code>{html.escape(d.name)}</code>\n\n",
            f"🆔 GID: <code>{d.gid}</code>\n",
            f"🚦 Status: <b>{d.status}</b>\n",
            f"📍 Path: <code>{d.dir}</code>\n",
            f"👥 Peers: {d.connections}\n",
            f"⚠️ Error: {d.error_message if d.error_message else 'no'}\n\n",
        ]
        if is_magnet:
            parts.append("🧲 Magnet \n")
        if d.is_torrent:
            parts.append("🌐 Torrent \n")
        parts.append(f"🗂️ <b>Files:</b>\n{files_info}")
        report = "".join(parts)

        await src.bot.bot.send_message(m.chat.id, report, parse_mode="HTML")
    except Exception as e:
        await src.bot.bot.reply_to(m, f"❌ <b>An error occurred on inspection</b>: {e}", parse_mode="HTML")
