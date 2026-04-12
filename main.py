import asyncio
import aria2p
import zipfile
import shutil
import typing
import src.text
import html
from pathlib import Path

from aria2p import Download
from telebot.async_telebot import AsyncTeleBot
from telebot.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery

from src.logger import logger, cleanup_old_logs
from src.shared import ADMIN_ID, BOT_TOKEN, ARIA2_SECRET
from src.text import generate_progress_bar
from src.ydisk import YDisk

ACTION_TO_TEXT = {
    "pause": "⏸️ Paused",
    "resume": "▶️ Resume",
    "rm": "🗑️ Deleted torrent",
    "del": "🧹 Fully deleted"
}

bot = AsyncTeleBot(BOT_TOKEN)
aria2 = aria2p.API(aria2p.Client(host="http://localhost", port=6800, secret=ARIA2_SECRET))
disk = YDisk()
pending_torrents = {}

is_uploading = False
uploading_amount_files = 0
uploading_current_file = ""
uploading_current_file_number = 0


def restricted(func: typing.Callable) -> typing.Callable:
    async def wrapper(message: Message, *args, **kwargs):
        if message.from_user.id == ADMIN_ID:
            return await func(message, *args, **kwargs)
        else:
            logger.warning(f"user {message.from_user.username} {message.from_user.id} not allowed")
        return False

    return wrapper


def get_total_size(download):
    return sum(f.length for f in download.files)


def get_status() -> list[str]:
    message_parts = []
    message = ""
    downloads = aria2.get_downloads()

    if len(downloads) <= 0:
        return ["🤷 There are no torrents currently"]

    for i, d in enumerate(downloads):
        total = sum(f.length for f in d.files)
        size_str = src.text.format_size(total) if total > 0 else "unknown size"
        speed_str = src.text.format_speed(d.download_speed)

        safe_name = html.escape(d.name)

        if d.seeder:
            status_icon, status_desc = "✅", "Sharing"
        elif d.status == "active":
            status_icon, status_desc = "🚀", speed_str
        elif d.status == "paused":
            status_icon, status_desc = "⏸", "Paused"
        elif d.status == "error":
            status_icon, status_desc = "❌", f"Error: {d.error_message} ({d.error_code})"
        else:
            status_icon, status_desc = "⏳", d.status.capitalize()

        progress_percent = d.progress / 100 if d.progress else 0.0
        bar = "📥 " + generate_progress_bar(progress_percent, 10) + " | "

        message += (
            f"🆔 <code>{i}</code> | 📎 <b>{safe_name}</b>\n"
            f"{bar if status_icon == '🚀' else ''}📁 {size_str}\n"
            f"🏷️ {status_icon} {status_desc}\n\n"
        )
        if len(message) > 3200:
            message_parts.append(message)
            message = ""

    if len(message) > 0:
        message_parts.append(message)

    return message_parts


@bot.message_handler(commands=['start'])
@restricted
async def start(m):
    await bot.reply_to(m, "📊 <b>Available commands:</b>\n\n"
                          "⏸️ <code>/pause</code> - Pause torrent(s)\n"
                          "▶️ <code>/play</code> - Resume torrent(s)\n"
                          "🗑️ <code>/rm</code> - Remove torrent from client\n"
                          "🧹 <code>/del</code> - Delete torrent and files\n"
                          "💿 <code>/upload</code> - Upload completed files to Yandex.Disk\n"
                          "❌ <code>/upload_cancel</code> - Cancel uploading\n"
                          "📊 <code>/upload_status</code> - Upload status\n\n"
                          "📎 Send <code>.torrent</code>, <code>.zip</code> archive, or <code>magnet:</code> link",
                       parse_mode="HTML")


@bot.message_handler(commands=['status'])
@restricted
async def status(m: Message):
    logger.info(f"status command received from user {m.from_user.id}")
    torrent_status = get_status()

    if len(torrent_status) == 1 and torrent_status[0] == "🤷 There are no torrents currently":
        logger.info("no active torrents found")
    else:
        logger.info(f"returning status of {len(torrent_status)} torrent(s)")
        
    for msg in torrent_status:
        await bot.reply_to(m, msg, parse_mode="HTML")


