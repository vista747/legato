from __future__ import annotations
import time
import subprocess
import html
import re
import click

from .config import load_config, save_config, config_path
from .lastfm import LastfmClient, LastfmError, validate_app_creds, period_to_lastfm
from .utils import now_ts, human_delta, clamp, lastfm_user_url, lastfm_artist_url, lastfm_album_url, lastfm_track_url, youtube_search_url
from .ansi import hyperlink, sgr, reset
from .theme import get_theme, set_accent, NAMED
from . import __version__

THEME_COLOR_NAMES = ", ".join(NAMED.keys())

def eprint(msg: str) -> None:
    click.echo(msg, err=True)

def fatal(msg: str, code: int = 1) -> None:
    eprint(f"error {msg}")
    raise SystemExit(code)

def make_client() -> LastfmClient:
    validate_app_creds()
    cfg = load_config()
    from . import lastfm as lastfm_mod
    return LastfmClient(
        api_key=lastfm_mod.APP_API_KEY,
        api_secret=lastfm_mod.APP_API_SECRET,
        session_key=cfg.get("lastfm_session_key"),
        username=cfg.get("username"),
    )

def require_connected(lfm: LastfmClient) -> None:
    # For commands that need a default user (like current/recent/top without --user)
    if not lfm.username:
        fatal("No last.fm account connected, run `legato setup` to connect your last.fm account")

def accent(s: str) -> str:
    return get_theme().accentize(s)

def link(text: str, url: str) -> str:
    return hyperlink(text, url)

def bold(text: str) -> str:
    return f"{sgr('1')}{text}{reset()}"

def _split_csv(value: str, min_parts: int, max_parts: int, what: str) -> list[str]:
    parts = [p.strip() for p in value.split("|")]
    if len(parts) < min_parts or len(parts) > max_parts or any(not p for p in parts):
        raise click.ClickException(
            f"{what} must use '|' separators with {min_parts}..{max_parts} parts (quote the full value)"
        )
    return parts

def _listify(items):
    if not items:
        return []
    return [items] if isinstance(items, dict) else items

def _recent_tracks_page(
    lfm: LastfmClient,
    user: str | None,
    page: int,
    limit: int = 200,
    retries: int = 2,
) -> dict | None:
    for attempt in range(retries + 1):
        try:
            return lfm.recent_tracks(user=user, limit=limit, page=page)
        except LastfmError:
            if attempt >= retries:
                return None
            time.sleep(0.4 * (attempt + 1))
    return None

def _plays_text(value: str | int) -> str:
    n = int(value)
    return f"{n} play" if n == 1 else f"{n} plays"

def _top_for_year(
    lfm: LastfmClient,
    user: str,
    kind: str,
    year: int,
    limit: int,
    max_pages: int = 300,
) -> list[tuple[str, str, int]]:
    counts: dict[tuple[str, str], int] = {}
    page = 1

    while page <= max_pages:
        rt = _recent_tracks_page(lfm, user=user, limit=200, page=page)
        if rt is None:
            break
        tracks = _listify(rt.get("track"))
        if not tracks:
            break

        seen_older = False
        for t in tracks:
            if str((t.get("@attr") or {}).get("nowplaying", "")).lower() == "true":
                continue
            uts = (t.get("date") or {}).get("uts")
            if not uts:
                continue
            ts_year = time.gmtime(int(uts)).tm_year
            if ts_year < year:
                seen_older = True
                continue
            if ts_year > year:
                continue

            artist = (t.get("artist") or {}).get("name") or (t.get("artist") or {}).get("#text") or ""
            track = t.get("name") or ""
            album = (t.get("album") or {}).get("#text") or ""

            if kind == "artist":
                if not artist:
                    continue
                key = (artist, "")
            elif kind == "album":
                if not artist or not album:
                    continue
                key = (album, artist)
            else:
                if not artist or not track:
                    continue
                key = (track, artist)
            counts[key] = counts.get(key, 0) + 1

        if seen_older:
            break

        attr = rt.get("@attr") or {}
        total_pages_raw = attr.get("totalPages")
        if total_pages_raw:
            try:
                if page >= int(total_pages_raw):
                    break
            except ValueError:
                pass
        page += 1

    ranked = sorted(counts.items(), key=lambda kv: kv[1], reverse=True)[:limit]
    return [(k[0], k[1], v) for k, v in ranked]

def _strip_markup(text: str) -> str:
    no_tags = re.sub(r"<[^>]+>", "", text or "")
    clean = html.unescape(no_tags).replace("\n", " ").strip()
    clean = re.sub(r"\s+", " ", clean)
    clean = re.sub(r"\s*Read more on Last\.fm\s*$", "…", clean, flags=re.IGNORECASE)
    return clean

