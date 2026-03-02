from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from platformdirs import user_config_dir
from tomlkit import parse, dumps

APP_NAME = "legato"

def config_dir() -> Path:
    return Path(user_config_dir(APP_NAME))

def config_path() -> Path:
    return config_dir() / "config.toml"

@dataclass
class Config:
    data: dict

    def get(self, key: str, default: Any = None) -> Any:
        return self.data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self.data[key] = value

def load_config() -> Config:
    path = config_path()
    if not path.exists():
        return Config(data={})
    doc = parse(path.read_text(encoding="utf-8"))
    return Config(data=dict(doc))

def save_config(cfg: Config) -> None:
    d = config_dir()
    d.mkdir(parents=True, exist_ok=True)
    path = config_path()
    path.write_text(dumps(cfg.data), encoding="utf-8")
