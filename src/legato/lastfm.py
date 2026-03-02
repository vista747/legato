from __future__ import annotations

import hashlib
import time
import webbrowser
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple, List

import httpx

API_ROOT = "https://ws.audioscrobbler.com/2.0/"

class LastfmError(RuntimeError):
    pass

def _md5(s: str) -> str:
    return hashlib.md5(s.encode("utf-8")).hexdigest()

def api_sig(params: Dict[str, str], secret: str) -> str:
    # Sort by key (ASCII ordering). Then concat key+value.
    parts = []
    for k in sorted(params.keys()):
        parts.append(k + params[k])
    base = "".join(parts) + secret
    return _md5(base)

@dataclass
class LastfmClient:
    api_key: str
    api_secret: str
    session_key: str | None = None
    username: str | None = None
    timeout_s: float = 20.0

    def _request(self, method: str, params: Dict[str, str], signed: bool = False) -> Dict[str, Any]:
        p = dict(params)
        p["api_key"] = self.api_key
        p["format"] = "json"
        if signed:
            if not self.api_secret:
                raise LastfmError("Missing Last.fm shared secret.")
            sig_params = {k: v for k, v in p.items() if k != "format"}
            p["api_sig"] = api_sig({k: str(v) for k, v in sig_params.items()}, self.api_secret)
        try:
            with httpx.Client(timeout=self.timeout_s) as client:
                if method.upper() == "GET":
                    r = client.get(API_ROOT, params=p)
                else:
                    r = client.post(API_ROOT, data=p)
            r.raise_for_status()
            data = r.json()
        except Exception as e:
            raise LastfmError(f"HTTP error: {e}") from e

        # API-level errors
        if isinstance(data, dict) and "error" in data:
            raise LastfmError(f"Last.fm error {data.get('error')}: {data.get('message')}")
        return data

    # ---- Auth ----
    def get_token(self) -> str:
        data = self._request("GET", {"method": "auth.getToken"}, signed=True)
        tok = data.get("token")
        if not tok:
            raise LastfmError("No token returned.")
        return tok

    def open_authorize(self, token: str) -> str:
        # Desktop auth: user visits this URL and authorizes the token.
        url = f"https://www.last.fm/api/auth/?api_key={self.api_key}&token={token}"
        webbrowser.open(url)
        return url

    def get_session(self, token: str) -> Tuple[str, str]:
        data = self._request("GET", {"method": "auth.getSession", "token": token}, signed=True)
        sess = data.get("session") or {}
        sk = sess.get("key")
        name = sess.get("name")
        if not sk or not name:
            raise LastfmError("No session returned; did you authorize in the browser?")
        self.session_key = sk
        self.username = name
        return sk, name

    # ---- User ----
    def user_info(self, user: str | None = None) -> Dict[str, Any]:
        data = self._request("GET", {"method": "user.getInfo", "user": user or self.username or ""}, signed=False)
        return data["user"]

    def recent_tracks(self, user: str | None = None, limit: int = 1, page: int = 1) -> Dict[str, Any]:
        data = self._request(
            "GET",
            {
                "method": "user.getRecentTracks",
                "user": user or self.username or "",
                "limit": str(limit),
                "page": str(page),
                "extended": "1",
            },
            signed=False,
        )
        return data.get("recenttracks", {})

    def top_artists(self, period: str, user: str | None = None, limit: int = 10, page: int = 1) -> Dict[str, Any]:
        data = self._request("GET", {
            "method":"user.getTopArtists",
            "user": user or self.username or "",
            "period": period,
            "limit": str(limit),
            "page": str(page),
        }, signed=False)
        return data.get("topartists", {})

    def top_albums(self, period: str, user: str | None = None, limit: int = 10, page: int = 1) -> Dict[str, Any]:
        data = self._request("GET", {
            "method":"user.getTopAlbums",
            "user": user or self.username or "",
            "period": period,
            "limit": str(limit),
            "page": str(page),
        }, signed=False)
        return data.get("topalbums", {})

    def top_tracks(self, period: str, user: str | None = None, limit: int = 10, page: int = 1) -> Dict[str, Any]:
        data = self._request("GET", {
            "method":"user.getTopTracks",
            "user": user or self.username or "",
            "period": period,
            "limit": str(limit),
            "page": str(page),
        }, signed=False)
        return data.get("toptracks", {})

    # ---- Track/Artist/Album info (includes userplaycount if username provided) ----
    def artist_info(self, artist: str, username: str | None = None) -> Dict[str, Any]:
        data = self._request("GET", {
            "method": "artist.getInfo",
            "artist": artist,
            "username": username or self.username or "",
            "autocorrect": "1",
        }, signed=False)
        return data.get("artist", {})

    def album_info(self, artist: str, album: str, username: str | None = None) -> Dict[str, Any]:
        data = self._request("GET", {
            "method": "album.getInfo",
            "artist": artist,
            "album": album,
            "username": username or self.username or "",
            "autocorrect": "1",
        }, signed=False)
        return data.get("album", {})

    def track_info(self, artist: str, track: str, username: str | None = None) -> Dict[str, Any]:
        data = self._request("GET", {
            "method": "track.getInfo",
            "artist": artist,
            "track": track,
            "username": username or self.username or "",
            "autocorrect": "1",
        }, signed=False)
        return data.get("track", {})

    # ---- Write calls ----
    def update_now_playing(self, artist: str, track: str, album: str | None = None, duration: int | None = None) -> Dict[str, Any]:
        if not self.session_key:
            raise LastfmError("Not authenticated. Run `legato setup`.")
        params = {
            "method": "track.updateNowPlaying",
            "artist": artist,
            "track": track,
            "sk": self.session_key,
        }
        if album: params["album"] = album
        if duration: params["duration"] = str(duration)
        return self._request("POST", params, signed=True)

    def scrobble(self, artist: str, track: str, timestamp: int, album: str | None = None, duration: int | None = None) -> Dict[str, Any]:
        if not self.session_key:
            raise LastfmError("Not authenticated. Run `legato setup`.")
        params = {
            "method": "track.scrobble",
            "artist": artist,
            "track": track,
            "timestamp": str(timestamp),
            "sk": self.session_key,
        }
        if album: params["album"] = album
        if duration: params["duration"] = str(duration)
        return self._request("POST", params, signed=True)

# ---- Helpers ----
def period_to_lastfm(period: str) -> str | None:
    # Return None for "day" (handled via aggregation).
    p = period.strip().lower()
    if p in {"week","w"}: return "7day"
    if p in {"month","m"}: return "1month"
    if p in {"quarter","q"}: return "3month"
    if p in {"year","y"}: return "12month"
    if p in {"overall","all"}: return "overall"
    if p in {"day","d"}: return None
    raise ValueError("period must be day|week|month|quarter|year")

def require_nonempty(label: str, v: str | None) -> str:
    if not v or not v.strip():
        raise LastfmError(f"Missing {label}. Set it with `legato config set {label} ...` or env var.")
    return v.strip()
