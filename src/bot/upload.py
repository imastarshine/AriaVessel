import html
from pathlib import Path

from aria2p import Download
from telebot.types import Message

import src.shared
import src.aria2
import src.aria2.statistics
import src.text
import src.bot
import src.bot.security
from src.logger import logger
from src.ydisk import YDisk

disk = YDisk()

is_uploading = False
uploading_amount_files = 0
uploading_current_file = ""
uploading_current_file_number = 0


async def upload_command(m: Message):
    global is_uploading, uploading_amount_files, uploading_current_file, uploading_current_file_number

    if is_uploading:
        await src.bot.bot.reply_to(
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
            await src.bot.bot.reply_to(m, f"❌ <b>Failed to get disk</b>", parse_mode="HTML")
            return

        parts = m.text.split()
        source_downloads = src.aria2.aria2.get_downloads()
        downloads, failed_list = src.text.parse_idx(parts[1], source_downloads)
        to_upload: list[Download] = []
        message_builder = src.text.MessageBuilder()

        for download in downloads:
            total_size = src.aria2.statistics.get_total_size(download)
            if download.completed_length == total_size and total_size > 0:
                to_upload.append(download)
            else:
                logger.warning(f"download not complete: {download.name}")
                message_builder.add_chunk(f"❌ {download.name} is not ready\n")
                continue

        for failed in failed_list:
            logger.warning(f"index parsing failed for: {failed}")
            message_builder.add_chunk(f"❌ {failed} failed\n")

        for failed_msg in message_builder.get_messages():
            await src.bot.bot.reply_to(m, failed_msg, parse_mode="HTML")

        if len(to_upload) <= 0:
            logger.info("no completed downloads found to upload")
            logger.info(f"parsed {len(downloads)} downloads, {len(failed_list)} failed to parse")
            await src.bot.bot.reply_to(m, "❌ <b>No files to upload</b>", parse_mode='HTML')
            return

        await src.bot.bot.reply_to(m, "☁️ <b>Starting to upload...</b>", parse_mode="HTML")

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
                    await src.bot.bot.send_message(src.shared.ADMIN_ID, f"❌ Failed to upload {rel_path}: {e}")

        is_uploading = False
        uploading_amount_files = 0
        uploading_current_file = ""
        uploading_current_file_number = 0

        logger.info(f"upload session finished: {success_uploaded_files}/{total_files} success")
        await src.bot.bot.reply_to(m,
                           f"✅ <b>All files uploaded!</b>\nSuccessfully uploaded: <code>{success_uploaded_files}</code> files",
                           parse_mode="HTML")

    except Exception as e:
        is_uploading = False
        uploading_amount_files = 0
        uploading_current_file = ""
        uploading_current_file_number = 0
        logger.exception(f"critical error in upload_cmd: {e}")
        await src.bot.bot.reply_to(m, f"❌ <b>An error occurred:</b> <code>{e}</code>", parse_mode="HTML")


async def upload_status_command(m: Message):
    global is_uploading, uploading_amount_files, uploading_current_file, uploading_current_file_number

    if not is_uploading:
        logger.info("upload status requested but no active upload")
        await src.bot.bot.reply_to(m, f"❌ <b>Not uploading right now</b>", parse_mode="HTML")
        return

    logger.info(f"upload status requested: {uploading_current_file_number}/{uploading_amount_files} files processed")
    await src.bot.bot.reply_to(
        m,
        f"📎 <b>Uploading</b> <code>{html.escape(uploading_current_file)}</code> ({uploading_current_file_number}/{uploading_amount_files})",
        parse_mode="HTML"
    )


async def upload_cancel_command(m: Message):
    global is_uploading
    if is_uploading:
        is_uploading = False
        await src.bot.bot.reply_to(m, "🛑 <b>Upload cancelled.</b>", parse_mode="HTML")
    else:
        await src.bot.bot.reply_to(m, "❌ <b>No active upload.</b>", parse_mode="HTML")
