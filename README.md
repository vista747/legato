# legato (Linux-only)

A minimal terminal client for Last.fm.

## Install (recommended)
```bash
python3 -m pip install --user pipx
pipx ensurepath
pipx install legato
```

## Setup
Legato uses the Last.fm desktop/web auth flow: it opens a browser to approve access, then polls for a session key.
Session keys are long-lived unless the user revokes your app in Last.fm settings.

```bash
legato setup
```

## Output style
No bordered tables. Plain text. Links are terminal hyperlinks (OSC 8) where supported.

## YouTube
`legato yt` prints a YouTube search link for the current track and notes that a smarter matcher is coming soon.

## App credentials (important)
Last.fm requires an **API key + shared secret for your application** (not the user). You must set these before release.

Edit:
- `src/legato/lastfm.py` -> `APP_API_KEY` and `APP_API_SECRET`

## Commands
- `legato current` (now playing / last scrobble)
- `legato recent [-n N] [--user USER]`
- `legato top artist|album|track [-p day|week|month|quarter|year|overall] [-n N]`
- `legato artist|album|track [--name ...] [--artist ...]`
- `legato np ARTIST TRACK [--album ...]` (update now playing)
- `legato scrobble ARTIST TRACK [--album ...] [--ts now|UNIX]`
- `legato love [ARTIST] [TRACK]` (defaults to current)
- `legato unlove [ARTIST] [TRACK]`
- `legato profile [--user USER]`
- `legato friends [--user USER] [-n N]`
- `legato pace [-i 5000] [-p month|week|year|day]`
- `legato yt [ARTIST] [TRACK] [--open]`
- `legato theme set <color>` (accent color; default bright red)
- `legato theme show`
- `legato doctor`
- `legato api METHOD [key=value ...]` (power-user escape hatch; read methods only unless --write)

## Notes
Legato aims to cover the core Last.fm functionality exposed by the official API (recent, now playing, scrobble, top, info, love/unlove, profile, friends).
Discord-server-only features are intentionally omitted.
