from transliterate import translit, detect_language
from aria2p import Download

from src.logger import logger

FILL = "█"
EMPTY = "░"


class MessageBuilder:
    def __init__(self, max_length: int = 3450, separator: str = "\n"):
        self.max_length = max_length
        self.separator = separator
        self.pages = []
        self._current_page = []
        self._current_length = 0

    def add_chunk(self, chunk: str):
        if not chunk:
            return

        chunk_len = len(chunk)
        separator_len = len(self.separator) if self._current_page else 0

        if self._current_length + separator_len + chunk_len > self.max_length:
            if chunk_len > self.max_length:
                self._flush_current_page()
                self._split_and_add_huge_chunk(chunk)
            else:
                self._flush_current_page()
                self._current_page.append(chunk)
                self._current_length = chunk_len
        else:
            self._current_page.append(chunk)
            self._current_length += separator_len + chunk_len

    def _flush_current_page(self):
        if self._current_page:
            self.pages.append(self.separator.join(self._current_page))
            self._current_page = []
            self._current_length = 0

    def _split_and_add_huge_chunk(self, huge_chunk: str):
        for i in range(0, len(huge_chunk), self.max_length):
            self.pages.append(huge_chunk[i:i + self.max_length])

    def get_messages(self) -> list[str]:
        self._flush_current_page()
        result = self.pages.copy()
        self.pages.clear()
        return result


def boolean_to_telegram_style(value: bool) -> str:
    return "success" if value else "danger"


def boolean_to_human_readable_string(boolean_value: bool) -> str:
    return "On" if boolean_value is True else "Off"


def generate_progress_bar(percent: float, width=20):
    filled_length = int(width * percent)

    bar = FILL * filled_length + EMPTY * (width - filled_length)
    return f"{bar} {percent * 100:.1f}%"


def format_speed(speed_bps: int):
    if speed_bps <= 0: return "0 KB/s"
    speed = speed_bps / 1024 # в КБ/с
    if speed < 1024:
        return f"{speed:.1f} KB/s"
    return f"{speed/1024:.1f} MB/s"


def parse_range(text: str):
    # Example command: /pause 0,2 -> than script does to make [0, 1, 2]. Also parse errors
    # Text must be: "0,2" -> [0, 1, 2]
    parts = [int(x.strip()) for x in text.split(',') if x.strip()]

    if len(parts) < 2:
        raise ValueError("Invalid range. Value range must include two numbers.")

    if len(parts) > 2:
        raise ValueError("Invalid range. Value range must include two numbers.")

    start_number, end_number = parts[0], parts[1]
    return list(range(start_number, end_number + 1))


def parse_list(text: str):
    # Example command: /pause [0,15,24] -> than script does to make [0, 15, 24]. Or other argument parsing
    # /pause [1, 15,25] -> [1, 15, 25]
    clean_text = text.strip("[] ")
    if not clean_text:
        raise ValueError("Provided list is empty.")

    return [int(x.strip()) for x in clean_text.split(',')]


def multi_index_list(source: list, indexes: list[int]) -> (list, list):
    result = []
    failed = []
    for index in indexes:
        try:
            result.append(source[index])
        except IndexError:
            failed.append(index)
            logger.error(f"Index {index} out of range.")
    return result, failed


def auto_translit(text: str) -> str:
    lang_code = detect_language(text)

    if lang_code:
        return translit(text, lang_code, reversed=True)
    return text


def parse_idx(idx: str, aria_downloads: list[Download]) -> tuple[list[Download], list[int | str]]:
    if idx.startswith("[") and idx.endswith("]"):
        idx = parse_list(idx)
    elif idx.find(",") > 0 and not idx.startswith("[") and not idx.endswith("]"):
        idx = parse_range(idx)
    elif idx.isdigit():
        idx = int(idx)
    else:
        raise ValueError(f"Can't parse idx: {idx} correctly")

    failed_list = []
    if isinstance(idx, list):
        downloads, failed_list = multi_index_list(aria_downloads, idx)
    else:
        downloads = [aria_downloads[idx]]

    return downloads, failed_list


def format_size(size):
    if size <= 0: return "0.00 B"
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size < 1024: return f"{size:.2f} {unit}"
        size /= 1024
