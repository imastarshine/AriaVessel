from src.aria2 import aria2
import src.bot.shared
import src.text
import html

from aria2p import Download

AFTER_NONE = src.bot.shared.AFTER_NONE


def get_total_size(download: Download):
    return sum(f.length for f in download.files)


def get_status() -> list[str]:
    downloads = aria2.get_downloads()

    if not downloads and not src.bot.shared.after_queue:
        return ["🤷 There are no torrents currently"]

    message_builder = src.text.MessageBuilder()

    for i, d in enumerate(downloads):
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

        after_info = ""
        if d.gid in src.bot.shared.after_queue:
            after_info = "\n\n⏳ <b>After:</b>\n"
            for task in src.bot.shared.after_queue[d.gid]:
                truncated = task["link"][:128] if len(task["link"]) > 128 else task["link"]
                after_info += f"  📎 {html.escape(truncated)}\n"

        message_builder.add_chunk(
            f"🆔 <code>{i}</code> | <b>GID</b> <code>{d.gid}</code> | 📎 <b>{safe_name}</b>\n"
            f"{bar if status_icon == '🚀' else ''}📁 {size_str}\n"
            f"🏷️ {status_icon} {status_desc}"
            f"{after_info}\n\n"
        )

    # Show queued items with no parent
    none_tasks = src.bot.shared.after_queue.get(AFTER_NONE)
    if none_tasks:
        msg = "\n⏳ <b>Queued (immediate):</b>\n"
        for task in none_tasks:
            truncated = task["link"][:128] if len(task["link"]) > 128 else task["link"]
            msg += f"  📎 {html.escape(truncated)}\n"
        message_builder.add_chunk(msg)

    return message_builder.get_messages()
