# legato v1.0.5

Legato is a lightweight terminal client for Last.fm.

This project is currently in beta and minor bugs may occur.
PyPI: https://pypi.org/project/legato-fm/

## Installation

Recommended (isolated install via `pipx`):

```bash
python3 -m pip install --user pipx
pipx install legato-fm
```

Upgrade later with:

```bash
pipx upgrade legato-fm
```

## First-time setup

Run setup once to connect your Last.fm account:

```bash
legato setup
```

This opens your browser for Last.fm authorization, then saves your session locally.

## Quick start

```bash
legato current
legato recent -n 5
legato top artist -p month -n 10
```

## Common tasks

### See what’s playing

```bash
legato current
# alias:
legato fm
```

### View recent listens

```bash
legato recent
legato recent -n 20
legato recent --user exampleuser
```

### Get top artists/albums/tracks

```bash
legato top artist -p week -n 10
legato top album -p month -n 10
legato top track -p year -n 25
```

Supported periods: `day`, `week`, `month`, `quarter`, `year`, `overall` (also `alltime`, `all`).

### Inspect stats for one item

```bash
legato artist "Dominic Fike"
legato album "Dijon | Absolutely"
legato track "Duster | Inside Out"
```

### Check play counts and first listen

```bash
legato plays --target artist --query "Charli xcx"
legato first --query "Muse | Uprising"
```

### Love / unlove tracks

```bash
legato love "George Clanton" "I Been Young"
legato unlove "Kevin Abstract" "Peach"
```

If no artist/track is passed, Legato uses your current track when possible.

### Scrobble manually

```bash
legato scrobble "Jai Paul" "Jasmine"
legato scrobble "Lorde | Ribs | Pure Heroine" --ts now
```

### Open a YouTube search for a track

```bash
legato yt
legato yt "Bakar" "Hell N Back" --open
```

### Profile and social

```bash
legato profile
legato friends -n 20
legato taste exampleuser -p month -n 10
```

### Theme and diagnostics

```bash
legato theme show
legato theme set red
legato doctor
```

## Full command list

- `legato --version`
- `legato setup`
- `legato current`
- `legato fm`
- `legato disconnect`
- `legato recent [-n N] [--user USER]`
- `legato top artist|album|track [-p day|week|month|quarter|year|overall|alltime|all] [--year YYYY] [-n N]`
- `legato artist|album|track [--name ...] [--artist ...]`
- `legato artist "ARTIST"`
- `legato album "ARTIST | ALBUM"`
- `legato track "ARTIST | TRACK"`
- `legato album [--query "ARTIST | ALBUM"] [--user USER]`
- `legato plays [--target artist|album|track] [--query "..."] [--name ...] [--artist ...] [--user USER]`
- `legato np ARTIST TRACK [--album ...]`
- `legato scrobble ARTIST TRACK [--album ...] [--ts now|UNIX]`
- `legato scrobble "ARTIST | TRACK[ | ALBUM]" [--album ...] [--ts now|UNIX]`
- `legato first [--query "ARTIST[ | TRACK]"] [--artist ...] [--track ...] [--user USER]`
- `legato taste OTHER_USER [--user USER] [-p period] [-n N]`
- `legato love [ARTIST] [TRACK]`
- `legato unlove [ARTIST] [TRACK]`
- `legato profile [--user USER]`
- `legato friends [--user USER] [-n N]`
- `legato pace [-i 5000] [-p month|week|year|day]`
- `legato yt [ARTIST] [TRACK] [--open]`
- `legato theme set <color>`
- `legato theme show`
- `legato doctor`
- `legato api METHOD [key=value ...]`

## Uninstall

```bash
pipx uninstall legato-fm
```
