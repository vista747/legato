from __future__ import annotations
from dataclasses import dataclass

OSC8_START = "\x1b]8;;{url}\x1b\\"
OSC8_END = "\x1b]8;;\x1b\\"

def hyperlink(text: str, url: str) -> str:
    return f"{OSC8_START.format(url=url)}{text}{OSC8_END}"

def sgr(code: str) -> str:
    return f"\x1b[{code}m"

def reset() -> str:
    return "\x1b[0m"

@dataclass
class Theme:
    # accent is an SGR fragment like "1;91" (bold bright red)
    accent: str = "1;91"

    def accentize(self, s: str) -> str:
        return f"{sgr(self.accent)}{s}{reset()}"
