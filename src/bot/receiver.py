import asyncio
import html
import re
import shutil
import zipfile

from slugify import slugify
from telebot.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

import src.aria2.statistics
import src.bot.after
import src.http_client
import src.bot.shared
import src.configs
import src.shared
import src.text
from src.logger import logger
from src.aria2 import aria2
from src.bot import bot

from pathlib import Path


def get_uri_options(metadata: src.http_client.FileMetadataResult) -> dict[str, str]:
    options = {
        "pause": "true"
    }
    if src.configs.config.uri_filename_rename:
        file_path = Path(metadata.filename)
        file_suffix = file_path.suffix
        new_file_name = file_path.stem

        if src.configs.config.uri_filename_translit:
            new_file_name = src.text.auto_translit(new_file_name)

        if src.configs.config.uri_filename_slugify:
            new_file_name = slugify(new_file_name)

        if 0 < src.configs.config.uri_filename_max_length < len(new_file_name):
            new_file_name = new_file_name[:src.configs.config.uri_filename_max_length]

        options["out"] = f"{new_file_name}{file_suffix}"

    return options


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
        logger.debug(f"Fetching http url '{link}'.")
        metadata = await src.http_client.get_file_metadata(link)
        logger.info(f"Metadata fetched successfully: {metadata}")

        if metadata.success:
            options = get_uri_options(metadata)
            download = aria2.add_uris([link], options=options)
            logger.info(f"Added HTTP link: {link}")
            return download, metadata
        else:
            logger.error(
                f"Failed to get metadata for {link} | Error = {metadata.error} | Code = {metadata.status_code}")
            await bot.send_message(
                src.shared.ADMIN_ID,
                f"❌ Failed to get metadata for {link}\nError: {metadata.error}\nCode : {metadata.status_code}"
            )
            return None

    except Exception as e:
        logger.error(f"Failed to add HTTP link {link}: {e}")
        await bot.send_message(src.shared.ADMIN_ID, f"❌ Failed to add HTTP link: {e}")
        return None


def extract_link_from_after_line(line: str) -> str | None:
    parts = line.strip().split(maxsplit=2)
    if len(parts) < 2:
        return None
    link = parts[-1]
    if link.startswith(("http://", "https://")):
        return link
    return None


async def process_after_file(lines: list[str], m: Message) -> list:
    downloads = aria2.get_downloads()
    added = []
    gids = []
    delay = src.bot.after.parse_after_delay(src.configs.config.after_delay)

    for line in lines:
        link = extract_link_from_after_line(line)
        if not link:
            continue
        await asyncio.sleep(delay)
        result = aria2.add_uris([link], options={"pause": "true"})
        gid = result.gid
        gids.append(gid)
        added.append(result)
        logger.info(f"after_file: added '{link}' (paused), gid={gid}")

    if not gids:
        return added

    parent_gid: str | None = downloads[-1].gid if downloads else None
    first_gid = gids[0]

    for child_gid in gids:
        if parent_gid:
            if parent_gid not in src.bot.shared.resume_queue:
                src.bot.shared.resume_queue[parent_gid] = []
            src.bot.shared.resume_queue[parent_gid].append(child_gid)
            logger.info(f"after_file: chained resume {child_gid} after {parent_gid}")
        parent_gid = child_gid

    if not downloads:
        aria2.resume([aria2.get_downloads([first_gid])[0]])

    safe_names = []
    for d in added:
        safe_names.append(html.escape(d.name or "unknown"))
    summary = "📋 <b>After chain added:</b>\n"
    for i, (sn, gid) in enumerate(zip(safe_names, gids)):
        status = "▶️ Started" if i == 0 and not downloads else "⏸ Paused"
        summary += f"{i+1}. 📦 <b>{sn}</b> (<code>{gid}</code>) {status}\n"
    if downloads:
        summary += f"\n⏳ First download will start after <code>{downloads[-1].gid}</code> completes"
    await bot.send_message(src.shared.ADMIN_ID, summary, parse_mode="HTML")

    return added


async def handle_source(m: Message):
    logger.info(f"new message id: {m.message_id}")
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
                after_lines = [ln for ln in lines if ln.strip().startswith("/after")]

                if after_lines and all(ln.strip().startswith("/after") for ln in lines if ln.strip()):
                    added = await process_after_file(lines, m)
                    return

                links = re.findall(r'magnet:\S+|https?://\S+', text_content)
                for link in links:
                    link = link.strip()
                    if link.startswith('magnet:'):
                        res = await process_magnet_link(link)
                        if res:
                            added.append(res)
                    elif link.startswith('http://') or link.startswith('https://'):
                        res = await process_http_link(link)
                        if res:
                            added.append(res)

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
            logger.info(f"pending processes: {src.bot.shared.pending_processes}")

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
                        InlineKeyboardButton("Add", callback_data=f"confirm_y", style="success"),
                        InlineKeyboardButton("Cancel", callback_data=f"confirm_n", style="danger")
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
    logger.debug(f"pending_torrents: {src.bot.shared.pending_processes}")

    if not gids:
        logger.info(f"no torrents currently pending")
        await bot.answer_callback_query(call.id, text="No torrents currently pending")
        return

    try:
        logger.info(f"callback query received: {call.data}, message id: {call.message.id}")
        if call.data == "confirm_y":
            logger.info(f"user accepted download, starting to download {len(gids)} torrents")
            downloads = aria2.get_downloads(gids)
            aria2.resume(downloads)
            await bot.answer_callback_query(call.id, text="✅ Starting to download")
        elif call.data == "confirm_n":
            logger.info(f"user canceled download, removing {len(gids)} torrents")
            downloads = aria2.get_downloads(gids)
            aria2.remove(downloads, force=True, files=True)
            await bot.answer_callback_query(call.id, text="❌ Canceled")

        if call.data.startswith("confirm_"):
            await bot.delete_message(call.message.chat.id, call.message.id)
    except Exception as e:
        logger.exception(f"an error occurred on confirm_callback: {e}")
        await bot.send_message(call.message.chat.id,
                               text=f"❌ <b>Got error on confirmation:</b> <code>{html.escape(str(e))}</code>",
                               parse_mode="HTML")
        