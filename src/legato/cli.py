from __future__ import annotations
import json as _json, subprocess, time
import typer
from rich.console import Console
from .config import load_config, save_config, config_path
from .help import MIN_HELP
from .lastfm import LastfmClient, LastfmError, period_to_lastfm, DEFAULT_API_KEY, DEFAULT_API_SECRET
from .utils import now_ts, human_delta, norm_key, clamp, lastfm_artist_url, lastfm_album_url, lastfm_track_url, env_get
from .youtube import YouTubeClient, YouTubeError

console = Console()
app = typer.Typer(no_args_is_help=True, add_completion=False)

def _lfm() -> LastfmClient:
    cfg = load_config()
    if "REPLACE_ME" in DEFAULT_API_KEY or "REPLACE_ME" in DEFAULT_API_SECRET:
        raise LastfmError("App credentials missing. Set DEFAULT_API_KEY/DEFAULT_API_SECRET in src/legato/lastfm.py")
    return LastfmClient(api_key=DEFAULT_API_KEY, api_secret=DEFAULT_API_SECRET,
                       session_key=cfg.get("lastfm_session_key"), username=cfg.get("username"))

def _parse_period(period: str) -> str:
    p=period.strip().lower()
    m={"d":"day","day":"day","w":"week","week":"week","m":"month","month":"month","q":"quarter","quarter":"quarter","y":"year","year":"year"}
    if p not in m: raise typer.BadParameter("period must be day|week|month|quarter|year")
    return m[p]

def _link(text: str, url: str) -> str:
    return f"[link={url}]{text}[/link]"

@app.command()
def help():
    console.print(MIN_HELP)

