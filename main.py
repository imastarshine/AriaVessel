import asyncio

import src.text
import html
import src.configs
import src.bot.after
import src.bot.shared
import src.bot.upload
import src.bot.command_initialize

from src.logger import logger, cleanup_old_logs
from src.shared import ADMIN_ID

from src.aria2 import aria2
from src.aria2.statistics import get_total_size
from src.bot import bot

# ------------------------ #

async def monitor():
    known = {d.gid for d in aria2.get_downloads() if d.completed_length == get_total_size(d) and get_total_size(d) > 0}
    known_removed = set()
    logger.info(f"monitor initialized with {len(known)} known completed downloads")

    while True:
        await asyncio.sleep(15)
        message_parts = []
        message = ""

        try:
            dls = aria2.get_downloads()
            completed_gids = []
            for i, d in enumerate(dls):
                total = get_total_size(d)
                if 0 < total == d.completed_length and d.gid not in known:
                    logger.info(f"new download completed: {d.name} ({d.gid}), size: {src.text.format_size(total)}")
                    safe_name = html.escape(d.name)
                    message += f"📦 <b>{safe_name}</b> (<code>{d.gid}</code>)\n"
                    if len(message) > 3200:
                        message_parts.append(message)
                        message = ""
                    known.add(d.gid)
                    completed_gids.append(d.gid)

                elif d.status == "error" and d.gid not in known:
                    known.add(d.gid)
                    completed_gids.append(d.gid)

            for cgid in completed_gids:
                await process_after_completion(cgid)

            current_gids = {d.gid for d in dls}
            for parent_gid in list(src.bot.shared.resume_queue.keys()):
                if parent_gid not in current_gids and parent_gid not in known_removed:
                    known_removed.add(parent_gid)
                    await process_after_completion(parent_gid)
            for parent_gid in list(src.bot.shared.after_queue.keys()):
                if parent_gid not in current_gids and parent_gid not in known_removed:
                    known_removed.add(parent_gid)
                    await process_after_completion(parent_gid)
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


async def process_after_completion(completed_gid: str):
    await process_after_queue(completed_gid)
    await process_resume_queue(completed_gid)


async def process_after_queue(completed_gid: str):
    links = src.bot.shared.after_queue.pop(completed_gid, None)
    if not links:
        return

    for link in links:
        delay = src.bot.after.parse_after_delay(src.configs.config.after_delay)
        await asyncio.sleep(delay)
        result = aria2.add_uris([link], options={"pause": "true"})
        gid = result.gid
        aria2.resume([result])
        safe_name = html.escape(result.name or link)
        await bot.send_message(
            ADMIN_ID,
            f"▶️ <b>After queue started:</b>\n📦 <b>{safe_name}</b> (<code>{gid}</code>)",
            parse_mode="HTML"
        )
        logger.info(f"after_queue: started download {gid} for link {link}")


async def process_resume_queue(completed_gid: str):
    child_gids = src.bot.shared.resume_queue.pop(completed_gid, None)
    if not child_gids:
        return

    for child_gid in child_gids:
        delay = src.bot.after.parse_after_delay(src.configs.config.after_delay)
        await asyncio.sleep(delay)
        try:
            dls = aria2.get_downloads([child_gid])
            if dls:
                aria2.resume(dls)
                safe_name = html.escape(dls[0].name or "unknown")
                await bot.send_message(
                    ADMIN_ID,
                    f"▶️ <b>After chain resumed:</b>\n📦 <b>{safe_name}</b> (<code>{child_gid}</code>)",
                    parse_mode="HTML"
                )
                logger.info(f"resume_queue: resumed {child_gid} after {completed_gid}")
        except Exception as e:
            logger.error(f"resume_queue: failed to resume {child_gid}: {e}")


async def main():
    logger.info("cleaning old log files")
    cleanup_old_logs(days=14)
    logger.info("starting main bot")
    # TODO: Remo disk check on main(), and add bot log for this

    try:
        await src.bot.upload.disk.init()
        logger.info("yandex disk initialized successfully")
    except Exception as e:
        logger.error(f"failed to initialize yandex disk: {e}")

    try:
        downloads = aria2.get_downloads()
        logger.info(f"connected to aria2, {len(downloads)} active downloads")
    except Exception as e:
        logger.error(f"failed to connect to aria2: {e}")
        raise

    src.bot.command_initialize.initialize()
    asyncio.create_task(monitor())
    logger.info("monitoring task started")
    await bot.infinity_polling()


if __name__ == "__main__":
    src.configs.config.load()
    asyncio.run(main())
    src.configs.config.save()
