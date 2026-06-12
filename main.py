import asyncio

import src.text
import html
import src.configs
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
