import asyncio
import html
import shutil
import zipfile

from telebot.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

import src.aria2.statistics
import src.http_client
import src.bot.shared
import src.shared
import src.text
import src.bot.after
import src.lists
from src.http_client import get_uri_options
from src.logger import logger
from src.aria2 import aria2
from src.bot import bot
from pathlib import Path


async def process_magnet_link(link: str):
    try:
        download = aria2.add_magnet(link, options={"pause": "true"})
        logger.info(f"Added magnet link: {link}")
        return download
    except Exception as e:
        logger.error(f"Failed to add magnet link {link}: {e}")
        await bot.send_message(src.shared.ADMIN_ID, f"❌ Failed to add magnet link: {e}")
        return None


async def process_http_link(link: str):
    try:
        metadata = await src.http_client.get_file_metadata(link)

        if metadata.success:
            options = get_uri_options(metadata)
            download = aria2.add_uris([link], options=options)
            logger.info(f"added http link: {metadata.filename or link[:80]} ({download.gid})")
            return download, metadata
        else:
            logger.error(f"metadata failed for {link[:80]}: {metadata.error} (HTTP {metadata.status_code})")
            await bot.send_message(
                src.shared.ADMIN_ID,
                f"❌ Failed to get metadata for {link[:128]}\nError: {metadata.error}\nCode: {metadata.status_code}"
            )
            return None

    except Exception as e:
        logger.error(f"Failed to add HTTP link {link}: {e}")
        await bot.send_message(src.shared.ADMIN_ID, f"❌ Failed to add HTTP link: {e}")
        return None


