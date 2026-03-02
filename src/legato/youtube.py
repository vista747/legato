from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Tuple

import httpx

class YouTubeError(RuntimeError):
    pass

SEARCH_URL = "https://www.googleapis.com/youtube/v3/search"

def _norm(s: str) -> str:
    s = s.casefold()
    s = re.sub(r"[^a-z0-9\s]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s

def score_title(title: str, artist: str, track: str) -> int:
    t = _norm(title)
    a = _norm(artist)
    tr = _norm(track)
    score = 0
    if a in t: score += 50
    if tr in t: score += 50
    if f"{a} {tr}" in t or f"{tr} {a}" in t: score += 30
    # penalties
    penalties = ["live", "cover", "sped up", "slowed", "remix", "karaoke", "nightcore", "8d"]
    for p in penalties:
        if p in t and p not in tr:
            score -= 10
    # bonuses
    bonuses = ["official", "audio", "provided to youtube", "topic"]
    for b in bonuses:
        if b in t:
            score += 5
    return score

@dataclass
class YouTubeClient:
    api_key: str
    timeout_s: float = 15.0

    def search_best(self, artist: str, track: str, max_results: int = 5) -> Dict[str, Any]:
        q = f"{artist} - {track}"
        params = {
            "part": "snippet",
            "type": "video",
            "maxResults": str(max_results),
            "q": q,
            "key": self.api_key,
        }
        try:
            with httpx.Client(timeout=self.timeout_s) as client:
                r = client.get(SEARCH_URL, params=params)
            r.raise_for_status()
            data = r.json()
        except Exception as e:
            raise YouTubeError(f"YouTube search failed: {e}") from e

        items = data.get("items") or []
        if not items:
            raise YouTubeError("No YouTube results.")
        # score
        best = None
        best_score = -10**9
        for it in items:
            sn = it.get("snippet") or {}
            title = sn.get("title") or ""
            sc = score_title(title, artist, track)
            if sc > best_score:
                best_score = sc
                best = it
        if not best:
            best = items[0]
        vid = (best.get("id") or {}).get("videoId")
        sn = best.get("snippet") or {}
        if not vid:
            raise YouTubeError("No videoId in best result.")
        return {
            "videoId": vid,
            "title": sn.get("title"),
            "channelTitle": sn.get("channelTitle"),
            "url": f"https://www.youtube.com/watch?v={vid}",
            "score": best_score,
            "query": q,
        }
