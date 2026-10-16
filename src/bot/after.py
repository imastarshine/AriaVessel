import asyncio
import dataclasses
import html
from telebot.types import Message

import aria2p.client

import src.lists
import uuid
import src.aria2
import src.http_client
import src.text
import src.bot.message
from src.logger import logger


@dataclasses.dataclass(eq=True)
class After:
    id: str
    link: str
    parents: list[str] | None = None

after_tasks: list[After] = []

MAX_ATTEMPTS = 3
RETRY_WAIT_SECONDS = 60
ERROR_WAIT_SECONDS = 10


def is_after_task_id_in_after_tasks(task_id):
    return any([True if item.id == task_id else False for item in after_tasks])


def add_task(link: str, parents: list[str] | None):
    if not link.startswith(("http://", "https://")):
        raise ValueError(f"link must start with http:// or https://, got: {link}")

    task_id = "after-" + str(uuid.uuid4())[:8]
    after_tasks.append(After(task_id, link, parents))
    logger.debug(f"after task added: id {task_id}, link {link}, parents {parents} (queue: {len(after_tasks)})")


async def check():
    """Run only from main loop"""

    if not after_tasks:
        return

    logger.debug(f"after check: {len(after_tasks)} task(s) in queue")

    for item in reversed(after_tasks):
        amount_parents = len(item.parents) if item.parents is not None else 0

        if amount_parents <= 0:
            can_be_started = True
        else:
            blockers = []
            for parent in item.parents:
                if parent.startswith("after-"):
                    if is_after_task_id_in_after_tasks(parent):
                        blockers.append(parent)
                else:
                    try:
                        download: aria2p.downloads.Download = src.aria2.aria2.get_download(parent)
                        if download.status not in ("complete", "error", "removed",):
                            blockers.append(f"{parent} ({download.status})")
                    except aria2p.client.ClientException as e:
                        if e.code == 1:
                            # GID is not found — parent already gone, safe to continue
                            logger.debug(f"after task {item.id}: parent {parent} not found, treating as done")
                        else:
                            logger.warning(f"after task {item.id}: parent {parent} check failed (code {e.code}): {e.message}")
                            blockers.append(f"{parent} (check failed)")

            can_be_started = not blockers
            if not can_be_started:
                logger.debug(f"after task {item.id} waiting for: {', '.join(blockers)}")

        if can_be_started:
            link = item.link
            logger.info(f"after task {item.id}: starting download {link} (parents: {item.parents})")
            last_error = "unknown error"
            is_successful = False

            for attempt in range(1, MAX_ATTEMPTS + 1):
                try:
                    metadata = await src.http_client.get_file_metadata(link)
                    if metadata.success:
                        options = src.http_client.get_uri_options(metadata)
                        result = src.aria2.aria2.add_uris([link], options=options)
                        src.aria2.aria2.resume([result])
                        safe_name = html.escape(result.name or link)
                        await src.bot.message.try_to_send_message(
                            f"▶️ <b>After download started:</b>\n📦 <b>{safe_name}</b> (<code>{result.gid}</code>)",
                            parse_mode="HTML"
                        )
                        logger.info(f"after task {item.id}: started as gid {result.gid} ({safe_name})")
                        for other in after_tasks:
                            if other.parents and item.id in other.parents:
                                other.parents.append(result.gid)
                        is_successful = True
                        break

                    last_error = metadata.error or f"HTTP {metadata.status_code}"
                    logger.warning(f"after task {item.id}: HEAD attempt {attempt}/{MAX_ATTEMPTS} failed: {last_error} — {link}")
                    if attempt < MAX_ATTEMPTS:
                        await src.bot.message.try_to_send_message(
                            f"⚠️ <b>After HEAD failed</b> (retry {attempt}/{MAX_ATTEMPTS}):\n{html.escape(link)}\n<code>{html.escape(last_error)}</code>",
                            parse_mode="HTML"
                        )
                        await asyncio.sleep(RETRY_WAIT_SECONDS)
                except Exception as e:
                    last_error = str(e)
                    logger.warning(f"after task {item.id}: attempt {attempt}/{MAX_ATTEMPTS} raised: {e}", exc_info=True)
                    if attempt < MAX_ATTEMPTS:
                        await asyncio.sleep(ERROR_WAIT_SECONDS)

            if not is_successful:
                await src.bot.message.try_to_send_message(
                    f"⚠️ <b>Failed to start after task</b>\nID: <code>{item.id}</code>\nLink: <code>{html.escape(item.link)}</code>\nReason: <code>{html.escape(last_error)}</code>",
                    parse_mode="HTML"
                )
                logger.error(f"after task {item.id}: giving up after {MAX_ATTEMPTS} attempt(s): {last_error}")

            logger.info(f"after task {item.id}: removed from queue")
            after_tasks.remove(item)


async def after_command(m: Message):
    try:
        parts = m.text.split(maxsplit=2)
        if len(parts) < 2:
            await src.bot.message.try_to_reply(m, "❌ Usage: /after <link> or /after <idx|gid|after-id> <link>", parse_mode="HTML")
            return

        link = parts[-1]
        if not link.startswith(("http://", "https://")):
            await src.bot.message.try_to_reply(m, "❌ The link must be http:// or https://", parse_mode="HTML")
            return

        if len(parts) == 3:
            parent = parts[1]

            if parent.startswith("after-"):
                if not is_after_task_id_in_after_tasks(parent):
                    await src.bot.message.try_to_reply(m, f"❌ Unknown after-id specified: {parent}", parse_mode="HTML")
                    return
                parents = [parent]
            else:
                try:
                    downloads, _ = src.text.parse_idx(parent, src.aria2.aria2.get_downloads())
                except (ValueError, IndexError):
                    downloads = []

                if not downloads:
                    await src.bot.message.try_to_reply(m, f"❌ Invalid GID/IDX specified: {parent}", parse_mode="HTML")
                    return
                parents = [downloads[0].gid]

            logger.info(f"adding new after task: {link} and {parents} (specified ID)")
            add_task(link, parents)
            await src.bot.message.try_to_reply(m, f"⏳ Queued ⎯ will start after <code>{parents[0]}</code>", parse_mode="HTML")
            return

        last_task = src.lists.safe_get_from_list(after_tasks, -1)

        logger.info(
            f"adding new after task: {link} and {last_task.id if last_task else 'None (not found)'} (not specified ID)")
        add_task(link, [last_task.id] if last_task else None)

        if last_task:
            await src.bot.message.try_to_reply(m, f"⏳ Queued ⎯ will start after <code>{last_task.id}</code>", parse_mode="HTML")
        else:
            await src.bot.message.try_to_reply(m, "⏳ Queued ⎯ will start immediately", parse_mode="HTML")
    except Exception as e:
        logger.exception(f"after command error: {e}", exc_info=True)
        await src.bot.message.try_to_reply(m, f"❌ <b>Error:</b> <code>{html.escape(str(e))}</code>", parse_mode="HTML")
