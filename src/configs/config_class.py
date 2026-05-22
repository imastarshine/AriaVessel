import json
from pathlib import Path
from typing import Any
from src.logger import logger

DEFAULT_CONFIG_PATH = Path('config.json')
PRETTY_NAMES = {
    "uri_filename_rename": "Rename file",
    "uri_filename_translit": "Transliterate",
    "uri_filename_slugify": "Slugify",
    "uri_filename_max_length": "Max length"
}


def clamp(value: int, min_val: int, max_val: int):
    return max(min_val, min(max_val, value))


class Config:
    def __init__(self):
        self.uri_filename_rename: bool = False
        self.uri_filename_translit: bool = False
        self.uri_filename_slugify: bool = False

        self.uri_filename_max_length: int = -1

    def __setattr__(self, key: str, value: Any):
        if key == "uri_filename_max_length" and isinstance(value, int):
            value = clamp(value, -1, 224)

        super().__setattr__(key, value)

    @staticmethod
    def get_pretty_label(key: str) -> str | None:
        return PRETTY_NAMES.get(key)

    def to_dict(self) -> dict[str, Any]:
        d = {}
        for k, v in self.__dict__.items():
            if not k.startswith('__'):
                d[k] = v
        return d

    def load(self):
        if not DEFAULT_CONFIG_PATH.exists():
            DEFAULT_CONFIG_PATH.write_text(json.dumps(self.to_dict()), encoding='utf-8')
        else:
            config_json: dict = json.loads(DEFAULT_CONFIG_PATH.read_text(encoding="utf-8"))
            if not isinstance(config_json, dict):
                logger.error(f'Config file is invalid. Expected JSON dictionary object but got {type(config_json)}')
                raise ValueError("Config must be a dictionary")
            for key, value in config_json.items():
                setattr(self, key, value)

    def save(self):
        DEFAULT_CONFIG_PATH.write_text(json.dumps(self.to_dict()), encoding='utf-8')
