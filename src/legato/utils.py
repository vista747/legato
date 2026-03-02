from __future__ import annotations
import datetime as dt
import re
from urllib.parse import quote

def now_ts() -> int:
    return int(dt.datetime.now(dt.timezone.utc).timestamp())

def human_delta(ts: int, now: int | None = None) -> str:
    now_ts_ = now if now is not None else now_ts()
    seconds = max(int(now_ts_ - ts), 0)
    if seconds < 60:
        return f"{seconds}s ago"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes}m ago"
    hours = minutes // 60
    if hours < 24:
        return f"{hours}h ago"
    return f"{hours//24}d ago"

def clamp(n: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, n))

def lastfm_user_url(user: str) -> str:
    return f"https://www.last.fm/user/{quote(user, safe='')}"

def lastfm_artist_url(artist: str) -> str:
    return f"https://www.last.fm/music/{quote(artist, safe='')}"

def lastfm_album_url(artist: str, album: str) -> str:
    return f"https://www.last.fm/music/{quote(artist, safe='')}/{quote(album, safe='')}"

def lastfm_track_url(artist: str, track: str) -> str:
    return f"https://www.last.fm/music/{quote(artist, safe='')}/_/{quote(track, safe='')}"

def youtube_search_url(artist: str, track: str) -> str:
    q = quote(f"{artist} - {track}")
    return f"https://www.youtube.com/results?search_query={q}"
