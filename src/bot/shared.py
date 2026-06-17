# int it's a user id, list contains gids for aria2c
pending_processes: dict[int, list[str]] = {}

# after_queue: key = parent identifier (gid, "__none__", or "__task_N__")
# value = list of {"link": str, "task_id": str, "retries": int}
after_queue: dict[str, list[dict]] = {}

# batch tasks: wait for ALL parents to finish before starting
# [{"link": str, "task_id": str, "parents": list[str], "retries": int}, ...]
after_batch: list[dict] = []

# maps a task_id ("__task_N__") to the real aria2 gid once the download is added
after_gid_map: dict[str, str] = {}

AFTER_NONE = "__none__"
after_counter = 0
after_last_task_id: str | None = None