def _entity_description(kind: str, info: dict) -> str:
    if kind == "artist":
        return _strip_markup(((info.get("bio") or {}).get("summary") or ""))
    return _strip_markup(((info.get("wiki") or {}).get("summary") or ""))

def _entity_recent_and_first(
    lfm: LastfmClient,
    user: str,
    kind: str,
    artist_name: str,
    item_name: str | None,
    recent_days: int = 30,
    max_pages: int = 60,
    max_seconds: float = 12.0,
) -> tuple[int, int | None, bool]:
    cutoff = now_ts() - recent_days * 86400
    recent_count = 0
    first_ts = None
    page = 1
    partial = False
    started = time.time()

    while page <= max_pages:
        if time.time() - started > max_seconds:
            partial = True
            break
        rt = _recent_tracks_page(lfm, user=user, limit=200, page=page)
        if rt is None:
            partial = True
            break
        tracks = _listify(rt.get("track"))
        if not tracks:
            break

        for t in tracks:
            if str((t.get("@attr") or {}).get("nowplaying", "")).lower() == "true":
                continue
            cur_artist = (t.get("artist") or {}).get("name") or (t.get("artist") or {}).get("#text") or ""
            cur_track = t.get("name") or ""
            cur_album = (t.get("album") or {}).get("#text") or ""
            if kind == "artist":
                is_match = cur_artist.casefold() == artist_name.casefold()
            elif kind == "album":
                is_match = (
                    cur_artist.casefold() == artist_name.casefold()
                    and (item_name or "").casefold() == cur_album.casefold()
                )
            else:
                is_match = (
                    cur_artist.casefold() == artist_name.casefold()
                    and (item_name or "").casefold() == cur_track.casefold()
                )
            if not is_match:
                continue

            uts = (t.get("date") or {}).get("uts")
            if not uts:
                continue
            ts = int(uts)
            if ts >= cutoff:
                recent_count += 1
            if first_ts is None or ts < first_ts:
                first_ts = ts

        attr = rt.get("@attr") or {}
        total_pages_raw = attr.get("totalPages")
        if total_pages_raw:
            try:
                if page >= int(total_pages_raw):
                    break
                if int(total_pages_raw) > max_pages:
                    partial = True
            except ValueError:
                pass
        page += 1

    return recent_count, first_ts, partial

def _print_stats_block(
    lfm: LastfmClient,
    user: str,
    kind: str,
    artist_name: str,
    item_name: str | None,
    lifetime_plays: str,
    description: str,
) -> None:
    recent_plays, first_ts, partial = _entity_recent_and_first(lfm, user, kind, artist_name, item_name)
    if description:
        click.echo(description)
    click.echo(f"{bold('Plays (lifetime):')} {lifetime_plays}")
    click.echo(f"{bold('Plays (recent 30d):')} {recent_plays}")
    if first_ts is None:
        click.echo(f"{bold('Discovery:')} unknown")
    else:
        click.echo(
            f"{bold('Discovery:')} {time.strftime('%Y-%m-%d', time.localtime(first_ts))} ({human_delta(first_ts)})"
        )
    if partial:
        click.echo(f"{bold('Note:')} stats are partial (history scan limit reached).")

@click.group(context_settings=dict(help_option_names=["-h", "--help"]))
@click.option(
    "--version",
    is_flag=True,
    is_eager=True,
    expose_value=False,
    callback=lambda ctx, param, value: (click.echo(f"legato, version {__version__}"), ctx.exit()) if value and not ctx.resilient_parsing else None,
    help="Show version and exit.",
)
def main():
    """legato - minimal Last.fm CLI"""
    pass

