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

# We keep Typer, but provide a minimal `help` command and short command help text.
# (Typer's built-in --help will still be rich-formatted; use `legato help` for minimal help.)
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
    return LastfmClient(api_key=str(api_key), api_secret=str(api_secret), session_key=session_key, username=username)

def _period_days(period: str) -> int:
    p = period.strip().lower()
    if p in {"day","d"}: return 1
    if p in {"week","w"}: return 7
    if p in {"month","m"}: return 30
    if p in {"quarter","q"}: return 90
    if p in {"year","y"}: return 365
    raise typer.BadParameter("period must be day|week|month|quarter|year")

def _parse_period(period: str) -> str:
    p = period.strip().lower()
    mapping = {"d":"day","day":"day","w":"week","week":"week","m":"month","month":"month","q":"quarter","quarter":"quarter","y":"year","year":"year"}
    if p not in mapping:
        raise typer.BadParameter("period must be day|week|month|quarter|year")
    return mapping[p]

def _copy_to_clipboard(text: str) -> bool:
    # best-effort: wl-copy (Wayland) then xclip
    for cmd in (["wl-copy"], ["xclip", "-selection", "clipboard"]):
        try:
            p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            p.communicate(input=text.encode("utf-8"), timeout=2)
            return p.returncode == 0
        except Exception:
            continue
    return False

@app.command()
def help():
    """Minimal help (no borders)."""
    console.print(MIN_HELP)

@app.command()
def setup():
    """Authenticate with Last.fm and store session key."""
    lfm = _get_lastfm()
    cfg = load_config()

    console.print("Requesting token…")
    token = lfm.get_token()
    url = lfm.open_authorize(token)
    console.print("Opened browser for authorization:")
    console.print(url)
    console.print("After approving access, press Enter here.")
    input()

    console.print("Fetching session…")
    sk, username = lfm.get_session(token)
    cfg.set("lastfm_session_key", sk)
    cfg.set("username", username)
    save_config(cfg)
    console.print(f"[bold]OK[/bold] authenticated as {username}")

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
            table.add_row("Played", f"{human_delta(ts)}")
    console.print(table)

@app.command()
def np(
    artist: str = typer.Argument(...),
    track: str = typer.Argument(...),
    album: str | None = typer.Option(None, "--album"),
    duration: int | None = typer.Option(None, "--duration"),
):
    """Update now playing."""
    lfm = _get_lastfm()
    lfm.update_now_playing(artist=artist, track=track, album=album, duration=duration)
    console.print("[bold]OK[/bold] now playing updated")

@app.command()
def scrobble(
    artist: str = typer.Argument(...),
    track: str = typer.Argument(...),
    album: str | None = typer.Option(None, "--album"),
    ts: str | None = typer.Option(None, "--ts", help="Timestamp: 'now' or unix seconds."),
    duration: int | None = typer.Option(None, "--duration"),
):
    """Submit a scrobble."""
    lfm = _get_lastfm()
    if ts is None or ts.strip().lower() == "now":
        timestamp = now_ts()
    else:
        timestamp = int(ts)
    lfm.scrobble(artist=artist, track=track, timestamp=timestamp, album=album, duration=duration)
    console.print("[bold]OK[/bold] scrobbled")

