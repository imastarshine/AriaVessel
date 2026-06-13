# int it's a user id, list contains gids for aria2c
pending_processes: dict[int, list[str]] = {}
# key: gid being waited on, value: list of http links to download after this gid completes
after_queue: dict[str, list[str]] = {}
# key: parent gid, value: list of child gids to resume when parent completes (for file-based chaining)
resume_queue: dict[str, list[str]] = {}