@bot.message_handler(commands=['upload'])
@restricted
async def upload_cmd(m: Message):
    global is_uploading, uploading_amount_files, uploading_current_file, uploading_current_file_number

    if is_uploading:
        await bot.reply_to(
            m,
            f"<b>A previous operation was still running. Wait until it's done.</b>",
            parse_mode="HTML"
        )
        return

    try:
        logger.info(f"received upload command: {m.text}")
        logger.info(f"upload command from user {m.from_user.id}, message id: {m.message_id}")
        if not await disk.check():
            logger.error("yadisk token check failed")
            await bot.reply_to(m, f"❌ <b>Failed to get disk</b>", parse_mode="HTML")
            return

        parts = m.text.split()
        source_downloads = aria2.get_downloads()
        downloads, failed_list = src.text.parse_idx(parts[1], source_downloads)
        to_upload: list[Download] = []

        message_parts = []
        message = ""

        for download in downloads:
            if download.completed_length == get_total_size(download) and get_total_size(download) > 0:
                to_upload.append(download)
            else:
                logger.warning(f"download not complete: {download.name}")
                message += f"❌ {download.name} is not ready\n"
                if len(message) > 3500:
                    message_parts.append(message)
                    message = ""
                continue

        for failed in failed_list:
            logger.warning(f"index parsing failed for: {failed}")
            message += f"❌ {failed} failed\n"
            if len(message) > 3500:
                message_parts.append(message)
                message = ""

        for failed_msg in message_parts:
            await bot.reply_to(m, failed_msg, parse_mode="HTML")

        message_parts.clear()

        if len(to_upload) <= 0:
            logger.info("no completed downloads found to upload")
            logger.info(f"parsed {len(downloads)} downloads, {len(failed_list)} failed to parse")
            await bot.reply_to(m, "❌ <b>No files to upload</b>", parse_mode='HTML')
            return

        await bot.reply_to(m, "☁️ <b>Starting to upload...</b>", parse_mode="HTML")

        total_files = sum(len(d.files) for d in to_upload)
        logger.info(f"starting upload of {total_files} files from {len(to_upload)} downloads")

        success_uploaded_files = 0
        is_uploading = True
        uploading_amount_files = total_files
        current_file_idx = 0

        for download in to_upload:
            if not is_uploading:
                logger.warning('stopping due to cancel request')
                return

            base_dir = Path(download.dir)
            logger.info(f"processing download: {download.name} in {base_dir}")
            logger.info(f"download has {len(download.files)} files to upload")

            for file in download.files:
                uploading_current_file_number += 1
                current_file_idx += 1
                full_path_obj = file.path
                uploading_current_file = full_path_obj.name

                try:
                    rel_path = full_path_obj.relative_to(base_dir)
                except ValueError:
                    rel_path = full_path_obj.name

                target_yandex_path = f"app:/downloads/{rel_path}"
                logger.info(f"uploading file {current_file_idx}/{total_files}: {rel_path}")

                try:
                    await disk.upload(str(full_path_obj), target_yandex_path)
                    success_uploaded_files += 1
                except Exception as e:
                    logger.error(f"failed to upload {rel_path}: {e}")
                    await bot.send_message(ADMIN_ID, f"❌ Failed to upload {rel_path}: {e}")

        is_uploading = False
        uploading_amount_files = 0
        uploading_current_file = ""
        uploading_current_file_number = 0

        logger.info(f"upload session finished: {success_uploaded_files}/{total_files} success")
        await bot.reply_to(m, f"✅ <b>All files uploaded!</b>\nSuccessfully uploaded: <code>{success_uploaded_files}</code> files", parse_mode="HTML")

    except Exception as e:
        is_uploading = False
        uploading_amount_files = 0
        uploading_current_file = ""
        uploading_current_file_number = 0
        logger.exception(f"critical error in upload_cmd: {e}")
        await bot.reply_to(m, f"❌ <b>An error occurred:</b> <code>{e}</code>", parse_mode="HTML")


@bot.message_handler(commands=['upload_status'])
@restricted
async def upload_status_cmd(m: Message):
    global is_uploading, uploading_amount_files, uploading_current_file, uploading_current_file_number

    if not is_uploading:
        logger.info("upload status requested but no active upload")
        await bot.reply_to(m, f"❌ <b>Not uploading right now</b>", parse_mode="HTML")
        return

    logger.info(f"upload status requested: {uploading_current_file_number}/{uploading_amount_files} files processed")
    await bot.reply_to(
        m,
        f"📎 <b>Uploading</b> <code>{html.escape(uploading_current_file)}</code> ({uploading_current_file_number}/{uploading_amount_files})",
        parse_mode="HTML"
    )


