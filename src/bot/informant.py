import html

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
                          "📊 <code>/status exclude-completed</code> — Hide completed\n"
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


def _build_status_text(filter_code: str) -> tuple[str, bool]:
    filter_str = FILTER_CODES.get(filter_code)
    parts = src.aria2.statistics.get_status(filter_str)
    if len(parts) == 1 and parts[0] == "🤷 There are no torrents currently":
        return parts[0], True
    return "\n\n".join(parts), len(parts) == 1


async def status_command(m: Message):
    parts = m.text.split(maxsplit=1)
    filter_code = "a"
    if len(parts) > 1 and parts[1].strip() == "exclude-completed":
        filter_code = "e"
    logger.info(f"status filter={filter_code}")

    text, single = _build_status_text(filter_code)
    sent = await src.bot.bot.reply_to(m, text, parse_mode="HTML")
    if single:
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("🔄 Update", callback_data=f"su:{sent.message_id}:{filter_code}"))
        try:
            await src.bot.bot.edit_message_reply_markup(sent.chat.id, sent.message_id, reply_markup=markup)
        except Exception:
            pass


async def status_update_callback(call: CallbackQuery):
    try:
        _, _, filter_code = call.data.split(":", 2)
        text, single = _build_status_text(filter_code)
        markup = None
        if single:
            markup = InlineKeyboardMarkup()
            markup.add(InlineKeyboardButton("🔄 Update", callback_data=f"su:{call.message.message_id}:{filter_code}"))
        await src.bot.bot.edit_message_text(text, call.message.chat.id, call.message.message_id, parse_mode="HTML", reply_markup=markup)
        answer = "✅ Updated" if "no torrents" not in text.lower() else "ℹ️ Nothing found"
        await src.bot.bot.answer_callback_query(call.id, text=answer)
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

