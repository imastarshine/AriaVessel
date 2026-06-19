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
    logger.info(f"{action} on {len(d)} download(s)")
    if action == "pause":
        return aria2.pause(d)
    elif action == "resume":
        return aria2.resume(d)
    elif action == "rm":
        return aria2.remove(d, force=True, files=False)
    elif action == "del":
        return aria2.remove(d, force=True, files=True)
    return None


async def restart_command(m: Message):
    try:
        parts = m.text.split()
        if len(parts) < 2:
            await src.bot.bot.reply_to(m, "❌ Usage: /restart <idx|gid> [idx|gid...]", parse_mode="HTML")
            return

        source_downloads = aria2.get_downloads()
        to_reload, failed_list = src.text.parse_idx(parts[1], source_downloads)
        msg_builder = src.text.MessageBuilder()

        for dl in to_reload:
            uri = None
            if dl.files and dl.files[0].uris:
                uri = dl.files[0].uris[0].get("uri")
            if not uri:
                safe_name = html.escape(dl.name or "Unknown")
                msg_builder.add_chunk(f"⚠️ <b>{safe_name}</b> – no URI to reload")
                continue

            aria2.remove([dl], force=True, files=False)
            result = aria2.add_uris([uri], options={"pause": "true"})
            aria2.resume([result])
            new_gid = result.gid
            logger.info(f"restarted {dl.gid} -> {new_gid} ({dl.name})")
            safe_name = html.escape(dl.name or uri)
            msg_builder.add_chunk(f"🔄 <b>{safe_name}</b> – restarted (<code>{new_gid}</code>)")

        for failed in failed_list:
            msg_builder.add_chunk(f"❓ {failed}")

        for part in msg_builder.get_messages():
            await src.bot.bot.reply_to(m, part, parse_mode="HTML")
    except Exception as e:
        logger.exception(f"restart failed: {e}")
        await src.bot.bot.reply_to(
            m,
            f"❌ <b>Error:</b> <code>{html.escape(str(e))}</code>\n\nUsage: <code>/restart &lt;id&gt;</code>",
            parse_mode="HTML"
        )


async def control_command(m: Message):
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
            logger.info(f"  {download.gid} {download.name} → {'ok' if result else 'fail'}")
            safe_name = html.escape(download.name)
            # aria2.pause/resume/remove return list[Download] on success, not bool
            message_builder.add_chunk(f"{'✅' if result else '❌ ' + str(result) + '. '}📦 <b>{safe_name}</b> (<code>{download.gid}</code>)")

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
