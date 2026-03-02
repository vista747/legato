# legato v1.0.3

A minimal terminal client for Last.fm.

## Install (recommended)
```bash
python3 -m pip install --user pipx
pipx install legato-fm
```

## Setup
Legato uses the Last.fm desktop/web auth flow: it opens a browser to approve access, then polls for a session key.
Session keys are long-lived unless the user revokes your app in Last.fm settings.

```bash
legato setup
```

## YouTube
`legato yt` prints a YouTube search link for the current track and notes that a smarter matcher is coming soon.


## Commands
- `legato --version`
- `legato current` (now playing / last scrobble)
- `legato fm` (FMbot-style alias for current)
- `legato disconnect` (remove saved session + username from local config)
- `legato recent [-n N] [--user USER]`
- `legato top artist|album|track [-p day|week|month|quarter|year|overall|alltime|all] [--year YYYY] [-n N]`
- `legato artist|album|track [--name ...] [--artist ...]`
- `legato artist "ARTIST"`
- `legato album "ARTIST | ALBUM"`
- `legato track "ARTIST | TRACK"`
- `legato album [--query "ARTIST | ALBUM"] [--user USER]`
- `legato plays [--target artist|album|track] [--query "..."] [--name ...] [--artist ...] [--user USER]`
- `legato np ARTIST TRACK [--album ...]` (update now playing)
- `legato scrobble ARTIST TRACK [--album ...] [--ts now|UNIX]`
- `legato scrobble "ARTIST | TRACK[ | ALBUM]" [--album ...] [--ts now|UNIX]`
- `legato first [--query "ARTIST[ | TRACK]"] [--artist ...] [--track ...] [--user USER]`
- `legato taste OTHER_USER [--user USER] [-p period] [-n N]`
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


4. Watch Actions run; after success users can install/update with:

```bash
pipx install legato
# or
pipx upgrade legato
```