@app.command()
def yt(
    artist: str | None = typer.Argument(None),
    track: str | None = typer.Argument(None),
    open: bool = typer.Option(False, "--open", help="Open result in browser."),
    copy: bool = typer.Option(False, "--copy", help="Copy URL to clipboard."),
    json: bool = typer.Option(False, "--json", help="Machine-readable output"),
):
    """Find best YouTube match / first result."""
    cfg = load_config()
    yt_key = cfg.get("youtube_api_key") or env_get("LEGATO_YT_KEY")
    if not yt_key:
        raise typer.BadParameter("Missing youtube_api_key. Set with `legato config set youtube_api_key ...`")

    if artist is None or track is None:
        # default to current track
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

    client = YouTubeClient(api_key=str(yt_key))
    result = client.search_best(artist=artist, track=track)

    if json:
        console.print(_json.dumps(result))
    else:
        table = Table(title="youtube")
        table.add_column("Field")
        table.add_column("Value")
        table.add_row("Title", str(result.get("title")))
        table.add_row("Channel", str(result.get("channelTitle")))
        table.add_row("URL", str(result.get("url")))
        console.print(table)

    url = str(result.get("url"))
    if copy:
        if _copy_to_clipboard(url):
            console.print("[bold]OK[/bold] copied to clipboard")
        else:
            console.print("[yellow]warn[/yellow] couldn't copy; missing wl-copy/xclip?")
    if open:
        try:
            subprocess.Popen(["xdg-open", url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass

# ---- top group ----
top_app = typer.Typer(no_args_is_help=True)
app.add_typer(top_app, name="top")

def _top_day_aggregate(kind: str, limit: int) -> list[tuple[str,str,int]]:
    # kind: artist|album|track
    lfm = _get_lastfm()
    cutoff = now_ts() - 24*3600
    counts = {}
    page = 1
    seen_old = False
    while page <= 10 and not seen_old:
        rt = lfm.recent_tracks(limit=200, page=page)
        tracks = rt.get("track") or []
        if isinstance(tracks, dict):
            tracks = [tracks]
        for t in tracks:
            attrs = t.get("@attr") or {}
            if str(attrs.get("nowplaying","")).lower() == "true":
                continue
            date = t.get("date") or {}
            uts = date.get("uts")
            if not uts:
                continue
            uts_i = int(uts)
            if uts_i < cutoff:
                seen_old = True
                break
            artist = (t.get("artist") or {}).get("name") or (t.get("artist") or {}).get("#text") or ""
            track = t.get("name") or ""
            album = (t.get("album") or {}).get("#text") or ""
            if kind == "artist":
                key = norm_key(artist)
                disp = artist
            elif kind == "album":
                key = norm_key(f"{artist}::{album}")
                disp = f"{album} — {artist}" if album else f"(no album) — {artist}"
            else:
                key = norm_key(f"{artist}::{track}")
                disp = f"{track} — {artist}"
            prev = counts.get(key)
            if prev:
                counts[key] = (disp, prev[1] + 1)
            else:
                counts[key] = (disp, 1)
        page += 1
    ranked = sorted(counts.values(), key=lambda x: x[1], reverse=True)
    return [(str(i+1), d, c) for i,(d,c) in enumerate(ranked[:limit])]

def _render_top(title: str, rows: list[tuple[str,str,int]]):
    table = Table(title=title)
    table.add_column("#", justify="right")
    table.add_column("Name")
    table.add_column("Plays", justify="right")
    for rank, name, plays in rows:
        table.add_row(rank, name, str(plays))
    console.print(table)

@top_app.command("artist")
def top_artist(
    period: str = typer.Option("week", "-p", "--period", help="day|week|month|quarter|year"),
    limit: int = typer.Option(10, "-n", "--limit"),
):
    p = _parse_period(period)
    limit = clamp(limit, 1, 100)
    if p == "day":
        rows = _top_day_aggregate("artist", limit)
        _render_top("top artist (day)", rows)
        return
    lfm = _get_lastfm()
    lf_period = period_to_lastfm(p)
    data = lfm.top_artists(period=lf_period, limit=limit)
    artists = data.get("artist") or []
    if isinstance(artists, dict):
        artists = [artists]
    rows = []
    for i,a in enumerate(artists[:limit]):
        name = a.get("name") or ""
        plays = int(a.get("playcount") or 0)
        rows.append((str(i+1), name, plays))
    _render_top(f"top artist ({p})", rows)

@top_app.command("album")
def top_album(
    period: str = typer.Option("week", "-p", "--period", help="day|week|month|quarter|year"),
    limit: int = typer.Option(10, "-n", "--limit"),
):
    p = _parse_period(period)
    limit = clamp(limit, 1, 100)
    if p == "day":
        rows = _top_day_aggregate("album", limit)
        _render_top("top album (day)", rows)
        return
    lfm = _get_lastfm()
    lf_period = period_to_lastfm(p)
    data = lfm.top_albums(period=lf_period, limit=limit)
    albums = data.get("album") or []
    if isinstance(albums, dict):
        albums = [albums]
    rows=[]
    for i,a in enumerate(albums[:limit]):
        name = a.get("name") or ""
        artist = (a.get("artist") or {}).get("name") or ""
        plays = int(a.get("playcount") or 0)
        disp = f"{name} — {artist}" if artist else name
        rows.append((str(i+1), disp, plays))
    _render_top(f"top album ({p})", rows)

@top_app.command("track")
def top_track(
    period: str = typer.Option("week", "-p", "--period", help="day|week|month|quarter|year"),
    limit: int = typer.Option(10, "-n", "--limit"),
):
    p = _parse_period(period)
    limit = clamp(limit, 1, 100)
    if p == "day":
        rows = _top_day_aggregate("track", limit)
        _render_top("top track (day)", rows)
        return
    lfm = _get_lastfm()
    lf_period = period_to_lastfm(p)
    data = lfm.top_tracks(period=lf_period, limit=limit)
    tracks = data.get("track") or []
    if isinstance(tracks, dict):
        tracks = [tracks]
    rows=[]
    for i,t in enumerate(tracks[:limit]):
        name = t.get("name") or ""
        artist = (t.get("artist") or {}).get("name") or ""
        plays = int(t.get("playcount") or 0)
        disp = f"{name} — {artist}" if artist else name
        rows.append((str(i+1), disp, plays))
    _render_top(f"top track ({p})", rows)

# ---- entity info ----
def _get_current_entities() -> dict:
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
    return {"artist": artist, "track": track, "album": album}

def _week_playcount_from_top(kind: str, name_key: str, artist_key: str | None = None) -> int | None:
    # look up in top lists (7day) and match. returns playcount or None if not present in first page(s)
    lfm = _get_lastfm()
    period = "7day"
    pages = 3
    limit = 200
    for page in range(1, pages+1):
        if kind == "artist":
            data = lfm.top_artists(period=period, limit=limit, page=page)
            items = data.get("artist") or []
            if isinstance(items, dict): items=[items]
            for it in items:
                if norm_key(it.get("name","")) == name_key:
                    return int(it.get("playcount") or 0)
        elif kind == "album":
            data = lfm.top_albums(period=period, limit=limit, page=page)
            items = data.get("album") or []
            if isinstance(items, dict): items=[items]
            for it in items:
                a = (it.get("artist") or {}).get("name") or ""
                if norm_key(it.get("name","")) == name_key and (artist_key is None or norm_key(a) == artist_key):
                    return int(it.get("playcount") or 0)
        else:
            data = lfm.top_tracks(period=period, limit=limit, page=page)
            items = data.get("track") or []
            if isinstance(items, dict): items=[items]
            for it in items:
                a = (it.get("artist") or {}).get("name") or ""
                if norm_key(it.get("name","")) == name_key and (artist_key is None or norm_key(a) == artist_key):
                    return int(it.get("playcount") or 0)
    return None

@app.command()
def artist(
    name: str | None = typer.Option(None, "--name", help="Override artist name."),
    period: str = typer.Option("week", "-p", "--period", help="day|week|month|quarter|year (for recent count; default week)"),
    json: bool = typer.Option(False, "--json"),
):
    p = _parse_period(period)
    lfm = _get_lastfm()
    ent = _get_current_entities()
    artist_name = name or ent["artist"]
    info = lfm.artist_info(artist_name)
    overall = int(((info.get("stats") or {}).get("userplaycount")) or 0)
    week = _week_playcount_from_top("artist", norm_key(artist_name))
    payload = {"artist": artist_name, "week_plays": week, "overall_plays": overall, "url": info.get("url")}
    if json:
        console.print(_json.dumps(payload)); return
    table = Table(title="artist")
    table.add_column("Field"); table.add_column("Value")
    table.add_row("Artist", artist_name)
    if week is not None: table.add_row("Plays (week)", str(week))
    table.add_row("Plays (overall)", str(overall))
    if info.get("url"): table.add_row("URL", str(info.get("url")))
    console.print(table)

@app.command()
def album(
    name: str | None = typer.Option(None, "--name", help="Override album name."),
    artist: str | None = typer.Option(None, "--artist", help="Album artist (recommended)."),
    period: str = typer.Option("week", "-p", "--period", help="day|week|month|quarter|year (for recent count; default week)"),
    json: bool = typer.Option(False, "--json"),
):
    lfm = _get_lastfm()
    ent = _get_current_entities()
    album_name = name or ent["album"]
    artist_name = artist or ent["artist"]
    if not album_name:
        raise typer.BadParameter("No album on current track; provide --name and --artist.")
    info = lfm.album_info(artist_name, album_name)
    overall = int(((info.get("userplaycount")) or 0))
    week = _week_playcount_from_top("album", norm_key(album_name), norm_key(artist_name))
    payload = {"album": album_name, "artist": artist_name, "week_plays": week, "overall_plays": overall, "url": info.get("url")}
    if json:
        console.print(_json.dumps(payload)); return
    table = Table(title="album")
    table.add_column("Field"); table.add_column("Value")
    table.add_row("Album", album_name)
    table.add_row("Artist", artist_name)
    if week is not None: table.add_row("Plays (week)", str(week))
    table.add_row("Plays (overall)", str(overall))
    if info.get("url"): table.add_row("URL", str(info.get("url")))
    console.print(table)

@app.command()
def track(
    name: str | None = typer.Option(None, "--name", help="Override track name."),
    artist: str | None = typer.Option(None, "--artist", help="Track artist (recommended)."),
    period: str = typer.Option("week", "-p", "--period", help="day|week|month|quarter|year (for recent count; default week)"),
    json: bool = typer.Option(False, "--json"),
):
    lfm = _get_lastfm()
    ent = _get_current_entities()
    track_name = name or ent["track"]
    artist_name = artist or ent["artist"]
    info = lfm.track_info(artist_name, track_name)
    overall = int(((info.get("userplaycount")) or 0))
    week = _week_playcount_from_top("track", norm_key(track_name), norm_key(artist_name))
    payload = {"track": track_name, "artist": artist_name, "week_plays": week, "overall_plays": overall, "url": info.get("url")}
    if json:
        console.print(_json.dumps(payload)); return
    table = Table(title="track")
    table.add_column("Field"); table.add_column("Value")
    table.add_row("Track", track_name)
    table.add_row("Artist", artist_name)
    if week is not None: table.add_row("Plays (week)", str(week))
    table.add_row("Plays (overall)", str(overall))
    if info.get("url"): table.add_row("URL", str(info.get("url")))
    console.print(table)

@app.command()
def pace(
    increment: int = typer.Option(5000, "--increment", "-i"),
    target: int | None = typer.Option(None, "--target"),
    period: str = typer.Option("month", "-p", "--period", help="day|week|month|quarter|year (rate sample window; default month)"),
    json: bool = typer.Option(False, "--json"),
):
    """Predict when you'll hit the next milestone."""
    lfm = _get_lastfm()
    p = _parse_period(period)
    days = _period_days(p)
    user = lfm.user_info()
    total = int(user.get("playcount") or 0)

    if target is None:
        if increment <= 0:
            raise typer.BadParameter("increment must be > 0")
        next_target = ((total // increment) + 1) * increment
    else:
        next_target = target
        if next_target <= total:
            raise typer.BadParameter("--target must be greater than current total")

    # estimate rate from recent tracks over window
    cutoff = now_ts() - days * 86400
    count = 0
    page = 1
    seen_old = False
    while page <= 20 and not seen_old:
        rt = lfm.recent_tracks(limit=200, page=page)
        tracks = rt.get("track") or []
        if isinstance(tracks, dict): tracks=[tracks]
        for t in tracks:
            attrs = t.get("@attr") or {}
            if str(attrs.get("nowplaying","")).lower() == "true":
                continue
            date = t.get("date") or {}
            uts = date.get("uts")
            if not uts:
                continue
            uts_i = int(uts)
            if uts_i < cutoff:
                seen_old = True
                break
            count += 1
        page += 1

    rate_per_day = count / max(days, 1)
    remaining = next_target - total
    eta_days = remaining / rate_per_day if rate_per_day > 0 else None
    eta_ts = int(now_ts() + eta_days * 86400) if eta_days is not None else None

    payload = {
        "total": total,
        "target": next_target,
        "remaining": remaining,
        "period_days": days,
        "sample_scrobbles": count,
        "rate_per_day": rate_per_day,
        "eta_days": eta_days,
        "eta_timestamp": eta_ts,
    }

    if json:
        console.print(_json.dumps(payload)); return

    table = Table(title="pace")
    table.add_column("Field"); table.add_column("Value")
    table.add_row("Current total", str(total))
    table.add_row("Target", str(next_target))
    table.add_row("Remaining", str(remaining))
    table.add_row("Rate (per day)", f"{rate_per_day:.2f}")
    if eta_ts is not None:
        import datetime as dt
        table.add_row("ETA", dt.datetime.fromtimestamp(eta_ts).strftime("%Y-%m-%d"))
        table.add_row("ETA (days)", f"{eta_days:.1f}")
    else:
        table.add_row("ETA", "unknown (no recent scrobbles in sample)")
    console.print(table)

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

@config_app.command("edit")
def config_edit():
    path = config_path()
    cfg = load_config()
    save_config(cfg)
    editor = os.environ.get("EDITOR")
    if not editor:
        console.print(str(path))
        return
    subprocess.call([editor, str(path)])

@app.command()
def doctor():
    cfg = load_config()
    table = Table(title="doctor")
    table.add_column("Check")
    table.add_column("Result")
    table.add_row("Config", str(config_path()))
    table.add_row("Username", "yes" if cfg.get("username") else "no")
    table.add_row("Last.fm API key", "yes" if cfg.get("lastfm_api_key") else "no")
    table.add_row("Last.fm session key", "yes" if cfg.get("lastfm_session_key") else "no")
    table.add_row("Last.fm secret (env)", "yes" if env_get("LEGATO_LASTFM_SECRET") else "no")
    table.add_row("YouTube API key", "yes" if cfg.get("youtube_api_key") else "no")
    console.print(table)
    console.print("[dim]Tip: run `legato help` for minimal usage output.[/dim]")

def main():
    try:
        app()
    except (LastfmError, YouTubeError) as e:
        console.print(f"[red]error[/red] {e}")
        raise SystemExit(1)

if __name__ == "__main__":
    main()
