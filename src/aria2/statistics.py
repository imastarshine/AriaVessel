from src.aria2 import aria2
import src.bot.after
import src.text
import html

from aria2p import Download


def get_total_size(download: Download):
    return sum(f.length for f in download.files)


def is_completed(dl: Download) -> bool:
    total = dl.total_length
    if dl.status == "complete":
        return True
    if 0 < total == dl.completed_length:
        return True
    return False


def _build_download_row(index: int, download: Download) -> str:
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

    return f"""<tr>
<td>{index}</td>
<td>{safe_name} (<code>{download.gid}</code>)</td>
<td align="right">{size_str}</td>
<td>{progress_bar_str}</td>
<td align="left">{eta_str}</td>
<td>{status_icon} {status_desc}</td>
</tr>"""


def _build_after_rows() -> list[str]:
    rows: list[str] = []

    for task in src.bot.after.after_tasks:
        truncated = f"{task.link[:128]}. . ." if len(task.link) > 128 else task.link
        url = html.escape(truncated)
        parents = ", ".join([html.escape(parent) for parent in task.parents]) if task.parents and len(task.parents) > 0 else "Does not have parents."
        parents = f"<code>{parents}</code>"
        rows.append(f"""<tr>
<td><code>{task.id}</code></td>
<td>{url}</td>
<td>{parents}</td>
</tr>""")

    return rows


def _join_into_messages(
    download_rows: list[str],
    after_rows: list[str],
    max_len: int = 30100,
) -> list[str]:
    messages: list[str] = []

    current = "## Downloads\n---\n\n<table>\n<tr>\n<td>#</td>\n<td>Name</td>\n<td>Size</td>\n<td>Progress</td>\n<td>ETA</td>\n<td>Status</td>\n</tr>"

    for row in download_rows:
        if len(current) + 1 + len(row) > max_len:
            current += "\n</table>"
            messages.append(current)
            current = "<table>\n<tr>\n<td>#</td>\n<td>Name</td>\n<td>Size</td>\n<td>Progress</td>\n<td>ETA</td>\n<td>Status</td>\n</tr>\n" + row
        else:
            current += "\n" + row

    current += "\n</table>"

    if after_rows:
        after_head = "\n\n## After\n---\n\n<table>\n<tr>\n<td>ID</td>\n<td>URL</td>\n<td>Task</td>\n</tr>"
        after_foot = "\n</table>"
        after_rows_str = "\n".join(after_rows)
        after_block = after_head + "\n" + after_rows_str + after_foot

        if len(current) + len(after_block) <= max_len:
            current += after_block
        else:
            if current:
                messages.append(current)
            current = "## After\n---\n\n<table>\n<tr>\n<td>ID</td>\n<td>URL</td>\n<td>Task</td>\n</tr>"
            for row in after_rows:
                if len(current) + 1 + len(row) > max_len:
                    current += "\n</table>"
                    messages.append(current)
                    current = "<table>\n<tr>\n<td>ID</td>\n<td>URL</td>\n<td>Task</td>\n</tr>\n" + row
                else:
                    current += "\n" + row
            current += "\n</table>"

    if current:
        messages.append(current)

    return messages


FILTER_ALL = "a"
FILTER_EXCLUDE_COMPLETED = "e"


def get_status(filter_str: str | None = None) -> list[str]:
    all_downloads = aria2.get_downloads()

    if filter_str == FILTER_EXCLUDE_COMPLETED:
        downloads = [(i, d) for i, d in enumerate(all_downloads) if not is_completed(d)]
    else:
        downloads = list(enumerate(all_downloads))

    if not downloads and not src.bot.after.after_tasks:
        return ["🤷 There are no torrents currently"]

    download_rows = [_build_download_row(i, d) for i, d in downloads]
    after_rows = _build_after_rows()

    return _join_into_messages(download_rows, after_rows)
