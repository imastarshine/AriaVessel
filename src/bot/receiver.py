import asyncio
import html
import random
import re
import shutil
import zipfile

from slugify import slugify
from telebot.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

import src.aria2.statistics
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


def _next_task_id() -> str:
    src.bot.shared.after_counter = getattr(src.bot.shared, "after_counter", 0) + 1
    task_id = f"__task_{src.bot.shared.after_counter}__"
    src.bot.shared.after_last_task_id = task_id
    return task_id


def _dl_finished(dl) -> bool:
    from src.aria2.statistics import get_total_size
    total = get_total_size(dl)
    if dl.status in ("complete", "error", "removed"):
        return True
    if 0 < total == dl.completed_length:
        return True
    return False


def _find_single_parent(downloads: list, arg: str) -> str | None:
    if len(arg) == 16 and all(c in "0123456789abcdef" for c in arg):
        return arg
    try:
        dl_list, _ = src.text.parse_idx(arg, downloads)
        if dl_list:
            return dl_list[0].gid
    except (ValueError, IndexError):
        pass
    return None


def parse_after_delay(raw: str = "") -> float:
    if not raw:
        raw = src.configs.config.uri_files_after_delay
    if "," in raw:
        parts = [x.strip() for x in raw.split(",", 1)]
        try:
            a, b = float(parts[0]), float(parts[1])
        except (ValueError, IndexError):
            return 2.0
        if a < 0.25:
            a = 0.25
        if b < 0.25:
            b = 0.25
        if a > b:
            a, b = b, a
        return random.uniform(a, b)
    else:
        try:
            v = float(raw)
        except ValueError:
            return 2.0
        return max(v, 0.25)


async def after_command(m: Message):
    try:
        parts = m.text.split(maxsplit=2)
        if len(parts) < 2:
            await bot.reply_to(m, "❌ Usage: /after <http-link> or /after <idx> <http-link> or /after <gid> <http-link>", parse_mode="HTML")
            return

        link = parts[-1]
        if not link.startswith(("http://", "https://")):
            await bot.reply_to(m, "❌ The link must be http:// or https://", parse_mode="HTML")
            return

        # save previous task BEFORE _next_task_id overwrites after_last_task_id
        last = src.bot.shared.after_last_task_id
        task_id = _next_task_id()
        entry = {"link": link, "task_id": task_id, "retries": 0}
        downloads = aria2.get_downloads()
        msg = ""

        if len(parts) == 2:
            # /after <link>  ->  if we have a previous after task, chain to it
            if last:
                src.bot.shared.after_queue.setdefault(last, []).append(entry)
                msg = "⏳ Queued – will start after previous task"
            else:
                active = [d for d in downloads if not _dl_finished(d)]
                if active:
                    parents = [d.gid for d in active]
                    src.bot.shared.after_batch.append({"parents": parents, **entry})
                    msg = f"⏳ Queued – will start after <b>{len(parents)}</b> download(s) complete"
                else:
                    asyncio.create_task(_run_after_directly(m, entry))
                    msg = "▶️ Starting now"

        else:
            # /after <idx|gid> <link>
            parent = _find_single_parent(downloads, parts[1])
            if parent is None:
                await bot.reply_to(m, "❌ Invalid ID or GID specified", parse_mode="HTML")
                return
            src.bot.shared.after_queue.setdefault(parent, []).append(entry)
            msg = f"⏳ Queued – will start after <code>{parent[:16]}</code>"

        await bot.reply_to(m, f"{msg}:\n{html.escape(link[:128])}", parse_mode="HTML")
        logger.info(f"after: queued {task_id} link={link}")
    except Exception as e:
        logger.exception(f"after command error: {e}")
        await bot.reply_to(m, f"❌ <b>Error:</b> <code>{html.escape(str(e))}</code>", parse_mode="HTML")


async def process_after_file(lines: list[str], m: Message) -> list:
    downloads = aria2.get_downloads()
    active = [d for d in downloads if not _dl_finished(d)]
    queued = []
    prev_key: str | None = None

    if active:
        parents = [d.gid for d in active]
    else:
        parents = None

    for line in lines:
        link = extract_link_from_after_line(line)
        if not link:
            continue
        task_id = _next_task_id()
        entry = {"link": link, "task_id": task_id, "retries": 0}

        if prev_key:
            src.bot.shared.after_queue.setdefault(prev_key, []).append(entry)
            logger.info(f"after_file: queued {task_id} after previous task")
        elif parents:
            src.bot.shared.after_batch.append({"parents": parents.copy(), **entry})
            logger.info(f"after_file: queued {task_id} after {len(parents)} download(s)")
        else:
            # no downloads — start immediately
            asyncio.create_task(_run_after_file_directly(entry))
            logger.info(f"after_file: started {task_id} immediately")

        queued.append(entry)
        prev_key = task_id
        logger.info(f"after_file: queued {task_id} link={link}")

    summary = "📋 <b>After chain queued:</b>\n"
    for i, entry in enumerate(queued):
        summary += f"{i+1}. 📎 {html.escape(entry['link'][:80])} (<code>{entry['task_id']}</code>)\n"
    if parents:
        summary += f"\n⏳ First download will start after <b>{len(parents)}</b> download(s) complete"
    await bot.send_message(src.shared.ADMIN_ID, summary, parse_mode="HTML")
    return queued


async def _run_after_directly(m: Message, entry: dict):
    await bot.send_message(
        src.shared.ADMIN_ID,
        f"▶️ <b>After task starting (no wait):</b>\n{html.escape(entry['link'][:128])}",
        parse_mode="HTML"
    )
    await process_after_task(entry)


async def _run_after_file_directly(entry: dict):
    await process_after_task(entry)


async def process_after_task(task: dict) -> None:
    link = task["link"]
    task_id = task["task_id"]

    for attempt in range(3):
        delay = parse_after_delay()
        await asyncio.sleep(delay)

        metadata = await src.http_client.get_file_metadata(link)
        if metadata.success:
            options = get_uri_options(metadata)
            result = aria2.add_uris([link], options=options)
            gid = result.gid
            src.bot.shared.after_gid_map[task_id] = gid
            aria2.resume([result])
            safe_name = html.escape(result.name or link)
            await bot.send_message(
                src.shared.ADMIN_ID,
                f"▶️ <b>After download started:</b>\n📦 <b>{safe_name}</b> (<code>{gid}</code>)",
                parse_mode="HTML"
            )
            logger.info(f"after task {task_id} added: {link}, gid={gid}")
            return

        err_detail = f"{metadata.error} (HTTP {metadata.status_code})" if metadata.status_code else metadata.error
        logger.warning(f"after task {task_id} HEAD attempt {attempt+1}/3 failed: {link} — {err_detail}")
        if attempt < 2:
            await bot.send_message(
                src.shared.ADMIN_ID,
                f"⚠️ <b>After HEAD failed</b> (retry {attempt+1}/3):\n{html.escape(link[:128])}\n<code>{html.escape(err_detail)}</code>",
                parse_mode="HTML"
            )
            await asyncio.sleep(60)

    src.bot.shared.after_gid_map[task_id] = "__failed__"
    await bot.send_message(
        src.shared.ADMIN_ID,
        f"❌ <b>After task failed</b> (3 attempts):\n{html.escape(link[:128])}",
        parse_mode="HTML"
    )
    logger.error(f"after task {task_id} failed after 3 attempts: {link}")


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
        