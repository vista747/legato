from __future__ import annotations
import re
from .config import load_config, save_config
from .ansi import Theme

NAMED = {
  "red": "1;91",
  "bright_red": "1;91",
  "orange": "1;93",
  "yellow": "1;93",
  "green": "1;92",
  "blue": "1;94",
  "magenta": "1;95",
  "cyan": "1;96",
  "white": "1;97",
}

def get_theme() -> Theme:
    cfg = load_config()
    accent = cfg.get("accent_sgr", "1;91")
    return Theme(accent=str(accent))

def set_accent(value: str) -> Theme:
    v = value.strip().lower()
    cfg = load_config()

    if v in NAMED:
        cfg.set("accent_sgr", NAMED[v])
        save_config(cfg)
        return Theme(NAMED[v])

    if re.fullmatch(r"[0-9;]{1,16}", v):
        cfg.set("accent_sgr", v)
        save_config(cfg)
        return Theme(v)

    raise ValueError("color must be one of: red, orange, yellow, green, blue, magenta, cyan, white, or an SGR code like '1;91'")