@bot.message_handler(commands=['upload_cancel'])
@restricted
async def upload_cancel(m: Message):
    global is_uploading
    if is_uploading:
        is_uploading = False
        await bot.reply_to(m, "🛑 <b>Upload cancelled.</b>", parse_mode="HTML")
    else:
        await bot.reply_to(m, "❌ <b>No active upload.</b>", parse_mode="HTML")


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


@bot.message_handler(commands=["inspect"])
async def inspect_command(m: Message):
    try:
        idx = int(m.text.split()[1])
        dls = aria2.get_downloads()
        if idx >= len(dls):
            await bot.reply_to(m, "❌ <b>The index you specified doesnt exist</b>", parse_mode="HTML")
            return

        d = dls[idx]

        files_info = "\n".join([f"📄 {f.path.split('/')[-1]} ({src.text.format_size(f.length)})" for f in d.files[:5]])
        if len(d.files) > 5:
            files_info += f"\n... and {len(d.files) - 5} files more"

        report = (
            f"🔍 <b>Inspection for</b>\n"
            f"📎 <code>{html.escape(d.name)}</code>\n\n"
            f"🆔 GID: <code>{d.gid}</code>\n"
            f"🚦 Status: <b>{d.status}</b>\n"
            f"📍 Path: <code>{d.dir}</code>\n"
            f"👥 Peers: {d.connections}\n"
            f"🧲 Magnet: {'Yes' if d.is_metadata else 'No'}\n"
            f"⚠️ Error: {d.error_message if d.error_message else 'no'}\n\n"
            f"<b>Files:</b>\n{files_info}"
        )

        await bot.send_message(m.chat.id, report, parse_mode="HTML")
    except Exception as e:
        await bot.reply_to(m, f"❌ <b>An error on inspection</b>: {e}", parse_mode="HTML")


@bot.message_handler(commands=['pause', 'resume', 'rm', 'del'])
@restricted
async def control(m: Message):
    # rm deleting torrent from session, with file saving
    # del deleting torrent and files
    # TODO: Add to status all file size

    try:
        parts = m.text.split()
        if len(parts) < 2:
            await bot.reply_to(m, "❌ Specify ID(s). Example: <code>/pause 0</code>", parse_mode="HTML")
            return
        cmd = parts[0].lower().removeprefix("/")
        source_downloads = aria2.get_downloads()
        downloads, failed_list = src.text.parse_idx(parts[1], source_downloads)

        message_parts = []
        message = ""
        operation_results = control_action(cmd, downloads)
        for result, download in zip(operation_results, downloads):
            logger.info(f"result={result}, download name='{download}' {download.name} + gid {download.gid}")
            safe_name = html.escape(download.name)
            if result is True:
                message += f"✅📦 <b>{safe_name}</b> (<code>{download.gid}</code>)\n"
            else:
                message += f"❌📦 <b>{safe_name}</b> (<code>{download.gid}</code>)\n"

            if len(message) > 3200:
                message_parts.append(message)
                message = ""

        for failed in failed_list:
            message += f"❓ {failed}\n"

        if len(message) > 0:
            message_parts.append(message)

        for index, part in enumerate(message_parts):
            if index == 0:
                part = ACTION_TO_TEXT.get(cmd) + "\n\n" + part

            await bot.reply_to(m, part, parse_mode='HTML')
    except Exception as e:
        logger.exception(f"an exception occurred on control: {e}")
        await bot.reply_to(
            m,
            f"❌ <b>An error occurred:</b> <code>{html.escape(str(e))}</code>\n\nDid you write a correct id?\nUsage: <code>/[resume,pause,rm,del] &lt;id&gt;</code>",
            parse_mode="HTML"
        )