@main.command()
@click.option("--timeout", default=120, show_default=True, type=int)
def setup(timeout: int):
    """Connect your Last.fm account (opens browser, then polls until approved)."""
    lfm = make_client()
    cfg = load_config()

    click.echo("Requesting token…")
    token = lfm.get_token()
    url = f"https://www.last.fm/api/auth/?api_key={lfm.api_key}&token={token}"

    try:
        subprocess.Popen(["xdg-open", url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass

    click.echo("Authorize in browser:")
    click.echo(url)
    click.echo("Waiting for approval… (Ctrl+C to cancel)")

    start = time.time()
    while True:
        if time.time() - start > timeout:
            fatal("Timed out waiting for approval.")
        sess = lfm.try_get_session(token)
        if sess:
            sk, username = sess
            cfg.set("lastfm_session_key", sk)
            cfg.set("username", username)
            save_config(cfg)
            click.echo(f"Connected as {link(username, lastfm_user_url(username))}")
            return
        time.sleep(2)

@main.command()
def disconnect():
    """Disconnect local Last.fm session from legato."""
    cfg = load_config()
    old_user = cfg.get("username")
    cfg.data.pop("lastfm_session_key", None)
    cfg.data.pop("username", None)
    save_config(cfg)
    if old_user:
        click.echo(f"Disconnected {old_user}")
    else:
        click.echo("No account was connected")

def _current_track(user: str | None = None):
    lfm = make_client()
    if user is None:
        require_connected(lfm)
    rt = lfm.recent_tracks(user=user, limit=1)
    tracks = rt.get("track") or []
    if isinstance(tracks, dict):
        tracks = [tracks]
    if not tracks:
        fatal("No recent tracks.")
    t0 = tracks[0]
    artist = (t0.get("artist") or {}).get("name") or (t0.get("artist") or {}).get("#text") or ""
    track = t0.get("name") or ""
    album = (t0.get("album") or {}).get("#text") or ""
    url = t0.get("url") or lastfm_track_url(artist, track)
    now_playing = str((t0.get("@attr") or {}).get("nowplaying", "")).lower() == "true"
    ts = None
    if not now_playing:
        uts = (t0.get("date") or {}).get("uts")
        if uts:
            ts = int(uts)
    return {"artist": artist, "track": track, "album": album, "url": url, "now_playing": now_playing, "ts": ts, "user": user or lfm.username or ""}

@main.command()
@click.option("--user", default=None)
def current(user: str | None):
    """Show now playing or most recent track."""
    ent = _current_track(user=user)
    u = ent["user"] or user or ""
    click.echo(accent(f"Now playing for {u}:") if ent["now_playing"] else accent(f"Last played for {u}:"))
    click.echo(link(ent["track"], ent["url"]))
    parts = []
    if ent["artist"]:
        parts.append(link(ent["artist"], lastfm_artist_url(ent["artist"])))
    if ent["album"]:
        parts.append(link(ent["album"], lastfm_album_url(ent["artist"], ent["album"])))
    click.echo(" - ".join(parts) if parts else "")
    if (not ent["now_playing"]) and ent["ts"] is not None:
        click.echo(human_delta(ent["ts"]))

@main.command("fm")
@click.option("--user", default=None)
def fm_alias(user: str | None):
    """FMbot-style alias for `current`."""
    current(user=user)

@main.command()
@click.option("-n", "--limit", default=10, show_default=True, type=int)
@click.option("--user", default=None)
def recent(limit: int, user: str | None):
    """Show recent scrobbles."""
    limit = clamp(limit, 1, 50)
    lfm = make_client()
    if user is None:
        require_connected(lfm)
    u = user or lfm.username or ""
    click.echo(accent(f"Recent for {u}:"))
    rt = lfm.recent_tracks(user=u, limit=limit)
    tracks = rt.get("track") or []
    if isinstance(tracks, dict):
        tracks = [tracks]
    for t in tracks[:limit]:
        artist = (t.get("artist") or {}).get("name") or (t.get("artist") or {}).get("#text") or ""
        track = t.get("name") or ""
        url = t.get("url") or lastfm_track_url(artist, track)
        np = str((t.get("@attr") or {}).get("nowplaying", "")).lower() == "true"
        line = f"- {link(track, url)} — {link(artist, lastfm_artist_url(artist))}"
        if not np:
            uts = (t.get("date") or {}).get("uts")
            if uts:
                line += f" ({human_delta(int(uts))})"
        click.echo(line)

@main.group()
def top():
    """Top charts."""
    pass

def _period(p: str) -> str:
    p = p.strip().lower()
    allowed = {"day","week","month","quarter","year","overall","alltime","all","d","w","m","q","y","o"}
    if p not in allowed:
        raise click.BadParameter("period must be day|week|month|quarter|year|overall|alltime|all")
    return {
        "d": "day",
        "w": "week",
        "m": "month",
        "q": "quarter",
        "y": "year",
        "o": "overall",
        "alltime": "overall",
        "all": "overall",
    }.get(p, p)

@top.command("artist")
@click.option(
    "-p",
    "--period",
    "--time",
    "--range",
    default="week",
    show_default=True,
    help="Time period: day|week|month|quarter|year|overall|alltime|all (aliases: d|w|m|q|y|o)",
)
@click.option("-n", "--limit", default=10, show_default=True, type=int)
@click.option("--year", "year_filter", default=None, type=int, help="Specific calendar year (e.g. 2024).")
@click.option("--user", default=None)
def top_artist(period: str, limit: int, year_filter: int | None, user: str | None):
    """Top artists for a period."""
    period = _period(period)
    limit = clamp(limit, 1, 50)
    lfm = make_client()
    if user is None:
        require_connected(lfm)
    u = user or lfm.username or ""
    if year_filter is not None:
        click.echo(accent(f"Top artists ({year_filter}) for {u}:"))
        rows = _top_for_year(lfm, u, "artist", year_filter, limit=limit)
        for i, (name, _, plays) in enumerate(rows, start=1):
            click.echo(f"{i}. {link(name, lastfm_artist_url(name))} ({_plays_text(plays)})")
        return

    click.echo(accent(f"Top artists ({period}) for {u}:"))
    data = lfm.top_artists(u, period_to_lastfm(period), limit=limit)
    items = data.get("artist") or []
    if isinstance(items, dict):
        items = [items]
    for i, it in enumerate(items[:limit], start=1):
        name = it.get("name") or ""
        plays = it.get("playcount") or "0"
        click.echo(f"{i}. {link(name, lastfm_artist_url(name))} ({_plays_text(plays)})")

@top.command("album")
@click.option(
    "-p",
    "--period",
    "--time",
    "--range",
    default="week",
    show_default=True,
    help="Time period: day|week|month|quarter|year|overall|alltime|all (aliases: d|w|m|q|y|o)",
)
@click.option("-n", "--limit", default=10, show_default=True, type=int)
@click.option("--year", "year_filter", default=None, type=int, help="Specific calendar year (e.g. 2024).")
@click.option("--user", default=None)
def top_album(period: str, limit: int, year_filter: int | None, user: str | None):
    """Top albums for a period."""
    period = _period(period)
    limit = clamp(limit, 1, 50)
    lfm = make_client()
    if user is None:
        require_connected(lfm)
    u = user or lfm.username or ""
    if year_filter is not None:
        click.echo(accent(f"Top albums ({year_filter}) for {u}:"))
        rows = _top_for_year(lfm, u, "album", year_filter, limit=limit)
        for i, (name, artist, plays) in enumerate(rows, start=1):
            click.echo(f"{i}. {link(name, lastfm_album_url(artist, name))} — {link(artist, lastfm_artist_url(artist))} ({_plays_text(plays)})")
        return

    click.echo(accent(f"Top albums ({period}) for {u}:"))
    data = lfm.top_albums(u, period_to_lastfm(period), limit=limit)
    items = data.get("album") or []
    if isinstance(items, dict):
        items = [items]
    for i, it in enumerate(items[:limit], start=1):
        name = it.get("name") or ""
        artist = (it.get("artist") or {}).get("name") or ""
        plays = it.get("playcount") or "0"
        click.echo(f"{i}. {link(name, lastfm_album_url(artist, name))} — {link(artist, lastfm_artist_url(artist))} ({_plays_text(plays)})")

@top.command("track")
@click.option(
    "-p",
    "--period",
    "--time",
    "--range",
    default="week",
    show_default=True,
    help="Time period: day|week|month|quarter|year|overall|alltime|all (aliases: d|w|m|q|y|o)",
)
@click.option("-n", "--limit", default=10, show_default=True, type=int)
@click.option("--year", "year_filter", default=None, type=int, help="Specific calendar year (e.g. 2024).")
@click.option("--user", default=None)
def top_track(period: str, limit: int, year_filter: int | None, user: str | None):
    """Top tracks for a period."""
    period = _period(period)
    limit = clamp(limit, 1, 50)
    lfm = make_client()
    if user is None:
        require_connected(lfm)
    u = user or lfm.username or ""
    if year_filter is not None:
        click.echo(accent(f"Top tracks ({year_filter}) for {u}:"))
        rows = _top_for_year(lfm, u, "track", year_filter, limit=limit)
        for i, (name, artist, plays) in enumerate(rows, start=1):
            click.echo(f"{i}. {link(name, lastfm_track_url(artist, name))} — {link(artist, lastfm_artist_url(artist))} ({_plays_text(plays)})")
        return

    click.echo(accent(f"Top tracks ({period}) for {u}:"))
    data = lfm.top_tracks(u, period_to_lastfm(period), limit=limit)
    items = data.get("track") or []
    if isinstance(items, dict):
        items = [items]
    for i, it in enumerate(items[:limit], start=1):
        name = it.get("name") or ""
        artist = (it.get("artist") or {}).get("name") or ""
        plays = it.get("playcount") or "0"
        click.echo(f"{i}. {link(name, lastfm_track_url(artist, name))} — {link(artist, lastfm_artist_url(artist))} ({_plays_text(plays)})")

@main.command()
@click.argument("query_arg", required=False)
@click.option("--name", default=None)
@click.option("--user", default=None)
def artist(query_arg: str | None, name: str | None, user: str | None):
    """Artist lookup with plays, recent plays, discovery date, and Last.fm description."""
    lfm = make_client()
    if user is None:
        require_connected(lfm)
    u = user or lfm.username or ""
    if query_arg:
        name = name or query_arg
    if not name:
        ent = _current_track(user=u)
        name = ent["artist"]
    info = lfm.artist_info(name, username=u)
    url = info.get("url") or lastfm_artist_url(name)
    stats = info.get("stats") or {}
    overall = stats.get("userplaycount") or "0"
    description = _entity_description("artist", info)
    click.echo(link(name, url))
    _print_stats_block(
        lfm=lfm,
        user=u,
        kind="artist",
        artist_name=name,
        item_name=None,
        lifetime_plays=str(overall),
        description=description,
    )

@main.command()
@click.argument("query_arg", required=False)
@click.option("--name", default=None)
@click.option("--artist", "artist_name", default=None)
@click.option("--query", default=None, help="Quoted pipe input: ARTIST | ALBUM")
@click.option("--user", default=None)
def album(query_arg: str | None, name: str | None, artist_name: str | None, query: str | None, user: str | None):
    """Album lookup with plays, recent plays, discovery date, and Last.fm description."""
    lfm = make_client()
    if user is None:
        require_connected(lfm)
    u = user or lfm.username or ""
    query_value = query_arg or query
    if query_value:
        q_artist, q_album = _split_csv(query_value, 2, 2, "album query")
        artist_name = artist_name or q_artist
        name = name or q_album
    if not name or not artist_name:
        ent = _current_track(user=u)
        name = name or ent["album"]
        artist_name = artist_name or ent["artist"]
    if not name or not artist_name:
        fatal("Missing album; pass --name and --artist.")
    info = lfm.album_info(artist_name, name, username=u)
    url = info.get("url") or lastfm_album_url(artist_name, name)
    overall = info.get("userplaycount") or "0"
    description = _entity_description("album", info)
    click.echo(link(name, url))
    click.echo(link(artist_name, lastfm_artist_url(artist_name)))
    _print_stats_block(
        lfm=lfm,
        user=u,
        kind="album",
        artist_name=artist_name,
        item_name=name,
        lifetime_plays=str(overall),
        description=description,
    )

@main.command()
@click.argument("query_arg", required=False)
@click.option("--name", default=None)
@click.option("--artist", "artist_name", default=None)
@click.option("--query", default=None, help="Quoted pipe input: ARTIST | TRACK")
@click.option("--user", default=None)
def track(query_arg: str | None, name: str | None, artist_name: str | None, query: str | None, user: str | None):
    """Track lookup with plays, recent plays, discovery date, and Last.fm description."""
    lfm = make_client()
    if user is None:
        require_connected(lfm)
    u = user or lfm.username or ""
    query_value = query_arg or query
    if query_value:
        q_artist, q_track = _split_csv(query_value, 2, 2, "track query")
        artist_name = artist_name or q_artist
        name = name or q_track
    if not name or not artist_name:
        ent = _current_track(user=u)
        name = name or ent["track"]
        artist_name = artist_name or ent["artist"]
    info = lfm.track_info(artist_name, name, username=u)
    url = info.get("url") or lastfm_track_url(artist_name, name)
    overall = info.get("userplaycount") or "0"
    description = _entity_description("track", info)
    click.echo(link(name, url))
    click.echo(link(artist_name, lastfm_artist_url(artist_name)))
    _print_stats_block(
        lfm=lfm,
        user=u,
        kind="track",
        artist_name=artist_name,
        item_name=name,
        lifetime_plays=str(overall),
        description=description,
    )

@main.command()
@click.option("--target", type=click.Choice(["artist", "album", "track"], case_sensitive=False), default="track", show_default=True)
@click.option("--query", default=None, help="Quoted pipe input: ARTIST | ALBUM, ARTIST | TRACK, or ARTIST")
@click.option("--name", default=None)
@click.option("--artist", "artist_name", default=None)
@click.option("--user", default=None)
def plays(target: str, query: str | None, name: str | None, artist_name: str | None, user: str | None):
    """FMbot-style playcount lookup for artist/album/track."""
    lfm = make_client()
    if user is None:
        require_connected(lfm)
    u = user or lfm.username or ""
    target = target.lower()

    if query:
        if target == "artist":
            q_artist = _split_csv(query, 1, 1, "--query")[0]
            artist_name = artist_name or q_artist
        else:
            q_artist, q_name = _split_csv(query, 2, 2, "--query")
            artist_name = artist_name or q_artist
            name = name or q_name

    if target == "artist":
        if not artist_name:
            ent = _current_track(user=u)
            artist_name = ent["artist"]
        info = lfm.artist_info(artist_name, username=u)
        url = info.get("url") or lastfm_artist_url(artist_name)
        plays_v = (info.get("stats") or {}).get("userplaycount") or "0"
        click.echo(link(artist_name, url))
        click.echo(f"Plays (overall): {plays_v}")
        return

    if not name or not artist_name:
        ent = _current_track(user=u)
        name = name or (ent["album"] if target == "album" else ent["track"])
        artist_name = artist_name or ent["artist"]

    if target == "album":
        info = lfm.album_info(artist_name, name, username=u)
        url = info.get("url") or lastfm_album_url(artist_name, name)
        plays_v = info.get("userplaycount") or "0"
        click.echo(link(name, url))
        click.echo(link(artist_name, lastfm_artist_url(artist_name)))
        click.echo(f"Plays (overall): {plays_v}")
        return

    info = lfm.track_info(artist_name, name, username=u)
    url = info.get("url") or lastfm_track_url(artist_name, name)
    plays_v = info.get("userplaycount") or "0"
    click.echo(link(name, url))
    click.echo(link(artist_name, lastfm_artist_url(artist_name)))
    click.echo(f"Plays (overall): {plays_v}")

@main.command()
@click.argument("artist")
@click.argument("track")
@click.option("--album", default=None)
def np(artist: str, track: str, album: str | None):
    """Update now playing."""
    lfm = make_client()
    lfm.update_now_playing(artist, track, album=album)
    click.echo("OK")

@main.command()
@click.argument("artist_or_csv")
@click.argument("track", required=False)
@click.option("--album", default=None)
@click.option("--ts", default="now", show_default=True)
def scrobble(artist_or_csv: str, track: str | None, album: str | None, ts: str):
    """Submit a scrobble. Accepts ARTIST TRACK or "ARTIST | TRACK[ | ALBUM]" in quotes."""
    if track is None:
        parts = _split_csv(artist_or_csv, 2, 3, "scrobble input")
        artist = parts[0]
        track = parts[1]
        if len(parts) == 3 and not album:
            album = parts[2]
    else:
        artist = artist_or_csv
    timestamp = now_ts() if ts.strip().lower() == "now" else int(ts)
    lfm = make_client()
    lfm.scrobble(artist, track, timestamp=timestamp, album=album)
    click.echo(f"Scrobbled: {link(track, lastfm_track_url(artist, track))} — {link(artist, lastfm_artist_url(artist))}")
    if album:
        click.echo(f"Album: {link(album, lastfm_album_url(artist, album))}")

@main.command()
@click.argument("artist", required=False)
@click.argument("track", required=False)
def love(artist: str | None, track: str | None):
    """Love a track (defaults to current)."""
    if not artist or not track:
        ent = _current_track()
        artist, track = ent["artist"], ent["track"]
    lfm = make_client()
    lfm.love(artist, track)
    click.echo("Loved")

@main.command()
@click.argument("artist", required=False)
@click.argument("track", required=False)
def unlove(artist: str | None, track: str | None):
    """Unlove a track (defaults to current)."""
    if not artist or not track:
        ent = _current_track()
        artist, track = ent["artist"], ent["track"]
    lfm = make_client()
    lfm.unlove(artist, track)
    click.echo("Unloved")

@main.command()
@click.option("--user", default=None)
def profile(user: str | None):
    """User profile summary."""
    lfm = make_client()
    if user is None:
        require_connected(lfm)
    u = user or lfm.username or ""
    info = lfm.user_info(u)
    name = info.get("name") or u
    url = info.get("url") or lastfm_user_url(u)
    plays = info.get("playcount") or "0"
    country = info.get("country") or ""
    click.echo(link(name, url))
    click.echo(f"Scrobbles: {plays}")
    if country:
        click.echo(f"Country: {country}")

@main.command()
@click.option("--user", default=None)
@click.option("-n", "--limit", default=20, show_default=True, type=int)
def friends(user: str | None, limit: int):
    """List friends."""
    limit = clamp(limit, 1, 50)
    lfm = make_client()
    if user is None:
        require_connected(lfm)
    u = user or lfm.username or ""
    click.echo(accent(f"Friends for {u}:"))
    data = lfm.friends(u, limit=limit, recenttracks=False)
    items = data.get("user") or []
    if isinstance(items, dict):
        items = [items]
    for it in items[:limit]:
        name = it.get("name") or ""
        click.echo(f"- {link(name, lastfm_user_url(name))}")

@main.command()
@click.option("-i", "--increment", default=5000, show_default=True, type=int)
@click.option(
    "-p",
    "--period",
    "--time",
    "--range",
    default="month",
    show_default=True,
    help="Time period: day|week|month|quarter|year|overall|alltime|all (aliases: d|w|m|q|y|o)",
)
def pace(increment: int, period: str):
    """Estimate when you'll hit next milestone based on recent rate."""
    period = _period(period)
    days = {"day":1,"week":7,"month":30,"quarter":90,"year":365,"overall":30}.get(period, 30)
    lfm = make_client()
    require_connected(lfm)
    info = lfm.user_info()
    total = int(info.get("playcount") or 0)
    next_target = ((total // increment) + 1) * increment
    remaining = next_target - total

    cutoff = now_ts() - days * 86400
    count = 0
    page = 1
    seen_old = False
    while page <= 20 and not seen_old:
        rt = _recent_tracks_page(lfm, user=None, limit=200, page=page)
        if rt is None:
            break
        tracks = rt.get("track") or []
        if isinstance(tracks, dict):
            tracks = [tracks]
        for t in tracks:
            if str((t.get("@attr") or {}).get("nowplaying", "")).lower() == "true":
                continue
            uts = (t.get("date") or {}).get("uts")
            if not uts:
                continue
            uts_i = int(uts)
            if uts_i < cutoff:
                seen_old = True
                break
            count += 1
        page += 1

    rate = count / max(days, 1)
    click.echo(f"Total scrobbles: {total}")
    click.echo(f"Next target: {next_target} (remaining {remaining})")
    click.echo(f"Rate: {rate:.2f}/day (sample {count} over {days}d)")
    if rate <= 0:
        click.echo("ETA: unknown")
        return
    eta_days = remaining / rate
    eta_ts = int(time.time() + eta_days * 86400)
    click.echo(f"ETA: {time.strftime('%Y-%m-%d', time.localtime(eta_ts))} (~{eta_days:.1f} days)")

@main.command()
@click.argument("artist", required=False)
@click.argument("track", required=False)
@click.option("--open", "open_", is_flag=True, help="Open the search in browser.")
def yt(artist: str | None, track: str | None, open_: bool):
    """YouTube search link for a track (smarter matching coming soon)."""
    if not artist or not track:
        ent = _current_track()
        artist, track = ent["artist"], ent["track"]
    url = youtube_search_url(artist, track)
    click.echo(link("YouTube search", url))
    click.echo("Note: smarter YouTube matching will be added soon.")
    if open_:
        try:
            subprocess.Popen(["xdg-open", url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass

@main.command()
@click.option("--artist", "artist_name", default=None, help="Filter artist name.")
@click.option("--track", "track_name", default=None, help="Filter track name (optionally with --artist).")
@click.option("--query", default=None, help="Quoted pipe input: ARTIST or ARTIST | TRACK")
@click.option("--user", default=None)
@click.option("--max-pages", default=200, show_default=True, type=int)
def first(artist_name: str | None, track_name: str | None, query: str | None, user: str | None, max_pages: int):
    """FMbot-style first scrobble lookup."""
    lfm = make_client()
    if user is None:
        require_connected(lfm)
    u = user or lfm.username or ""
    max_pages = clamp(max_pages, 1, 500)

    if query:
        q_parts = _split_csv(query, 1, 2, "--query")
        artist_name = artist_name or q_parts[0]
        if len(q_parts) == 2:
            track_name = track_name or q_parts[1]

    if not artist_name and not track_name:
        ent = _current_track(user=u)
        artist_name, track_name = ent["artist"], ent["track"]

    page = 1
    latest_match = None
    while page <= max_pages:
        rt = _recent_tracks_page(lfm, user=u, limit=200, page=page)
        if rt is None:
            break
        tracks = _listify(rt.get("track"))
        if not tracks:
            break

        for t in tracks:
            if str((t.get("@attr") or {}).get("nowplaying", "")).lower() == "true":
                continue
            cur_artist = (t.get("artist") or {}).get("name") or (t.get("artist") or {}).get("#text") or ""
            cur_track = t.get("name") or ""
            if artist_name and cur_artist.casefold() != artist_name.casefold():
                continue
            if track_name and cur_track.casefold() != track_name.casefold():
                continue
            uts = (t.get("date") or {}).get("uts")
            if not uts:
                continue
            latest_match = {
                "artist": cur_artist,
                "track": cur_track,
                "url": t.get("url") or lastfm_track_url(cur_artist, cur_track),
                "ts": int(uts),
            }

        attr = rt.get("@attr") or {}
        total_pages_raw = attr.get("totalPages")
        if total_pages_raw:
            try:
                if page >= int(total_pages_raw):
                    break
            except ValueError:
                pass
        page += 1

    if not latest_match:
        fatal("No matching scrobbles found.")

    click.echo(accent(f"First scrobble for {u}:"))
    click.echo(link(latest_match["track"], latest_match["url"]))
    click.echo(link(latest_match["artist"], lastfm_artist_url(latest_match["artist"])))
    click.echo(time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(latest_match["ts"])))

@main.command()
@click.argument("other_user")
@click.option("--user", default=None, help="Base user (defaults to connected account).")
@click.option(
    "-p",
    "--period",
    "--time",
    "--range",
    default="overall",
    show_default=True,
    help="Time period: day|week|month|quarter|year|overall|alltime|all (aliases: d|w|m|q|y|o)",
)
@click.option("-n", "--limit", default=100, show_default=True, type=int)
def taste(other_user: str, user: str | None, period: str, limit: int):
    """FMbot-style taste comparison using shared top artists."""
    period = _period(period)
    limit = clamp(limit, 10, 500)
    lfm = make_client()
    if user is None:
        require_connected(lfm)
    base_user = user or lfm.username or ""

    left = _listify(lfm.top_artists(base_user, period_to_lastfm(period), limit=limit).get("artist"))
    right = _listify(lfm.top_artists(other_user, period_to_lastfm(period), limit=limit).get("artist"))

    left_map = {str(it.get("name") or ""): int(it.get("playcount") or 0) for it in left if it.get("name")}
    right_map = {str(it.get("name") or ""): int(it.get("playcount") or 0) for it in right if it.get("name")}
    shared = [name for name in left_map.keys() if name in right_map]

    overlap_num = sum(min(left_map[n], right_map[n]) for n in shared)
    overlap_den = sum(max(left_map.get(n, 0), right_map.get(n, 0)) for n in set(left_map) | set(right_map))
    score = (100.0 * overlap_num / overlap_den) if overlap_den else 0.0

    click.echo(accent(f"Taste: {base_user} vs {other_user} ({period})"))
    click.echo(f"Compatibility: {score:.1f}%")
    click.echo(f"Shared artists: {len(shared)}")

    if not shared:
        return
    ranked = sorted(shared, key=lambda n: min(left_map[n], right_map[n]), reverse=True)[:10]
    for i, name in enumerate(ranked, start=1):
        click.echo(f"{i}. {link(name, lastfm_artist_url(name))} ({left_map[name]} / {right_map[name]})")

@main.group()
def theme():
    """Theme / accent color.

    Named colors: red, bright_red, orange, yellow, green, blue, magenta, cyan, white.
    """
    pass

@theme.command("show")
def theme_show():
    t = get_theme()
    click.echo(f"accent_sgr={t.accent}")

@theme.command("set")
@click.argument("color", metavar=f"COLOR ({THEME_COLOR_NAMES}|SGR)")
def theme_set(color: str):
    """Set accent color.

    COLOR can be one of: red, bright_red, orange, yellow, green, blue, magenta, cyan, white
    or an SGR code like: 1;91
    """
    try:
        t = set_accent(color)
    except Exception as e:
        raise click.ClickException(str(e))
    click.echo(f"accent_sgr={t.accent}")

@main.command()
def doctor():
    """Config + connectivity sanity."""
    click.echo(f"Config: {config_path()}")
    cfg = load_config()
    click.echo(f"Username: {cfg.get('username') or '(none)'}")
    click.echo(f"Session key: {'yes' if cfg.get('lastfm_session_key') else 'no'}")
    click.echo("Tip: if setup fails, confirm your app API key/secret and that your key isn’t suspended.")

@main.command()
@click.argument("method")
@click.argument("pairs", nargs=-1)
@click.option("--write", is_flag=True, help="Allow POST write calls (dangerous).")
def api(method: str, pairs: tuple[str, ...], write: bool):
    """Call a Last.fm API method directly: legato api user.getInfo user=NAME"""
    lfm = make_client()
    params = {"method": method}
    for p in pairs:
        if "=" not in p:
            raise click.ClickException("Params must be key=value")
        k, v = p.split("=", 1)
        params[k] = v

    write_methods = {"track.scrobble","track.updatenowplaying","track.love","track.unlove","auth.getsession"}
    is_write = method.strip().lower() in write_methods
    if is_write and not write:
        raise click.ClickException("Refusing write method without --write.")
    signed = is_write and method.strip().lower() != "auth.getsession"
    http_method = "POST" if is_write and method.strip().lower() != "auth.getsession" else "GET"
    if signed:
        if not lfm.session_key:
            raise click.ClickException("Not connected. Run `legato setup`.")
        params["sk"] = lfm.session_key

    data = lfm._request(http_method, params, signed=signed)
    click.echo(data)

def _run():
    try:
        main()
    except LastfmError as e:
        fatal(str(e), code=1)

if __name__ == "__main__":
    _run()
