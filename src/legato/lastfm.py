from __future__ import annotations
import hashlib
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple
import httpx

API_ROOT = "https://ws.audioscrobbler.com/2.0/"

# Set these before release (application credentials, NOT user credentials)
APP_API_KEY = "67026e05f0045edf2802f4934f786507"
APP_API_SECRET = "d1372ddd649e1c25526b10ab38ea30fa"

class LastfmError(RuntimeError):
    pass

def _md5(s: str) -> str:
    return hashlib.md5(s.encode("utf-8")).hexdigest()

def api_sig(params: Dict[str, str], secret: str) -> str:
    base = "".join(k + params[k] for k in sorted(params.keys())) + secret
    return _md5(base)

@dataclass
class LastfmClient:
    api_key: str
    api_secret: str
    session_key: Optional[str] = None
    username: Optional[str] = None
    timeout_s: float = 20.0

    def _request(self, http_method: str, params: Dict[str, str], signed: bool = False) -> Dict[str, Any]:
        p = dict(params)
        p["api_key"] = self.api_key
        p["format"] = "json"
        if signed:
            sig_params = {k: str(v) for k, v in p.items() if k != "format"}
            p["api_sig"] = api_sig(sig_params, self.api_secret)
        try:
            with httpx.Client(timeout=self.timeout_s) as client:
                if http_method.upper() == "POST":
                    r = client.post(API_ROOT, data=p)
                else:
                    r = client.get(API_ROOT, params=p)
            r.raise_for_status()
            data = r.json()
        except Exception as e:
            raise LastfmError(f"HTTP error: {e}") from e
        if isinstance(data, dict) and "error" in data:
            raise LastfmError(f"Last.fm error {data.get('error')}: {data.get('message')}")
        return data

    def get_token(self) -> str:
        data = self._request("GET", {"method": "auth.getToken"}, signed=False)
        tok = data.get("token")
        if not tok:
            raise LastfmError("No token returned.")
        return tok

    def try_get_session(self, token: str) -> Optional[Tuple[str, str]]:
        try:
            data = self._request("GET", {"method": "auth.getSession", "token": token}, signed=True)
            sess = data.get("session") or {}
            sk = sess.get("key")
            name = sess.get("name")
            if sk and name:
                self.session_key = sk
                self.username = name
                return sk, name
        except LastfmError:
            return None
        return None

    def user_info(self, user: Optional[str] = None) -> Dict[str, Any]:
        return self._request("GET", {"method": "user.getInfo", "user": user or self.username or ""}).get("user", {})

    def recent_tracks(self, user: Optional[str] = None, limit: int = 10, page: int = 1) -> Dict[str, Any]:
        data = self._request("GET", {"method": "user.getRecentTracks", "user": user or self.username or "",
                                     "limit": str(limit), "page": str(page), "extended": "1"})
        return data.get("recenttracks", {})

    def top_artists(self, user: str, period: str, limit: int = 10, page: int = 1) -> Dict[str, Any]:
        data = self._request("GET", {"method": "user.getTopArtists", "user": user, "period": period,
                                     "limit": str(limit), "page": str(page)})
        return data.get("topartists", {})

    def top_albums(self, user: str, period: str, limit: int = 10, page: int = 1) -> Dict[str, Any]:
        data = self._request("GET", {"method": "user.getTopAlbums", "user": user, "period": period,
                                     "limit": str(limit), "page": str(page)})
        return data.get("topalbums", {})

    def top_tracks(self, user: str, period: str, limit: int = 10, page: int = 1) -> Dict[str, Any]:
        data = self._request("GET", {"method": "user.getTopTracks", "user": user, "period": period,
                                     "limit": str(limit), "page": str(page)})
        return data.get("toptracks", {})

    def friends(self, user: str, limit: int = 50, page: int = 1, recenttracks: bool = False) -> Dict[str, Any]:
        data = self._request("GET", {"method": "user.getFriends", "user": user, "limit": str(limit),
                                     "page": str(page), "recenttracks": "1" if recenttracks else "0"})
        return data.get("friends", {})

    def artist_info(self, artist: str, username: Optional[str] = None) -> Dict[str, Any]:
        return self._request("GET", {"method": "artist.getInfo", "artist": artist, "username": username or self.username or "",
                                     "autocorrect": "1"}).get("artist", {})

    def album_info(self, artist: str, album: str, username: Optional[str] = None) -> Dict[str, Any]:
        return self._request("GET", {"method": "album.getInfo", "artist": artist, "album": album, "username": username or self.username or "",
                                     "autocorrect": "1"}).get("album", {})

    def track_info(self, artist: str, track: str, username: Optional[str] = None) -> Dict[str, Any]:
        return self._request("GET", {"method": "track.getInfo", "artist": artist, "track": track, "username": username or self.username or "",
                                     "autocorrect": "1"}).get("track", {})

    def update_now_playing(self, artist: str, track: str, album: Optional[str] = None) -> None:
        if not self.session_key:
            raise LastfmError("Not connected. Run `legato setup`.")
        p = {"method": "track.updateNowPlaying", "artist": artist, "track": track, "sk": self.session_key}
        if album:
            p["album"] = album
        self._request("POST", p, signed=True)

    def scrobble(self, artist: str, track: str, timestamp: int, album: Optional[str] = None) -> None:
        if not self.session_key:
            raise LastfmError("Not connected. Run `legato setup`.")
        p = {"method": "track.scrobble", "artist": artist, "track": track, "timestamp": str(timestamp), "sk": self.session_key}
        if album:
            p["album"] = album
        self._request("POST", p, signed=True)

    def love(self, artist: str, track: str) -> None:
        if not self.session_key:
            raise LastfmError("Not connected. Run `legato setup`.")
        self._request("POST", {"method": "track.love", "artist": artist, "track": track, "sk": self.session_key}, signed=True)

    def unlove(self, artist: str, track: str) -> None:
        if not self.session_key:
            raise LastfmError("Not connected. Run `legato setup`.")
        self._request("POST", {"method": "track.unlove", "artist": artist, "track": track, "sk": self.session_key}, signed=True)

def validate_app_creds() -> None:
    if (not APP_API_KEY) or (not APP_API_SECRET) or "REPLACE_ME" in APP_API_KEY or "REPLACE_ME" in APP_API_SECRET:
        raise LastfmError("Missing app credentials. Set APP_API_KEY and APP_API_SECRET in src/legato/lastfm.py")

def period_to_lastfm(p: str) -> str:
    p = p.strip().lower()
    mapping = {
        "day": "7day",     # Last.fm top endpoints do not expose a 1-day period; using 7day
        "week": "7day",
        "month": "1month",
        "quarter": "3month",
        "year": "12month",
        "overall": "overall",
    }
    if p not in mapping:
        raise ValueError("period must be day|week|month|quarter|year|overall")
    return mapping[p]