@bot.message_handler(content_types=['document', 'text'])
@restricted
async def handle_source(m: Message):
    logger.info(f"new message id: {m.message_id}")
    tmp_dir: Path | None = None

    added = []
    try:
        if m.content_type == 'document':
            if m.document.file_name.endswith('.zip'):
                tmp_dir = Path() / f"tmp_{m.message_id}"
                tmp_dir.mkdir(parents=True, exist_ok=True)

                info = await bot.get_file(m.document.file_id)
                content = await bot.download_file(info.file_path)
                archive_path = tmp_dir / f"archive.zip"
                with archive_path.open("wb") as f:
                    f.write(content)

                with zipfile.ZipFile(archi8ve_path, 'r') as z:
                    z.extractall(tmp_dir)

                for f in tmp_dir.rglob('*.torrent'):
                    added.append(aria2.add_torrent(f, options={"pause": "true"}))
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
        elif m.text and m.text.startswith('magnet:'):
            added.append(aria2.add_magnet(m.text, options={"pause": "true"}))

        logger.info(f"Added {len(added)} new torrents")
        if added:
            pending_torrents[ADMIN_ID] = [d.gid for d in added]
            logger.info(f"pending torrents: {pending_torrents}")
            messages = []
            message = "Found:\n"
            for i, d in enumerate(added):
                if len(message) > 3500:
                    messages.append(message)
                    message = ""
                    await asyncio.sleep(0.05)

                safe_name = html.escape(d.name)
                message += f"📦 <b>{safe_name}</b> ({src.text.format_size(get_total_size(d))})\n"

            if len(message) > 0:
                messages.append(message)

            if len(message) > 0:
                for index, msg in enumerate(messages):
                    markup = None
                    if index == len(messages) - 1:
                        markup = InlineKeyboardMarkup()
                        markup.row(
                            InlineKeyboardButton("Add", callback_data=f"confirm_y", style="success"),
                            InlineKeyboardButton("Cancel", callback_data=f"confirm_n", style="danger")
                        )
                    logger.debug(f"index: {index}, msg: {msg}")
                    await bot.send_message(ADMIN_ID, message, reply_markup=markup, parse_mode="HTML")
    except Exception as e:
        logger.exception(f"an error occurred on handle_source: {e}")
        await bot.send_message(ADMIN_ID, f"❌ <b>Got error:</b> <code>{html.escape(str(e))}</code>", parse_mode="HTML")
    finally:
        if tmp_dir and tmp_dir.exists():
            shutil.rmtree(tmp_dir)


@bot.callback_query_handler(func=lambda call: call.data.startswith("confirm_"))
@restricted
async def confirm_callback(call: CallbackQuery):
    # gids: list[aria2p.Download] = pending_torrents.pop(ADMIN_ID, [])
    gids: list[str] = pending_torrents.pop(ADMIN_ID, [])
    logger.debug(f"pending_torrents: {pending_torrents}")

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
            # TODO: To try
            await bot.delete_message(call.message.chat.id, call.message.id)
    except Exception as e:
        logger.exception(f"an error occurred on confirm_callback: {e}")
        await bot.send_message(call.message.chat.id, text=f"❌ <b>Got error on confirmation:</b> <code>{html.escape(str(e))}</code>", parse_mode="HTML")


# ------------------------ #

async def monitor():
    known = {d.gid for d in aria2.get_downloads() if d.completed_length == get_total_size(d) and get_total_size(d) > 0}
    logger.info(f"monitor initialized with {len(known)} known completed downloads")

    while True:
        await asyncio.sleep(15)
        message_parts = []
        message = ""

        try:
            dls = aria2.get_downloads()
            for i, d in enumerate(dls):
                total = get_total_size(d)
                if 0 < total == d.completed_length and d.gid not in known:
                    # TODO: We can add auto disable seeding

                    logger.info(f"new download completed: {d.name} ({d.gid}), size: {src.text.format_size(total)}")
                    safe_name = html.escape(d.name)
                    message += f"📦 <b>{safe_name}</b> (<code>{d.gid}</code>)\n"
                    if len(message) > 3200:
                        message_parts.append(message)
                        message = ""

                    known.add(d.gid)
        except Exception as e:
            logger.exception(f"an error occurred on monitor: {e}")
            continue

        if len(message) > 0:
            message_parts.append(message)

        try:
            for index, msg in enumerate(message_parts):
                if index == 0:
                    msg = "✅ Downloaded:\n\n" + msg
                await bot.send_message(ADMIN_ID, msg, parse_mode="HTML")
        except Exception as e:
            logger.exception(f"an error occurred on message send in monitor: {e}")


async def main():
    logger.info("cleaning old log files")
    cleanup_old_logs(days=14)
    logger.info("starting main bot")
    # TODO: Remo disk check on main(), and add bot log for this
    
    try:
        await disk.init()
        logger.info("yandex disk initialized successfully")
    except Exception as e:
        logger.error(f"failed to initialize yandex disk: {e}")
        raise
        
    try:
        downloads = aria2.get_downloads()
        logger.info(f"connected to aria2, {len(downloads)} active downloads")
    except Exception as e:
        logger.error(f"failed to connect to aria2: {e}")
        raise
        
    asyncio.create_task(monitor())
    logger.info("monitoring task started")
    await bot.infinity_polling()


if __name__ == "__main__":
    asyncio.run(main())