@app.command()
def setup(timeout: int = typer.Option(120, "--timeout")):
    lfm=_lfm(); cfg=load_config()
    console.print("Requesting token…")
    token=lfm.get_token()
    url=f"https://www.last.fm/api/auth/?api_key={lfm.api_key}&token={token}"
    try: subprocess.Popen(["xdg-open", url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception: pass
    console.print("Authorize in browser:"); console.print(url)
    console.print("Waiting for approval… (Ctrl+C to cancel)")
    start=time.time()
    while True:
        if time.time()-start>timeout: raise typer.Exit(code=1)
        sess=lfm.try_get_session(token)
        if sess:
            sk, username=sess
            cfg.set("lastfm_session_key", sk); cfg.set("username", username)
            save_config(cfg)
            console.print(f"Connected as {_link(username, f'https://www.last.fm/user/{username}')}")
            return
        time.sleep(2)

def _get_current_entities():
    lfm=_lfm()
    rt=lfm.recent_tracks(limit=1); tracks=rt.get("track") or []
    if isinstance(tracks, dict): tracks=[tracks]
    if not tracks: raise typer.Exit(1)
    t0=tracks[0]
    artist=(t0.get("artist") or {}).get("name") or (t0.get("artist") or {}).get("#text") or ""
    track=t0.get("name") or ""
    album=(t0.get("album") or {}).get("#text") or ""
    attrs=t0.get("@attr") or {}
    now_playing=str(attrs.get("nowplaying","")).lower()=="true"
    ts=None
    if not now_playing:
        uts=(t0.get("date") or {}).get("uts")
        if uts: ts=int(uts)
    return {"artist":artist,"track":track,"album":album,"now_playing":now_playing,"ts":ts,"url":t0.get("url")}

@app.command()
def current(json: bool = typer.Option(False, "--json")):
    lfm=_lfm()
    ent=_get_current_entities()
    payload={"now_playing":ent["now_playing"],"artist":ent["artist"],"track":ent["track"],"album":ent["album"],"timestamp":ent["ts"],"url":ent["url"]}
    if json: console.print(_json.dumps(payload)); return
    user=lfm.username or (load_config().get("username") or "")
    console.print(f"Now playing for {user}:")
    t_url=ent["url"] or lastfm_track_url(ent["artist"], ent["track"])
    console.print(_link(ent["track"], t_url))
    parts=[_link(ent["artist"], lastfm_artist_url(ent["artist"]))] if ent["artist"] else []
    if ent["album"]:
        parts.append(_link(ent["album"], lastfm_album_url(ent["artist"], ent["album"])))
    console.print(" - ".join(parts))
    if (not ent["now_playing"]) and ent["ts"] is not None:
        console.print(human_delta(ent["ts"]))

@app.command()
def np(artist: str, track: str, album: str | None = typer.Option(None, "--album"), duration: int | None = typer.Option(None, "--duration")):
    _lfm().update_now_playing(artist, track, album=album, duration=duration); console.print("OK")

@app.command()
def scrobble(artist: str, track: str, album: str | None = typer.Option(None, "--album"),
             ts: str | None = typer.Option(None, "--ts"), duration: int | None = typer.Option(None, "--duration")):
    timestamp=now_ts() if (ts is None or ts.strip().lower()=="now") else int(ts)
    _lfm().scrobble(artist, track, timestamp=timestamp, album=album, duration=duration); console.print("OK")

top_app=typer.Typer(no_args_is_help=True); app.add_typer(top_app, name="top")

def _top_day_aggregate(kind: str, limit: int):
    lfm=_lfm(); cutoff=now_ts()-24*3600; counts={}; page=1; seen_old=False
    while page<=10 and not seen_old:
        rt=lfm.recent_tracks(limit=200, page=page); tracks=rt.get("track") or []
        if isinstance(tracks, dict): tracks=[tracks]
        for t in tracks:
            if str((t.get("@attr") or {}).get("nowplaying","")).lower()=="true": continue
            uts=(t.get("date") or {}).get("uts")
            if not uts: continue
            uts_i=int(uts)
            if uts_i<cutoff: seen_old=True; break
            artist=(t.get("artist") or {}).get("name") or (t.get("artist") or {}).get("#text") or ""
            track=t.get("name") or ""
            album=(t.get("album") or {}).get("#text") or ""
            if kind=="artist":
                key=norm_key(artist); disp=("artist", artist, None)
            elif kind=="album":
                key=norm_key(f"{artist}::{album}"); disp=("album", artist, album or "")
            else:
                key=norm_key(f"{artist}::{track}"); disp=("track", artist, track)
            counts[key]=(disp, counts.get(key,(disp,0))[1]+1)
        page+=1
    ranked=sorted(counts.values(), key=lambda x:x[1], reverse=True)
    return [(i+1, x[0], x[1]) for i,x in enumerate(ranked[:limit])]

def _print_top_header(kind: str, period: str, username: str):
    console.print(f"Top {kind} ({period}) for {username}:")

@top_app.command("artist")
def top_artist(period: str = typer.Option("week","-p","--period"), limit: int = typer.Option(10,"-n","--limit")):
    p=_parse_period(period); limit=clamp(limit,1,100); lfm=_lfm(); username=lfm.username or (load_config().get("username") or "")
    _print_top_header("artists", p, username)
    if p=="day":
        for rank, disp, plays in _top_day_aggregate("artist", limit):
            artist=disp[1]; console.print(f"{rank}. {_link(artist, lastfm_artist_url(artist))} ({plays})")
        return
    data=lfm.top_artists(period=period_to_lastfm(p), limit=limit); items=data.get("artist") or []
    if isinstance(items, dict): items=[items]
    for i,it in enumerate(items[:limit], start=1):
        name=it.get("name") or ""; plays=int(it.get("playcount") or 0)
        console.print(f"{i}. {_link(name, lastfm_artist_url(name))} ({plays})")

@top_app.command("album")
def top_album(period: str = typer.Option("week","-p","--period"), limit: int = typer.Option(10,"-n","--limit")):
    p=_parse_period(period); limit=clamp(limit,1,100); lfm=_lfm(); username=lfm.username or (load_config().get("username") or "")
    _print_top_header("albums", p, username)
    if p=="day":
        for rank, disp, plays in _top_day_aggregate("album", limit):
            artist=disp[1]; album=disp[2] or ""
            console.print(f"{rank}. {_link(album or '(no album)', lastfm_album_url(artist, album) if album else lastfm_artist_url(artist))} — {_link(artist, lastfm_artist_url(artist))} ({plays})")
        return
    data=lfm.top_albums(period=period_to_lastfm(p), limit=limit); items=data.get("album") or []
    if isinstance(items, dict): items=[items]
    for i,it in enumerate(items[:limit], start=1):
        name=it.get("name") or ""; artist=(it.get("artist") or {}).get("name") or ""; plays=int(it.get("playcount") or 0)
        console.print(f"{i}. {_link(name, lastfm_album_url(artist, name))} — {_link(artist, lastfm_artist_url(artist))} ({plays})")

@top_app.command("track")
def top_track(period: str = typer.Option("week","-p","--period"), limit: int = typer.Option(10,"-n","--limit")):
    p=_parse_period(period); limit=clamp(limit,1,100); lfm=_lfm(); username=lfm.username or (load_config().get("username") or "")
    _print_top_header("tracks", p, username)
    if p=="day":
        for rank, disp, plays in _top_day_aggregate("track", limit):
            artist=disp[1]; track=disp[2]
            console.print(f"{rank}. {_link(track, lastfm_track_url(artist, track))} — {_link(artist, lastfm_artist_url(artist))} ({plays})")
        return
    data=lfm.top_tracks(period=period_to_lastfm(p), limit=limit); items=data.get("track") or []
    if isinstance(items, dict): items=[items]
    for i,it in enumerate(items[:limit], start=1):
        name=it.get("name") or ""; artist=(it.get("artist") or {}).get("name") or ""; plays=int(it.get("playcount") or 0)
        console.print(f"{i}. {_link(name, lastfm_track_url(artist, name))} — {_link(artist, lastfm_artist_url(artist))} ({plays})")

def _week_playcount_from_top(kind: str, name_key: str, artist_key: str | None = None) -> int | None:
    lfm=_lfm()
    for page in range(1,4):
        if kind=="artist":
            items=(lfm.top_artists(period="7day", limit=200, page=page).get("artist") or [])
            if isinstance(items, dict): items=[items]
            for it in items:
                if norm_key(it.get("name",""))==name_key: return int(it.get("playcount") or 0)
        elif kind=="album":
            items=(lfm.top_albums(period="7day", limit=200, page=page).get("album") or [])
            if isinstance(items, dict): items=[items]
            for it in items:
                a=(it.get("artist") or {}).get("name") or ""
                if norm_key(it.get("name",""))==name_key and (artist_key is None or norm_key(a)==artist_key):
                    return int(it.get("playcount") or 0)
        else:
            items=(lfm.top_tracks(period="7day", limit=200, page=page).get("track") or [])
            if isinstance(items, dict): items=[items]
            for it in items:
                a=(it.get("artist") or {}).get("name") or ""
                if norm_key(it.get("name",""))==name_key and (artist_key is None or norm_key(a)==artist_key):
                    return int(it.get("playcount") or 0)
    return None

@app.command()
def artist(name: str | None = typer.Option(None, "--name"), json: bool = typer.Option(False, "--json")):
    ent=_get_current_entities(); artist_name=name or ent["artist"]
    info=_lfm().artist_info(artist_name)
    overall=int(((info.get("stats") or {}).get("userplaycount")) or 0)
    week=_week_playcount_from_top("artist", norm_key(artist_name))
    if json: console.print(_json.dumps({"artist":artist_name,"week_plays":week,"overall_plays":overall,"url":info.get("url")})); return
    console.print(_link(artist_name, info.get("url") or lastfm_artist_url(artist_name)))
    if week is not None: console.print(f"Plays (week): {week}")
    console.print(f"Plays (overall): {overall}")

@app.command()
def album(name: str | None = typer.Option(None, "--name"), artist: str | None = typer.Option(None, "--artist"), json: bool = typer.Option(False, "--json")):
    ent=_get_current_entities()
    album_name=name or ent["album"]; artist_name=artist or ent["artist"]
    if not album_name: raise typer.BadParameter("No album on current track; provide --name and --artist.")
    info=_lfm().album_info(artist_name, album_name)
    overall=int(info.get("userplaycount") or 0)
    week=_week_playcount_from_top("album", norm_key(album_name), norm_key(artist_name))
    if json: console.print(_json.dumps({"album":album_name,"artist":artist_name,"week_plays":week,"overall_plays":overall,"url":info.get("url")})); return
    console.print(_link(album_name, info.get("url") or lastfm_album_url(artist_name, album_name)))
    console.print(_link(artist_name, lastfm_artist_url(artist_name)))
    if week is not None: console.print(f"Plays (week): {week}")
    console.print(f"Plays (overall): {overall}")

@app.command()
def track(name: str | None = typer.Option(None, "--name"), artist: str | None = typer.Option(None, "--artist"), json: bool = typer.Option(False, "--json")):
    ent=_get_current_entities()
    track_name=name or ent["track"]; artist_name=artist or ent["artist"]
    info=_lfm().track_info(artist_name, track_name)
    overall=int(info.get("userplaycount") or 0)
    week=_week_playcount_from_top("track", norm_key(track_name), norm_key(artist_name))
    if json: console.print(_json.dumps({"track":track_name,"artist":artist_name,"week_plays":week,"overall_plays":overall,"url":info.get("url")})); return
    console.print(_link(track_name, info.get("url") or lastfm_track_url(artist_name, track_name)))
    console.print(_link(artist_name, lastfm_artist_url(artist_name)))
    if week is not None: console.print(f"Plays (week): {week}")
    console.print(f"Plays (overall): {overall}")

@app.command()
def pace(increment: int = typer.Option(5000,"-i","--increment"), target: int | None = typer.Option(None,"--target"),
         period: str = typer.Option("month","-p","--period"), json: bool = typer.Option(False,"--json")):
    p=_parse_period(period)
    days={"day":1,"week":7,"month":30,"quarter":90,"year":365}[p]
    lfm=_lfm(); total=int(lfm.user_info().get("playcount") or 0)
    next_target=((total//increment)+1)*increment if target is None else target
    if next_target<=total: raise typer.BadParameter("target must be > current total")
    cutoff=now_ts()-days*86400; count=0; page=1; seen_old=False
    while page<=20 and not seen_old:
        rt=lfm.recent_tracks(limit=200, page=page); tracks=rt.get("track") or []
        if isinstance(tracks, dict): tracks=[tracks]
        for t in tracks:
            if str((t.get("@attr") or {}).get("nowplaying","")).lower()=="true": continue
            uts=(t.get("date") or {}).get("uts")
            if not uts: continue
            uts_i=int(uts)
            if uts_i<cutoff: seen_old=True; break
            count+=1
        page+=1
    rate=count/max(days,1); remaining=next_target-total
    eta_days=(remaining/rate) if rate>0 else None
    if json: console.print(_json.dumps({"total":total,"target":next_target,"remaining":remaining,"rate_per_day":rate,"eta_days":eta_days})); return
    console.print(f"Total scrobbles: {total}")
    console.print(f"Next target: {next_target} (remaining {remaining})")
    console.print(f"Rate: {rate:.2f}/day (sample {count} over {days}d)")
    if eta_days is None: console.print("ETA: unknown"); return
    import datetime as dt
    console.print(f"ETA: {dt.datetime.fromtimestamp(int(time.time()+eta_days*86400)).strftime('%Y-%m-%d')} (~{eta_days:.1f} days)")

@app.command()
def yt(artist: str | None = typer.Argument(None), track: str | None = typer.Argument(None),
       open: bool = typer.Option(False,"--open"), copy: bool = typer.Option(False,"--copy")):
    cfg=load_config()
    yt_key=cfg.get("youtube_api_key") or env_get("LEGATO_YT_KEY")
    if not yt_key: raise typer.BadParameter("Missing youtube_api_key. Set with `legato config set youtube_api_key ...`")
    if artist is None or track is None:
        ent=_get_current_entities(); artist=artist or ent["artist"]; track=track or ent["track"]
    res=YouTubeClient(api_key=str(yt_key)).search_best(artist, track)
    url=str(res.get("url")); console.print(_link(res.get("title") or url, url))
    if copy:
        for cmd in (["wl-copy"], ["xclip","-selection","clipboard"]):
            try:
                p=subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                p.communicate(input=url.encode("utf-8"), timeout=2)
                if p.returncode==0: break
            except Exception: pass
    if open:
        try: subprocess.Popen(["xdg-open", url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception: pass

config_app=typer.Typer(no_args_is_help=True); app.add_typer(config_app, name="config")

@config_app.command("path")
def _cpath(): console.print(str(config_path()))

@config_app.command("get")
def _cget(key: str):
    v=load_config().get(key)
    if v is None: raise typer.Exit(1)
    console.print(str(v))

@config_app.command("set")
def _cset(key: str, value: str):
    cfg=load_config(); cfg.set(key, value); save_config(cfg); console.print("OK")

@app.command()
def doctor():
    cfg=load_config()
    console.print(f"Config: {config_path()}")
    console.print(f"Username: {cfg.get('username') or '(none)'}")
    console.print(f"Session key: {'yes' if cfg.get('lastfm_session_key') else 'no'}")
    console.print(f"YouTube key: {'yes' if cfg.get('youtube_api_key') else 'no'}")

def main():
    try:
        app()
    except (LastfmError, YouTubeError) as e:
        console.print(f"error {e}")
        raise SystemExit(1)

if __name__ == "__main__":
    main()
