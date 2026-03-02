from __future__ import annotations

import datetime as dt
import os
import re
from typing import Iterable

def now_ts() -> int:
    return int(dt.datetime.now().timestamp())

def human_delta(ts: int, now: int | None = None) -> str:
    now_dt = dt.datetime.fromtimestamp(now or now_ts())
    ts_dt = dt.datetime.fromtimestamp(ts)
    delta = now_dt - ts_dt
    seconds = max(int(delta.total_seconds()), 0)
    if seconds < 60:
        return f"{seconds}s ago"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes}m ago"
    hours = minutes // 60
    if hours < 24:
        return f"{hours}h ago"
    days = hours // 24
    return f"{days}d ago"

def normalize_space(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()

def norm_key(s: str) -> str:
    # for matching: lowercase, strip punctuation-ish
    s = s.casefold()
    s = re.sub(r"[^a-z0-9\s]+", "", s)
    s = normalize_space(s)
    return s

def env_get(name: str) -> str | None:
    v = os.environ.get(name)
    return v.strip() if v and v.strip() else None

def clamp(n: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, n))

def chunks(lst: list, size: int) -> Iterable[list]:
    for i in range(0, len(lst), size):
        yield lst[i:i+size]
