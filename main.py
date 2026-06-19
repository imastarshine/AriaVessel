import asyncio
import html

import src.text
import src.configs
import src.bot.shared
import src.bot.upload
import src.bot.command_initialize
import src.bot.receiver

from src.logger import logger, cleanup_old_logs
from src.shared import ADMIN_ID

from src.aria2 import aria2
from src.aria2.statistics import get_total_size
from src.bot import bot

AFTER_NONE = src.bot.shared.AFTER_NONE


def _is_finished(gid: str) -> bool:
    try:
        dls = aria2.get_downloads([gid])
        if not dls:
            return True
        dl = dls[0]
        total = get_total_size(dl)
        if dl.status in ("complete", "error", "removed"):
            return True
        if 0 < total == dl.completed_length:
            return True
        return False
    except Exception:
        logger.warning(f"_is_finished: couldn't check gid={gid}, assuming not finished")
        return False


async def monitor():
    known: set[str] = {d.gid for d in aria2.get_downloads() if d.completed_length == get_total_size(d) and get_total_size(d) > 0}
    known_removed: set[str] = set()
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
    known_removed: set[str] = set()
    while True:
        await asyncio.sleep(10)

        try:
            if len(known_removed) > 1000:
                logger.debug("pruning known_removed")
                known_removed.clear()

            # --- single-parent queue ---
            for parent_key in list(src.bot.shared.after_queue.keys()):
                if parent_key not in src.bot.shared.after_queue:
                    continue
                tasks = src.bot.shared.after_queue[parent_key]
                if not tasks:
                    del src.bot.shared.after_queue[parent_key]
                    continue

                ready = False
                gid: str | None = None

                if parent_key == AFTER_NONE:
                    ready = True
                elif parent_key.startswith("__task_"):
                    gid = src.bot.shared.after_gid_map.get(parent_key)
                    if gid is None:
                        continue
                    if gid == "__failed__":
                        # HEAD failed — skip failed task, unblock chain
                        ready = True
                else:
                    gid = parent_key

                if not ready and gid:
                    if gid in known_removed or _is_finished(gid):
                        ready = True
                        known_removed.add(gid)

                if ready:
                    all_tasks = src.bot.shared.after_queue.pop(parent_key, [])
                    logger.info(f"after_queue ready: {parent_key} -> {len(all_tasks)} task(s)")
                    if parent_key.startswith("__task_") and parent_key in src.bot.shared.after_gid_map:
                        del src.bot.shared.after_gid_map[parent_key]
                    for task in all_tasks:
                        await src.bot.receiver.process_after_task(task)

            # --- batch queue (all parents must finish) ---
            batch_copy = src.bot.shared.after_batch.copy()
            src.bot.shared.after_batch.clear()
            processed_ids: set[str] = set()
            for batch in batch_copy:
                if batch.get("task_id") in processed_ids:
                    # already processed in this cycle (can happen with await yielding)
                    continue
                parents_left = [g for g in batch["parents"] if g not in known_removed and not _is_finished(g)]
                if not parents_left:
                    logger.info(f"after_batch ready: {batch.get('task_id', '?')} ({len(batch['parents'])} parent(s))")
                    await src.bot.receiver.process_after_task(batch)
                    task_id = batch.get("task_id", "")
                    if task_id and task_id in src.bot.shared.after_gid_map:
                        del src.bot.shared.after_gid_map[task_id]
                    processed_ids.add(task_id)
                else:
                    src.bot.shared.after_batch.append(batch)

        except Exception as e:
            logger.exception(f"after_worker error: {e}")


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

    src.bot.command_initialize.initialize()
    asyncio.create_task(monitor())
    asyncio.create_task(after_worker())
    logger.info("monitoring and after_worker tasks started")
    await bot.infinity_polling()


if __name__ == "__main__":
    src.configs.config.load()
    asyncio.run(main())
    src.configs.config.save()
