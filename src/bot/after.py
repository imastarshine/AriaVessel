import asyncio
import html
import random

from telebot.types import Message

import src.aria2
import src.aria2.statistics
import src.bot
import src.bot.shared
import src.configs
import src.shared
import src.text
from src.aria2 import aria2
from src.logger import logger


def parse_after_delay(raw: str) -> float:
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


def find_parent_gid(args: list[str], downloads: list) -> str | None:
    if len(args) == 0:
        return None
    first = args[0]
    # check if it's a gid (aria2 gid is 16 chars hex)
    if len(first) == 16 and all(c in "0123456789abcdef" for c in first):
        return first
    # check if it's an index
    if first.isdigit() or (first.startswith("[") and first.endswith("]")) or ("," in first and not first.startswith("[")):
        try:
            dl_list, _ = src.text.parse_idx(first, downloads)
            if dl_list:
                return dl_list[0].gid
        except (ValueError, IndexError):
            pass
    return None


async def after_command(m: Message):
    try:
        parts = m.text.split(maxsplit=2)
        if len(parts) < 2:
            await src.bot.bot.reply_to(m, "❌ Usage: /after &lt;http-link&gt; or /after &lt;idx&gt; &lt;http-link&gt; or /after &lt;gid&gt; &lt;http-link&gt;", parse_mode="HTML")
            return

        downloads = aria2.get_downloads()
        link: str = ""
        parent_gid: str | None = None

        if len(parts) == 2:
            link = parts[1]
            if not link.startswith(("http://", "https://")):
                await src.bot.bot.reply_to(m, "❌ The link must be http:// or https://", parse_mode="HTML")
                return
            if len(downloads) == 0:
                parent_gid = None
            else:
                parent_gid = downloads[-1].gid
        elif len(parts) >= 3:
            arg1 = parts[1]
            link = parts[2]
            if not link.startswith(("http://", "https://")):
                await src.bot.bot.reply_to(m, "❌ The link must be http:// or https://", parse_mode="HTML")
                return
            parent_gid = find_parent_gid([arg1], downloads)
            if parent_gid is None:
                await src.bot.bot.reply_to(
                    m,
                    f"❌ <b>Invalid ID or GID:</b> <code>{html.escape(arg1)}</code>",
                    parse_mode="HTML"
                )
                return

        if parent_gid:
            parent_dl = next((d for d in downloads if d.gid == parent_gid), None)
            is_finished = (
                parent_dl is None
                or parent_dl.status in ("complete", "error", "removed")
                or (0 < src.aria2.statistics.get_total_size(parent_dl) == parent_dl.completed_length)
            )
            if is_finished:
                parent_gid = None
            else:
                if parent_gid not in src.bot.shared.after_queue:
                    src.bot.shared.after_queue[parent_gid] = []
                src.bot.shared.after_queue[parent_gid].append(link)
                await src.bot.bot.reply_to(
                    m,
                    f"⏳ Will download after <code>{parent_gid}</code> completes:\n"
                    f"{html.escape(link[:128])}",
                    parse_mode="HTML"
                )
                logger.info(f"after_queue: added link '{link}' waiting for gid {parent_gid}")

        if not parent_gid:
            delay = parse_after_delay(src.configs.config.after_delay)
            await asyncio.sleep(delay)
            result = aria2.add_uris([link], options={"pause": "true"})
            gid = result.gid
            dl = aria2.get_downloads([gid])[0]
            safe_name = html.escape(dl.name or link)
            aria2.resume([dl])
            await src.bot.bot.reply_to(
                m,
                f"📦 <b>{safe_name}</b> (<code>{gid}</code>)\n"
                f"▶️ <b>Starting immediately</b>",
                parse_mode="HTML"
            )
            logger.info(f"after: added '{link}' immediately, gid={gid}")

    except Exception as e:
        logger.exception(f"after command error: {e}")
        await src.bot.bot.reply_to(
            m,
            f"❌ <b>Error:</b> <code>{html.escape(str(e))}</code>",
            parse_mode="HTML"
        )
