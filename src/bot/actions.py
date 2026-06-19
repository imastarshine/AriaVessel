from aria2p import Download
from telebot.types import Message

from src.aria2 import aria2

import src.bot
import src.bot.security
import src.text
import html

from src.logger import logger

ACTION_TO_TEXT = {
    "pause": "⏸️ Paused",
    "resume": "▶️ Resume",
    "rm": "🗑️ Deleted torrent",
    "del": "🧹 Fully deleted"
}


def control_action(action: str, d: list[Download]):
    logger.info(f"download list: {d}")
    if action == "pause":
        return aria2.pause(d)
    elif action == "resume":
        return aria2.resume(d)
    elif action == "rm":
        return aria2.remove(d, force=True, files=False)
    elif action == "del":
        return aria2.remove(d, force=True, files=True)
    return None


async def control_command(m: Message):
    # rm deleting torrent from session, with file saving
    # del deleting torrent and files
    # TODO: Add to status all file size

    try:
        parts = m.text.split()
        # TODO: Message builder

        if len(parts) < 2:
            await src.bot.bot.reply_to(m, "❌ Specify ID(s). Example: <code>/pause 0</code>", parse_mode="HTML")
            return
        cmd = parts[0].lower().removeprefix("/")
        source_downloads = aria2.get_downloads()
        downloads, failed_list = src.text.parse_idx(parts[1], source_downloads)
        message_builder = src.text.MessageBuilder()

        operation_results = control_action(cmd, downloads)
        if not operation_results:
            raise ValueError(f"Unknown action: {cmd}")
        for result, download in zip(operation_results, downloads):
            logger.info(f"result={result}, download name='{download}' {download.name} + gid {download.gid}")
            safe_name = html.escape(download.name)
            # aria2.pause/resume/remove return list[Download] on success, not bool
            message_builder.add_chunk(f"{'✅' if result else '❌'}📦 <b>{safe_name}</b> (<code>{download.gid}</code>)")

        for failed in failed_list:
            message_builder.add_chunk(f"❓ {failed}")

        for index, part in enumerate(message_builder.get_messages()):
            if index == 0:
                part = f"{ACTION_TO_TEXT.get(cmd)}\n\n{part}"

            await src.bot.bot.reply_to(m, part, parse_mode='HTML')
    except Exception as e:
        logger.exception(f"an exception occurred on control: {e}")
        await src.bot.bot.reply_to(
            m,
            f"❌ <b>An error occurred:</b> <code>{html.escape(str(e))}</code>\n\nDid you write a correct id?\nUsage: <code>/[resume,pause,rm,del] &lt;id&gt;</code>",
            parse_mode="HTML"
        )
