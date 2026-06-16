# int it's a user id, list contains gids for aria2c
pending_processes: dict[int, list[str]] = {}

# after_queue: key = parent identifier (gid, "__none__", or "__task_N__")
# value = list of {"link": str, "task_id": str, "retries": int}
after_queue: dict[str, list[dict]] = {}
# maps a task_id ("__task_N__") to the real aria2 gid once the download is added
after_gid_map: dict[str, str] = {}

AFTER_NONE = "__none__"
after_counter = 0
