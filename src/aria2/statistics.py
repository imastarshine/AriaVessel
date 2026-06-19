from src.aria2 import aria2
import src.bot.shared
import src.text
import html

from aria2p import Download

AFTER_NONE = src.bot.shared.AFTER_NONE


def get_total_size(download: Download):
    return sum(f.length for f in download.files)


def is_completed(dl: Download) -> bool:
    total = get_total_size(dl)
    if dl.status == "complete":
        return True
    if 0 < total == dl.completed_length:
        return True
    return False


def _resolve_parent_label(parent_key: str) -> str | None:
    if parent_key == AFTER_NONE:
        return None
    if parent_key.startswith("__task_"):
        gid = src.bot.shared.after_gid_map.get(parent_key)
        if gid and gid != "__failed__":
            return gid
        return None
    return parent_key


def _build_after_block() -> str:
    block = ""
    for parent_key, tasks in src.bot.shared.after_queue.items():
        parent_label = _resolve_parent_label(parent_key)
        for task in tasks:
            truncated = task["link"][:128] if len(task["link"]) > 128 else task["link"]
            line = f"  📎 {html.escape(truncated)}"
            if parent_label:
                line += f" → after <code>{parent_label}</code>"
            block += line + "\n"

    for batch in src.bot.shared.after_batch:
        truncated = batch["link"][:128] if len(batch["link"]) > 128 else batch["link"]
        block += f"  📎 {html.escape(truncated)} → after <b>{len(batch['parents'])}</b> download(s)\n"

    return block


FILTER_ALL = "a"
FILTER_EXCLUDE_COMPLETED = "e"


def get_status(filter_str: str | None = None) -> list[str]:
    all_downloads = aria2.get_downloads()

    if filter_str == FILTER_EXCLUDE_COMPLETED:
        downloads = [(i, d) for i, d in enumerate(all_downloads) if not is_completed(d)]
    else:
        downloads = list(enumerate(all_downloads))

    if not downloads and not src.bot.shared.after_queue and not src.bot.shared.after_batch:
        return ["🤷 There are no torrents currently"]

    message_builder = src.text.MessageBuilder()

    for i, d in downloads:
        total = sum(f.length for f in d.files)
        size_str = src.text.format_size(total) if total > 0 else "unknown size"
        speed_str = src.text.format_speed(d.download_speed) + f" (eta: {d.eta_string(2)})" if d.download_speed else "0 B/s"

        safe_name = html.escape(d.name or f"Unknown (g:{d.gid})")

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
        bar = "📥 " + src.text.generate_progress_bar(progress_percent, 10) + " | "

        message_builder.add_chunk(
            f"🆔 <code>{i}</code> | <b>GID</b> <code>{d.gid}</code> | 📎 <b>{safe_name}</b>\n"
            f"{bar if status_icon == '🚀' else ''}📁 {size_str}\n"
            f"🏷️ {status_icon} {status_desc}\n\n"
        )

    # After queue info at the bottom
    after_block = _build_after_block()
    if after_block:
        message_builder.add_chunk("⏳ <b>After queue:</b>\n" + after_block)

    return message_builder.get_messages()
