from src.aria2 import aria2
import src.bot.shared
import src.text
import html

from src.logger import logger

from aria2p import Download

AFTER_NONE = src.bot.shared.AFTER_NONE


def get_total_size(download: Download):
    return sum(f.length for f in download.files)


def is_completed(dl: Download) -> bool:
    total = dl.total_length
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

    markdown = "## After\n---"
    text_block = src.text.MessageBuilder(max_length=16384)

    for parent_key, tasks in src.bot.shared.after_queue.items():
        parent_label = _resolve_parent_label(parent_key)
        for task in tasks:
            truncated = task["link"][:128] if len(task["link"]) > 128 else task["link"]
            url = f"{html.escape(truncated)}"
            after_gid = f"<code>{parent_label}</code>" if parent_label else "-"
            text_block.add_chunk(f"""<tr>
    <td>{url}</td>
    <td>{after_gid}</td>
</tr>""")

    for batch in src.bot.shared.after_batch:
        truncated = batch["link"][:128] if len(batch["link"]) > 128 else batch["link"]
        url = f"{html.escape(truncated)}"
        after_gid = f"<b>{len(batch['parents'])}</b> download(s)"
        text_block.add_chunk(f"""<tr>
    <td>{url}</td>
    <td>{after_gid}</td>
</tr>""")

    messages = text_block.get_messages()
    if len(messages) > 0:
        builded_text = "".join(messages)
        markdown += f"""
<table>
<tr>
    <td>URL</td>
    <td>Task</td>
</tr>
{builded_text}
</table>
"""
        return markdown
    else:
        return ""


FILTER_ALL = "a"
FILTER_EXCLUDE_COMPLETED = "e"


def get_status(filter_str: str | None = None) -> str:
    all_downloads = aria2.get_downloads()

    if filter_str == FILTER_EXCLUDE_COMPLETED:
        downloads = [(i, d) for i, d in enumerate(all_downloads) if not is_completed(d)]
    else:
        downloads = list(enumerate(all_downloads))

    markdown = "## Downloads\n---"
    text_builder = src.text.MessageBuilder(max_length=30_000)

    if len(downloads) == 0:
        markdown += "\n- 🤷 There are no downloads currently"
    else:


        markdown += "\n\n<table>"
        markdown += """\n    <tr>
    <td>#</td>
    <td>Name</td>
    <td>Size</td>
    <td>Progress</td>
    <td>ETA</td>
    <td>Status</td>
    </tr>"""

        for index, download in downloads:
            size_str = src.text.format_size(download.total_length) if download.total_length > 0 else "unknown size"
            eta_str = download.eta_string(2) if download.download_speed else "∞"
            speed_str = src.text.format_speed(download.download_speed) if download.download_speed else "0 B/s"

            progress_percent = download.progress / 100 if download.progress else 0.0
            progress_bar_str = src.text.generate_progress_bar(progress_percent, 10)

            safe_name = html.escape(download.name or f"Unknown (g:{download.gid})")

            if download.seeder:
                status_icon, status_desc = "✅", "Sharing"
            elif download.status == "active":
                status_icon, status_desc = "🚀", speed_str
            elif download.status == "paused":
                status_icon, status_desc = "⏸", "Paused"
            elif download.status == "error":
                status_icon, status_desc = "❌", f"Error: {download.error_message} ({download.error_code})"
            else:
                status_icon, status_desc = "⏳", download.status.capitalize()

            text_builder.add_chunk(f"""<tr>
        <td>{index}</td>
        <td>{safe_name} (<code>{download.gid}</code>)</td>
        <td align="right">{size_str}</td>
        <td>{progress_bar_str}</td>
        <td align="left">{eta_str}</td>
        <td>{status_icon} {status_desc}</td>
    </tr>""")

        markdown += "\n".join(text_builder.get_messages()) + f"\n</table>"

    after_block = _build_after_block()
    if after_block:
        markdown += f"\n\n{after_block}"

    logger.info(f"markdown length: {len(markdown)}")
    return markdown
