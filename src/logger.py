import logging
import os
import sys
from datetime import datetime, timedelta


def cleanup_old_logs(days=7):
    cutoff = datetime.now() - timedelta(days=days)
    for f in os.listdir("logs"):
        path = os.path.join("logs", f)
        if os.path.isfile(path):
            ctime = datetime.fromtimestamp(os.path.getctime(path))
            if ctime < cutoff:
                os.remove(path)


os.makedirs("logs", exist_ok=True)

logger_handler = logging.FileHandler(f"logs/{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.log", "a", encoding="utf-8")
logger_handler.setLevel(logging.INFO)
logger_handler.setFormatter(
    logging.Formatter("%(asctime)s [%(levelname)s] (%(filename)s:%(lineno)d - %(funcName)s) | %(message)s"))

console_handler = logging.StreamHandler(sys.stdout)
console_handler.setLevel(logging.DEBUG)
console_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] | %(message)s"))

logger = logging.getLogger("TelemetryLogu")
logger.propagate = False
logger.handlers.clear()
logger.setLevel(logging.INFO)
logger.addHandler(logger_handler)
logger.addHandler(console_handler)
