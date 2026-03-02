from __future__ import annotations

import json as _json
import os
import subprocess
import time
import typer
from rich.console import Console
from rich.table import Table

from .config import load_config, save_config, config_path
from .utils import env_get, human_delta, now_ts, norm_key, clamp
from .lastfm import LastfmClient, LastfmError, period_to_lastfm
from .youtube import YouTubeClient, YouTubeError
from .help import MIN_HELP

console = Console()
app = typer.Typer(no_args_is_help=True, add_completion=False)


def _get_lastfm() -> LastfmClient:
    cfg = load_config()
    api_key = cfg.get("lastfm_api_key") or env_get("LEGATO_LASTFM_KEY")
    api_secret = env_get("LEGATO_LASTFM_SECRET") or cfg.get("lastfm_api_secret")
    session_key = cfg.get("lastfm_session_key")
    username = cfg.get("username") or cfg.get("lastfm_username")

    if not api_key:
        raise LastfmError("Missing lastfm_api_key. Set with `legato config set lastfm_api_key ...`")
    if not api_secret:
        raise LastfmError("Missing Last.fm shared secret. Set env LEGATO_LASTFM_SECRET (recommended).")

    return LastfmClient(
        api_key=str(api_key),
        api_secret=str(api_secret),
        session_key=session_key,
        username=username,
    )


def _period_days(period: str) -> int:
    p = period.strip().lower()
    if p in {"day", "d"}:
        return 1
    if p in {"week", "w"}:
        return 7
    if p in {"month", "m"}:
        return 30
    if p in {"quarter", "q"}:
        return 90
    if p in {"year", "y"}:
        return 365
    raise typer.BadParameter("period must be day|week|month|quarter|year")


def _parse_period(period: str) -> str:
    p = period.strip().lower()
    mapping = {
        "d": "day",
        "day": "day",
        "w": "week",
        "week": "week",
        "m": "month",
        "month": "month",
        "q": "quarter",
        "quarter": "quarter",
        "y": "year",
        "year": "year",
    }
    if p not in mapping:
        raise typer.BadParameter("period must be day|week|month|quarter|year")
    return mapping[p]


@app.command()
def help():
    """Minimal help (no borders)."""
    console.print(MIN_HELP)


@app.command()
def setup(timeout: int = typer.Option(120, "--timeout", help="Seconds to wait for approval.")):
    """Authenticate with Last.fm and store session key."""
    lfm = _get_lastfm()
    cfg = load_config()

    console.print("Requesting token…")
    token = lfm.get_token()
    url = f"https://www.last.fm/api/auth/?api_key={lfm.api_key}&token={token}"

    # Linux-native open
    try:
        subprocess.Popen(["xdg-open", url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass

    console.print("Authorize Legato in your browser:")
    console.print(url)
    console.print("Waiting for approval… (Ctrl+C to cancel)")

    start = time.time()
    while True:
        if time.time() - start > timeout:
            raise typer.Exit(code=1)

        sess = lfm.try_get_session(token)
        if sess is not None:
            sk, username = sess
            cfg.set("lastfm_session_key", sk)
            cfg.set("username", username)
            save_config(cfg)
            console.print(f"[bold]OK[/bold] authenticated as {username}")
            return

        time.sleep(2)


@app.command()
def current(json: bool = typer.Option(False, "--json", help="Machine-readable output")):
    """Show now playing if available; otherwise last scrobble."""
    lfm = _get_lastfm()
    rt = lfm.recent_tracks(limit=1)
    tracks = rt.get("track") or []
    if isinstance(tracks, dict):
        tracks = [tracks]
    if not tracks:
        raise typer.Exit(1)

    t0 = tracks[0]
    artist = (t0.get("artist") or {}).get("name") or (t0.get("artist") or {}).get("#text") or ""
    track = t0.get("name") or ""
    album = (t0.get("album") or {}).get("#text") or ""
    attrs = t0.get("@attr") or {}
    now_playing = str(attrs.get("nowplaying", "")).lower() == "true"

    ts = None
    if not now_playing:
        date = t0.get("date") or {}
        uts = date.get("uts")
        if uts:
            ts = int(uts)

    payload = {
        "now_playing": now_playing,
        "artist": artist,
        "track": track,
        "album": album,
        "timestamp": ts,
    }

    if json:
        console.print(_json.dumps(payload))
        return

    table = Table(title="current", show_lines=False)
    table.add_column("Field")
    table.add_column("Value")
    table.add_row("Artist", artist)
    table.add_row("Track", track)
    if album:
        table.add_row("Album", album)
    if now_playing:
        table.add_row("Status", "Now playing")
    else:
        if ts is not None:
            table.add_row("Played", f"{human_delta(ts)}")  # only show x ago if not playing
    console.print(table)


# (rest of the beta commands can remain as in your beta if you want;
# the key fix is: working imports + _get_lastfm + setup polling)


# ---- config group ----
config_app = typer.Typer(no_args_is_help=True)
app.add_typer(config_app, name="config")


@config_app.command("path")
def config_path_cmd():
    console.print(str(config_path()))


@config_app.command("get")
def config_get(key: str):
    cfg = load_config()
    val = cfg.get(key)
    if val is None:
        raise typer.Exit(1)
    console.print(str(val))


@config_app.command("set")
def config_set(key: str, value: str):
    cfg = load_config()
    cfg.set(key, value)
    save_config(cfg)
    console.print(f"set {key}")


def main():
    try:
        app()
    except (LastfmError, YouTubeError) as e:
        console.print(f"[red]error[/red] {e}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()