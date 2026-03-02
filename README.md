# legato

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

## Output style
No bordered tables. Plain text. Links are terminal hyperlinks (OSC 8) where supported.

## YouTube
`legato yt` prints a YouTube search link for the current track and notes that a smarter matcher is coming soon.

## App credentials (important)
Last.fm requires an **API key + shared secret for your application** (not the user). You must set these before release.

Edit:
- `src/legato/lastfm.py` -> `APP_API_KEY` and `APP_API_SECRET`

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

## Notes
Legato aims to cover the core Last.fm functionality exposed by the official API (recent, now playing, scrobble, top, info, love/unlove, profile, friends).
Discord-server-only features are intentionally omitted.

## Publish to PyPI (GitHub Actions)

This repo includes [publish workflow](.github/workflows/publish-pypi.yml) that:
- builds package artifacts,
- runs `twine check`,
- publishes to PyPI when you push a tag like `v0.5.0`.

### One-time setup
1. Create a PyPI API token (scope it to this project).
2. In GitHub: **Settings → Secrets and variables → Actions → New repository secret**.
3. Add secret name: `PYPI_API_TOKEN`, value: your token.

### Release flow
1. Bump version in `pyproject.toml`.
2. Commit and push.
3. Create and push a tag:

```bash
git tag v0.5.0
git push origin v0.5.0
```

4. Watch Actions run; after success users can install/update with:

```bash
pipx install legato
# or
pipx upgrade legato
```
