from __future__ import annotations
import time
import subprocess
import click

from .config import load_config, save_config, config_path
from .lastfm import LastfmClient, LastfmError, validate_app_creds, period_to_lastfm
from .utils import now_ts, human_delta, clamp, lastfm_user_url, lastfm_artist_url, lastfm_album_url, lastfm_track_url, youtube_search_url
from .ansi import hyperlink
from .theme import get_theme, set_accent

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

def accent(s: str) -> str:
    return get_theme().accentize(s)

def link(text: str, url: str) -> str:
    return hyperlink(text, url)

@click.group(context_settings=dict(help_option_names=["-h", "--help"]))
def main():
    """legato - minimal Last.fm CLI (Linux-only)."""
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

def _current_track(user: str | None = None):
    lfm = make_client()
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

@main.command()
@click.option("-n", "--limit", default=10, show_default=True, type=int)
@click.option("--user", default=None)
def recent(limit: int, user: str | None):
    """Show recent scrobbles."""
    limit = clamp(limit, 1, 50)
    lfm = make_client()
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
    allowed = {"day","week","month","quarter","year","overall","d","w","m","q","y"}
    if p not in allowed:
        raise click.BadParameter("period must be day|week|month|quarter|year|overall")
    return {"d":"day","w":"week","m":"month","q":"quarter","y":"year"}.get(p, p)

@top.command("artist")
@click.option("-p", "--period", default="week", show_default=True)
@click.option("-n", "--limit", default=10, show_default=True, type=int)
@click.option("--user", default=None)
def top_artist(period: str, limit: int, user: str | None):
    """Top artists for a period."""
    period = _period(period)
    limit = clamp(limit, 1, 50)
    lfm = make_client()
    u = user or lfm.username or ""
    click.echo(accent(f"Top artists ({period}) for {u}:"))
    data = lfm.top_artists(u, period_to_lastfm(period), limit=limit)
    items = data.get("artist") or []
    if isinstance(items, dict):
        items = [items]
    for i, it in enumerate(items[:limit], start=1):
        name = it.get("name") or ""
        plays = it.get("playcount") or "0"
        click.echo(f"{i}. {link(name, lastfm_artist_url(name))} ({plays})")

@top.command("album")
@click.option("-p", "--period", default="week", show_default=True)
@click.option("-n", "--limit", default=10, show_default=True, type=int)
@click.option("--user", default=None)
def top_album(period: str, limit: int, user: str | None):
    """Top albums for a period."""
    period = _period(period)
    limit = clamp(limit, 1, 50)
    lfm = make_client()
    u = user or lfm.username or ""
    click.echo(accent(f"Top albums ({period}) for {u}:"))
    data = lfm.top_albums(u, period_to_lastfm(period), limit=limit)
    items = data.get("album") or []
    if isinstance(items, dict):
        items = [items]
    for i, it in enumerate(items[:limit], start=1):
        name = it.get("name") or ""
        artist = (it.get("artist") or {}).get("name") or ""
        plays = it.get("playcount") or "0"
        click.echo(f"{i}. {link(name, lastfm_album_url(artist, name))} — {link(artist, lastfm_artist_url(artist))} ({plays})")

@top.command("track")
@click.option("-p", "--period", default="week", show_default=True)
@click.option("-n", "--limit", default=10, show_default=True, type=int)
@click.option("--user", default=None)
def top_track(period: str, limit: int, user: str | None):
    """Top tracks for a period."""
    period = _period(period)
    limit = clamp(limit, 1, 50)
    lfm = make_client()
    u = user or lfm.username or ""
    click.echo(accent(f"Top tracks ({period}) for {u}:"))
    data = lfm.top_tracks(u, period_to_lastfm(period), limit=limit)
    items = data.get("track") or []
    if isinstance(items, dict):
        items = [items]
    for i, it in enumerate(items[:limit], start=1):
        name = it.get("name") or ""
        artist = (it.get("artist") or {}).get("name") or ""
        plays = it.get("playcount") or "0"
        click.echo(f"{i}. {link(name, lastfm_track_url(artist, name))} — {link(artist, lastfm_artist_url(artist))} ({plays})")

@main.command()
@click.option("--name", default=None)
@click.option("--user", default=None)
def artist(name: str | None, user: str | None):
    """Artist info + user playcount."""
    lfm = make_client()
    u = user or lfm.username or ""
    if not name:
        ent = _current_track(user=u)
        name = ent["artist"]
    info = lfm.artist_info(name, username=u)
    url = info.get("url") or lastfm_artist_url(name)
    stats = info.get("stats") or {}
    overall = stats.get("userplaycount") or "0"
    click.echo(link(name, url))
    click.echo(f"Plays (overall): {overall}")

@main.command()
@click.option("--name", default=None)
@click.option("--artist", "artist_name", default=None)
@click.option("--user", default=None)
def album(name: str | None, artist_name: str | None, user: str | None):
    """Album info + user playcount."""
    lfm = make_client()
    u = user or lfm.username or ""
    if not name or not artist_name:
        ent = _current_track(user=u)
        name = name or ent["album"]
        artist_name = artist_name or ent["artist"]
    if not name or not artist_name:
        fatal("Missing album; pass --name and --artist.")
    info = lfm.album_info(artist_name, name, username=u)
    url = info.get("url") or lastfm_album_url(artist_name, name)
    overall = info.get("userplaycount") or "0"
    click.echo(link(name, url))
    click.echo(link(artist_name, lastfm_artist_url(artist_name)))
    click.echo(f"Plays (overall): {overall}")

@main.command()
@click.option("--name", default=None)
@click.option("--artist", "artist_name", default=None)
@click.option("--user", default=None)
def track(name: str | None, artist_name: str | None, user: str | None):
    """Track info + user playcount."""
    lfm = make_client()
    u = user or lfm.username or ""
    if not name or not artist_name:
        ent = _current_track(user=u)
        name = name or ent["track"]
        artist_name = artist_name or ent["artist"]
    info = lfm.track_info(artist_name, name, username=u)
    url = info.get("url") or lastfm_track_url(artist_name, name)
    overall = info.get("userplaycount") or "0"
    click.echo(link(name, url))
    click.echo(link(artist_name, lastfm_artist_url(artist_name)))
    click.echo(f"Plays (overall): {overall}")

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
@click.argument("artist")
@click.argument("track")
@click.option("--album", default=None)
@click.option("--ts", default="now", show_default=True)
def scrobble(artist: str, track: str, album: str | None, ts: str):
    """Submit a scrobble."""
    timestamp = now_ts() if ts.strip().lower() == "now" else int(ts)
    lfm = make_client()
    lfm.scrobble(artist, track, timestamp=timestamp, album=album)
    click.echo("OK")

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
@click.option("-p", "--period", default="month", show_default=True)
def pace(increment: int, period: str):
    """Estimate when you'll hit next milestone based on recent rate."""
    period = _period(period)
    days = {"day":1,"week":7,"month":30,"quarter":90,"year":365,"overall":30}.get(period, 30)
    lfm = make_client()
    info = lfm.user_info()
    total = int(info.get("playcount") or 0)
    next_target = ((total // increment) + 1) * increment
    remaining = next_target - total

    cutoff = now_ts() - days * 86400
    count = 0
    page = 1
    seen_old = False
    while page <= 20 and not seen_old:
        rt = lfm.recent_tracks(limit=200, page=page)
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

@main.group()
def theme():
    """Theme / accent color."""
    pass

@theme.command("show")
def theme_show():
    t = get_theme()
    click.echo(f"accent_sgr={t.accent}")

@theme.command("set")
@click.argument("color")
def theme_set(color: str):
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