async def handle_source(m: Message):
    logger.info(f"msg from {m.from_user.id}: {m.content_type}")
    tmp_dir: Path | None = None
    added = []

    try:
        if m.content_type == 'document':
            # Handle .txt files
            if m.document.file_name.endswith('.txt'):
                info = await bot.get_file(m.document.file_id)
                content = await bot.download_file(info.file_path)
                text_content = content.decode('utf-8')

                lines = text_content.strip().splitlines()
                after_links = []
                for line in lines:
                    line = line.strip()
                    if not line:
                        continue

                    try:
                        if line.startswith("magnet:"):
                            res = await process_magnet_link(line)
                            added += [res] if res else []
                        elif line.startswith(("http://", "https://")):
                            res = await process_http_link(line)
                            added += [res] if res else []
                        elif line.startswith(("/after https://", "/after http://")):
                            after_links.append(line.removeprefix("/after ").strip())
                    except Exception as e:
                        logger.warning(f"failed to process line '{line[:80]}': {e}")

                for after_link in after_links:
                    last_task = src.lists.safe_get_from_list(src.bot.after.after_tasks, -1)
                    logger.info(
                        f"adding new after task (from file): {after_link} and {last_task.id if last_task else 'None (not found)'} (not specified ID)")
                    src.bot.after.add_task(after_link, [last_task.id] if last_task else None)

                if after_links:
                    logger.info(f"queued {len(after_links)} after task(s) from .txt file")
                    string_links = [f"📎 <code>{html.escape(after_link[:128])}</code>" for after_link in after_links]
                    await bot.send_message(
                        src.shared.ADMIN_ID,
                        f"⏳ Queued {len(after_links)} after task(s):\n" + "\n".join(string_links),
                        parse_mode="HTML"
                    )
                elif not added:
                    logger.info("no links found in .txt file")
                    await bot.send_message(src.shared.ADMIN_ID, "📄 No links found in the .txt file")

            # Handle .zip files
            elif m.document.file_name.endswith('.zip'):
                tmp_dir = Path() / f"tmp_{m.message_id}"
                tmp_dir.mkdir(parents=True, exist_ok=True)

                info = await bot.get_file(m.document.file_id)
                content = await bot.download_file(info.file_path)
                archive_path = tmp_dir / f"archive.zip"
                with archive_path.open("wb") as f:
                    f.write(content)

                with zipfile.ZipFile(archive_path, 'r') as z:
                    z.extractall(tmp_dir)

                for f in tmp_dir.rglob('*.torrent'):
                    added.append(aria2.add_torrent(f, options={"pause": "true"}))

            # Handle .torrent files
            elif m.document.file_name.endswith('.torrent'):
                tmp_dir = Path() / f"tmp_{m.message_id}"
                tmp_dir.mkdir(parents=True, exist_ok=True)

                info = await bot.get_file(m.document.file_id)
                content = await bot.download_file(info.file_path)

                torrent_path = tmp_dir / f"tmp_{m.document.file_id}.torrent"
                with torrent_path.open("wb") as f:
                    f.write(content)

                added.append(aria2.add_torrent(torrent_path, options={"pause": "true"}))
                torrent_path.unlink(missing_ok=True)

        # Handle text messages
        elif m.text:
            if m.text.startswith('magnet:'):
                res = await process_magnet_link(m.text)
                if res:
                    added.append(res)

            elif m.text.startswith('http://') or m.text.startswith('https://'):
                res = await process_http_link(m.text)
                if res:
                    added.append(res)

        logger.info(f"Added {len(added)} new download processes")

        if added:
            src.bot.shared.pending_processes[src.shared.ADMIN_ID] = [d[0].gid if isinstance(d, tuple) else d.gid for d in added]
            logger.info(f"pending processes count: {len(added)}")

            messages = []
            message = "Found:\n"
            for i, d in enumerate(added):
                if len(message) > 3500:
                    messages.append(message)
                    message = ""
                    await asyncio.sleep(0.05)

                if isinstance(d, tuple):
                    download, file_metadata = d[0], d[1]
                    safe_name = html.escape(download.name)
                    message += f"📦 <b>{safe_name}</b> ({src.text.format_size(file_metadata.size)})\n"
                else:
                    safe_name = html.escape(d.name)
                    message += f"📦 <b>{safe_name}</b> ({src.text.format_size(src.aria2.statistics.get_total_size(d))})\n"

            if len(message) > 0:
                messages.append(message)

            for index, msg in enumerate(messages):
                markup = None
                if index == len(messages) - 1:
                    markup = InlineKeyboardMarkup()
                    markup.row(
                        InlineKeyboardButton("Add", callback_data="confirm_y", style="success"),
                        InlineKeyboardButton("Cancel", callback_data="confirm_n", style="danger")
                    )
                logger.debug(f"index: {index}, msg: {msg}")
                await bot.send_message(src.shared.ADMIN_ID, msg, reply_markup=markup, parse_mode="HTML")

    except Exception as e:
        logger.exception(f"an error occurred on handle_source: {e}")
        await bot.send_message(src.shared.ADMIN_ID, f"❌ <b>Got error:</b> <code>{html.escape(str(e))}</code>", parse_mode="HTML")
    finally:
        if tmp_dir and tmp_dir.exists():
            shutil.rmtree(tmp_dir)


async def confirm_callback(call: CallbackQuery):
    gids: list[str] = src.bot.shared.pending_processes.pop(src.shared.ADMIN_ID, [])

    if not gids:
        await bot.answer_callback_query(call.id, text="No torrents currently pending")
        return

    try:
        logger.info(f"confirm: {call.data} — {len(gids)} torrent(s)")
        if call.data == "confirm_y":
            downloads = aria2.get_downloads(gids)
            aria2.resume(downloads)
            await bot.answer_callback_query(call.id, text="✅ Starting to download")
        elif call.data == "confirm_n":
            downloads = aria2.get_downloads(gids)
            aria2.remove(downloads, force=True, files=True)
            await bot.answer_callback_query(call.id, text="❌ Canceled")

        if call.data.startswith("confirm_"):
            await bot.delete_message(call.message.chat.id, call.message.id)
    except Exception as e:
        logger.exception(f"confirm_callback: {e}")
        await bot.send_message(call.message.chat.id,
                               text=f"❌ <b>Got error on confirmation:</b> <code>{html.escape(str(e))}</code>",
                               parse_mode="HTML")
        