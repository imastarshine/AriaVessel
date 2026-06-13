from src.aria2 import aria2
import src.bot.shared
import src.text
import html

from aria2p import Download

def get_total_size(download: Download):
    return sum(f.length for f in download.files)


def get_status() -> list[str]:
    downloads = aria2.get_downloads()

    if len(downloads) <= 0 and not src.bot.shared.after_queue and not src.bot.shared.resume_queue:
        return ["🤷 There are no torrents currently"]

    message_builder = src.text.MessageBuilder()

    for i, d in enumerate(downloads):
        total = sum(f.length for f in d.files)
        size_str = src.text.format_size(total) if total > 0 else "unknown size"
        speed_str = src.text.format_speed(d.download_speed) + f" (eta: {d.eta_string(2)})" if d.download_speed else ""

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
            links = src.bot.shared.after_queue[d.gid]
            after_info = "\n⏳ <b>After:</b>\n"
            for link in links:
                truncated = link[:128] if len(link) > 128 else link
                after_info += f"  📎 {html.escape(truncated)}\n"
        if d.gid in src.bot.shared.resume_queue:
            child_gids = src.bot.shared.resume_queue[d.gid]
            child_info = "\n⏳ <b>After (chain):</b>\n"
            dl_map = {dl.gid: dl for dl in downloads}
            for cgid in child_gids:
                cd = dl_map.get(cgid)
                name = html.escape(cd.name) if cd else cgid[:16]
                child_info += f"  ▶️ {name} (<code>{cgid}</code>)\n"
            after_info += child_info

        message_builder.add_chunk(
            f"🆔 <code>{i}</code> | <b>GID</b> <code>{d.gid}</code> | 📎 <b>{safe_name}</b>\n"
            f"{bar if status_icon == '🚀' else ''}📁 {size_str}\n"
            f"🏷️ {status_icon} {status_desc}"
            f"{after_info}\n\n"
        )

    return message_builder.get_messages()
