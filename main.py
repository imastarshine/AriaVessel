import asyncio
import html

from telebot import asyncio_helper

import src.text
import src.configs
import src.bot.shared
import src.bot.upload
import src.bot.command_initialize
import src.bot.receiver
import src.bot.after

from src.logger import logger, cleanup_old_logs
from src.shared import ADMIN_ID

from src.aria2 import aria2
from src.aria2.statistics import get_total_size
from src.bot import bot


async def monitor():
    known: set[str] = {d.gid for d in aria2.get_downloads() if d.completed_length == get_total_size(d) and get_total_size(d) > 0}
    logger.info(f"monitor initialized with {len(known)} known completed downloads")

    while True:
        await asyncio.sleep(15)
        message_parts = []
        message = ""

        try:
            dls = aria2.get_downloads()
            for d in dls:
                total = get_total_size(d)
                if 0 < total == d.completed_length and d.gid not in known:
                    logger.info(f"new download completed: {d.name} ({d.gid}), size: {src.text.format_size(total)}")
                    safe_name = html.escape(d.name)
                    message += f"📦 <b>{safe_name}</b> (<code>{d.gid}</code>)\n"
                    if len(message) > 3200:
                        message_parts.append(message)
                        message = ""
                    known.add(d.gid)

                elif d.status == "error" and d.gid not in known:
                    known.add(d.gid)
        except Exception as e:
            logger.exception(f"an error occurred on monitor: {e}")
            continue

        if message:
            message_parts.append(message)

        try:
            for index, msg in enumerate(message_parts):
                if index == 0:
                    msg = "✅ Downloaded:\n\n" + msg
                await bot.send_message(ADMIN_ID, msg, parse_mode="HTML")
        except Exception as e:
            logger.exception(f"an error occurred on message send in monitor: {e}")


async def after_worker():
    while True:
        await asyncio.sleep(10)

        try:
            await src.bot.after.check()
        except Exception as e:
            logger.warning(f"an exception occurred on after_worker: {e}", exc_info=True)


async def main():
    logger.info("cleaning old log files")
    cleanup_old_logs(days=14)
    logger.info("starting main bot")

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

    if (src.shared.TELEGRAM_BOT_SOCKS5_PROXY
            and isinstance(src.shared.TELEGRAM_BOT_SOCKS5_PROXY, str)
            and src.shared.TELEGRAM_BOT_SOCKS5_PROXY.startswith("socks5")):
        asyncio_helper.proxy = src.shared.TELEGRAM_BOT_SOCKS5_PROXY

    src.bot.command_initialize.initialize()
    asyncio.create_task(monitor())
    asyncio.create_task(after_worker())
    logger.info("monitoring and after_worker tasks started")
    await bot.infinity_polling()


if __name__ == "__main__":
    src.configs.config.load()
    asyncio.run(main())
    src.configs.config.save()
