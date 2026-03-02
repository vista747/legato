from __future__ import annotations
import datetime as dt, os, re
from urllib.parse import quote

def now_ts() -> int:
    return int(dt.datetime.now().timestamp())

def human_delta(ts: int, now: int | None = None) -> str:
    now_dt = dt.datetime.fromtimestamp(now or now_ts())
    ts_dt = dt.datetime.fromtimestamp(ts)
    seconds = max(int((now_dt - ts_dt).total_seconds()), 0)
    if seconds < 60: return f"{seconds}s ago"
    minutes = seconds // 60
    if minutes < 60: return f"{minutes}m ago"
    hours = minutes // 60
    if hours < 24: return f"{hours}h ago"
    return f"{hours//24}d ago"

def norm_key(s: str) -> str:
    s = s.casefold()
    s = re.sub(r"[^a-z0-9\s]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()

def env_get(name: str) -> str | None:
    v = os.environ.get(name)
    return v.strip() if v and v.strip() else None

def clamp(n: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, n))

def lastfm_artist_url(artist: str) -> str:
    return f"https://www.last.fm/music/{quote(artist, safe='')}"

def lastfm_album_url(artist: str, album: str) -> str:
    return f"https://www.last.fm/music/{quote(artist, safe='')}/{quote(album, safe='')}"

def lastfm_track_url(artist: str, track: str) -> str:
    return f"https://www.last.fm/music/{quote(artist, safe='')}/_/{quote(track, safe='')}"
